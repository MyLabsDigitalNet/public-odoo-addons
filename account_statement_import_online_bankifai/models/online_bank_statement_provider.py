import json
import base64
from datetime import datetime
from uuid import uuid4

import requests
from dateutil.relativedelta import relativedelta
from werkzeug.urls import url_join

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, str2bool


class OnlineBankStatementProvider(models.Model):
    _inherit = "online.bank.statement.provider"

    interval_number = fields.Integer(default=4)

    # bankifai_token_expiration = fields.Datetime(related='bankifai_user_id.token_expiration', readonly=True)
    # bankifai_connectionId = fields.Char(string='Connection ID', readonly=True)
    bankifai_user_id = fields.Many2one(comodel_name='bankifai.user', string='BankifAI User')
    bankifai_connection_id = fields.Many2one(comodel_name='bankifai.connection', string='BankifAI Connection')
    bankifai_account_id = fields.Many2one(comodel_name='bankifai.account', string="BankifAI Current Account")
    bankifai_callback_url = fields.Char(string="BankifAI Redirect URL", compute='_compute_bankifai_callback_url')
    bankifai_connection_status_code = fields.Char(related='bankifai_connection_id.status_code')

    retrieve_days_before = fields.Integer(string="Days before date since", default=1, help="How many days before date since should be retrieved to process transactions with diferent booking and value date.")

    @api.constrains('retrieve_days_before')
    def _check_retrieve_days_before(self):
        for record in self:
            if record.retrieve_days_before < 0:
                raise ValidationError("Days before date since must be 0 or greatter.")
            
    def _pull(self, date_since, date_until):
        if self.service == "bankifai" and self.env.context.get("scheduled", False):
            date_since = date_since - relativedelta(days=self.retrieve_days_before)
        return super()._pull(date_since, date_until)

    def _compute_bankifai_callback_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        callback_url = url_join(base_url, "dedomena/response")
        self.write({'bankifai_callback_url': callback_url})

    @api.model
    def _get_available_services(self):
        """Include the new service BankifAI in the online providers."""
        return super()._get_available_services() + [
            ("bankifai", "BankifAI"),
        ]

    def _bankifai_get_matched_bankifai_account_ids(self):
        self.ensure_one()
        if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.check_callback_url", 'True')):
            bankifai_account_ids = self.bankifai_user_id.bankifai_connection_ids.filtered(lambda connection: connection.callback_url == self.bankifai_callback_url)._get_matched_bankifai_account_ids(self.account_number)
        else:
            bankifai_account_ids = self.bankifai_user_id.bankifai_connection_ids._get_matched_bankifai_account_ids(self.account_number)
        return bankifai_account_ids

    def _bankifai_get_connection_id(self, bankifai_connection_identification):
        return self.bankifai_user_id.bankifai_connection_ids.filtered(lambda connection: connection.connection_identification == bankifai_connection_identification)

    def _set_bankifai_connection_id(self, bankifai_connection_id, dry=False):
        self.write({'bankifai_connection_id': bankifai_connection_id.id})
        bankifai_connection_id._finish_connection(dry=dry)
        self.journal_id._update_expected_expiring_synchronization_date()

    def bankifai_susccess_agregation(self, bankifai_connection_identification):
        self.ensure_one()
        self.bankifai_user_id._update_connections()
        bankifai_connection_id = self._bankifai_get_connection_id(bankifai_connection_identification)
        self._set_bankifai_connection_id(bankifai_connection_id)

    def bankifai_get_token(self, force_refresh=False):
        self.ensure_one()
        return self.bankifai_user_id._get_token()

    def _get_action_create_user(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('account_statement_import_online_bankifai.bankifai_user_create_wizard_action')
        context = json.loads(action.get('context', '{}'))
        context.update(
            {
                'default_online_bank_statement_provider_id': self.id,
            }
        )
        action['context'] = json.dumps(context)
        return action

    def action_select_bankifai_bank(self):
        self.ensure_one()
        if not self.env.context.get('update_consent', False):
            
            if self.service != 'bankifai':
                self.service = 'bankifai'

            if not self.bankifai_user_id:
                return self._get_action_create_user()

            self.bankifai_user_id._update_connections()
            self.bankifai_user_id.bankifai_connection_ids._update_accounts()
            bankifai_account_ids = self._bankifai_get_matched_bankifai_account_ids()
            if bankifai_account_ids:  # TODO filter tambien por estado de la conexion
                action = self.env['ir.actions.actions']._for_xml_id('account_statement_import_online_bankifai.bankifai_connection_existing_wizard_action')
                context = json.loads(action.get('context', '{}'))
                context.update(
                    {
                        'default_online_bank_statement_provider_id': self.id,
                        'default_bankifai_connection_id': fields.first(bankifai_account_ids.bankifai_connection_id).id,
                        'default_available_bankifai_connection_ids': bankifai_account_ids.bankifai_connection_id.ids,
                    }
                )
                action['context'] = json.dumps(context)
                return action
        return self.action_open_bankifai_widget()

    def action_open_bankifai_widget(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'bankifai_widget',
            'target': 'new',
            'context': {
                'active_online_bank_statement_provider_id': self.id,
            },
        }

    def bankifai_update_connection(self, bankifai_connection_identification):
        self._bankifai_get_connection_id(bankifai_connection_identification)._update_connection()

    def action_disconnect(self):
        self.sudo().write(
            {
                "bankifai_connection_id": False,
                "bankifai_account_id": False,
            }
        )
        self.journal_id._update_expected_expiring_synchronization_date()  # To remove activities
        for online_bank_statement_provider in self:
            online_bank_statement_provider.sudo().message_post(
                body=_(
                    "Your account number %(iban_number)s has been successfully disconnected.")
                % {"iban_number": self.journal_id.bank_account_id.display_name}
            )
        return True

    def _obtain_statement_data(self, date_since, date_until):
        """Generic online cron overrided for acting when the sync is for BankifAI."""
        self.ensure_one()
        if self.service == "bankifai":
            return self._bankifai_obtain_statement_data(date_since, date_until)
        return super()._obtain_statement_data(date_since, date_until)

    def _bankifai_request_transactions(self, date_since, date_until):
        """Method for requesting BankifAI transactions."""
        return self.bankifai_account_id._request_transactions(date_since, date_until)

    def _bankifai_should_update_connection(self):
        return self.bankifai_connection_id.status_code != 'OK' or not self.bankifai_account_id

    def _bankifai_account_is_ready(self):
        return self.bankifai_connection_id.status_code == 'OK' and self.bankifai_account_id

    def _bankifai_obtain_statement_data(self, date_since, date_until):
        """Called from the cron or the manual pull wizard to obtain transactions for
        the given period.
        """
        self.ensure_one()
        if self._bankifai_should_update_connection():
            self.bankifai_connection_id._update_connection()
        if not self._bankifai_account_is_ready():
            return [], {}
        
        self.bankifai_account_id._update_cashflow_historical()
        self.bankifai_account_id._update_cashflow_forecasts()

        currency_model = self.env["res.currency"]

        own_acc_number = self.account_number
        transactions = self._bankifai_request_transactions(date_since, date_until)

        res = []
        sequence = 0
        currencies_cache = {}
        statement_data = {}
        for tr in transactions:
            string_date = tr.get("txValueDate") or tr.get("txOperationDate")
            # CHECK ME: if there's not date string, is transaction still valid?
            if not string_date:
                continue
            current_date = fields.Date.from_string(string_date)
            sequence += 1
            amount = float(tr.get("txAmount", 0.0))
            balance = float(tr.get("txBalance", 0.0) or 0.0)
            amount_currency = amount
            balance_currency = balance
            if (
                self.bankifai_account_id.currency_id
                and self.journal_id.currency_id
                and self.bankifai_account_id.currency_id.id != self.journal_id.currency_id.id
            ):
                amount_currency = self.bankifai_account_id.currency_id._convert(
                    amount,
                    self.journal_id.currency_id,
                    self.journal_id.company_id,
                    current_date,
                )
                balance_currency = self.bankifai_account_id.currency_id._convert(
                    balance,
                    self.journal_id.currency_id,
                    self.journal_id.company_id,
                    current_date,
                )
            partner_name = tr.get("txTransferSenderReceiver", False)
            account_number = tr.get("txTransferAccountNumber", "")
            if account_number == own_acc_number:
                account_number = False  # Discard own bank account number
            if "txDescription" in tr:
                payment_ref = tr["txDescription"]
            elif "remittanceInformationUnstructured" in tr:
                payment_ref = tr["remittanceInformationUnstructured"]
            elif "remittanceInformationUnstructuredArray" in tr:
                payment_ref = " ".join(
                    tr["remittanceInformationUnstructuredArray"])
            else:
                payment_ref = partner_name

            res.append(
                {
                    "sequence": sequence,
                    "date": current_date,
                    "ref": partner_name or "/",
                    "payment_ref": payment_ref,
                    "unique_import_id": self._get_bankifai_unique_import_id(tr),
                    "amount": amount_currency,
                    "account_number": account_number,
                    "partner_name": partner_name,
                    "transaction_type": tr.get("bankTransactionCode", ""),
                    "narration": self.bankifai_get_note(tr),
                    "category_id": self._get_bankifai_category_id(tr),
                }
            )

            if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.sort_transactions", 'True')) and self.bankifai_account_id.account_type == 'ACCOUNT' and not 'balance_start' in statement_data:
                statement_data['balance_start'] = balance_currency - amount_currency
        return res, statement_data

    def _create_or_update_statement(
        self, data, statement_date_since, statement_date_until
    ):
        if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.use_cashflow_historical_balance", 'True')) and self.bankifai_account_id.account_type == 'ACCOUNT' and self.bankifai_connection_id.last_refresh_datetime.date() >= statement_date_since.date():

            bankifai_cashflow_id = self.bankifai_account_id.bankifai_cashflow_ids.filtered_domain([('has_historical', '=', True), ('date', '=', statement_date_since.date() - relativedelta(days=1))])

            if bankifai_cashflow_id:
                if not data:
                    data = ([], {})
                
                unfiltered_lines, statement_values = data
                statement_values['balance_start'] = bankifai_cashflow_id.cashflow_balance

        return super(OnlineBankStatementProvider, self)._create_or_update_statement(data, statement_date_since, statement_date_until)

    def _get_bankifai_unique_import_id(self, tr):
        self.ensure_one()
        return str(self.bankifai_account_id.account_provider_identification) + tr.get("txProviderId")

    def _get_bankifai_category_id(self, tr):
        category_data = tr.get('category', False)

        if not category_data:
            return False

        category_id = self.env['account.bank.statement.line.category'].search([('bankifai_indentification', '=', category_data.get('catId'))])
        if not category_id:
            category_id = self.env['account.bank.statement.line.category'].sudo().create(
                {
                    'bankifai_indentification': category_data.get('catId'),
                    'parent_id': self.env['account.bank.statement.line.category'].search([('bankifai_indentification', '=', category_data.get('parentId'))]).id,
                    'code': category_data.get('code'),
                    'name': category_data.get('description'),
                }
            )

        return category_id.id

    def bankifai_get_note(self, tr):
        """Override to get different notes."""
        note_elements = [
            "additionalInformation",
            "balanceAfterTransaction",
            "bankTransactionCode",
            "bookingDate",
            "checkId",
            "creditorAccount",
            "creditorAgent",
            "creditorId",
            "creditorName",
            "currencyExchange",
            "debtorAccount",
            "debtorAgent",
            "debtorName",
            "entryReference",
            "mandateId",
            "proprietaryBank",
            "remittanceInformation Unstructured",
            "transactionAmount",
            "transactionId",
            "ultimateCreditor",
            "ultimateDebtor",
            "valueDate",
        ]
        notes = [str(tr[element]) for element in note_elements if tr.get(element)]
        return "\n".join(notes)


