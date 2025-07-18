import json
import base64
from datetime import datetime
from uuid import uuid4
from pytz import timezone, utc

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

    retrieve_days_before = fields.Integer(string="Days before date since", default=7, help="How many days before date since should be retrieved to process transactions with diferent booking and value date.")

    add_additional_information_in_ref = fields.Boolean(string="Add additional information in reference", help="If checked, the additional information will be added to the payment reference of the transaction.")

    use_date = fields.Selection(
        selection=[
            ('operation_date', 'Operation Date'),
            ('value_date', 'Value Date'),
        ],
    )

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
                % {"iban_number": online_bank_statement_provider.journal_id.bank_account_id.display_name}
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
        journal_currency_id = self.journal_id.currency_id or self.journal_id.company_id.currency_id
        for tr in transactions:
            values = {}
            if self.use_date == 'operation_date':
                string_date = tr.get("txOperationDate") or tr.get("txValueDate")
            elif self.use_date == 'value_date':
                string_date = tr.get("txValueDate") or tr.get("txOperationDate")
            # CHECK ME: if there's not date string, is transaction still valid?
            if not string_date:
                continue
            current_date = fields.Date.from_string(string_date)
            sequence += 1
            amount = float(tr.get("txAmount", 0.0))
            balance = float(tr.get("txBalance", 0.0) or 0.0)
            amount_currency = float(tr.get("txOriginalAmount", 0.0) or 0.0)
            
            foreign_currency_code = tr.get("txCurrency", journal_currency_id.name)
            foreign_currency_id = currencies_cache.get(foreign_currency_code)
            if not foreign_currency_id:
                foreign_currency_id = currency_model.search([("name", "=", foreign_currency_code)])
                currencies_cache[foreign_currency_code] = foreign_currency_id

            if foreign_currency_id and foreign_currency_id.id != journal_currency_id.id:
                values.update({
                    "foreign_currency_id": foreign_currency_id.id,
                    "amount_currency": amount_currency,
                })
            # if (
            #     self.bankifai_account_id.currency_id
            #     and self.journal_id.currency_id
            #     and self.bankifai_account_id.currency_id.id != self.journal_id.currency_id.id
            # ):
            #     amount_currency = self.bankifai_account_id.currency_id._convert(
            #         amount,
            #         self.journal_id.currency_id,
            #         self.journal_id.company_id,
            #         current_date,
            #     )
            #     balance_currency = self.bankifai_account_id.currency_id._convert(
            #         balance,
            #         self.journal_id.currency_id,
            #         self.journal_id.company_id,
            #         current_date,
            #     )
            partner_name = tr.get("txTransferSenderReceiver", "")
            account_number = tr.get("txTransferAccountNumber", "")
            if account_number == own_acc_number:
                account_number = False  # Discard own bank account number
            
            values.update({
                "sequence": sequence,
                "date": current_date,
                "ref": self.bankifai_get_payment_ref(tr),
                "payment_ref": self.bankifai_get_payment_ref(tr),
                "unique_import_id": self._get_bankifai_unique_import_id(tr),
                "amount": amount,
                "account_number": account_number,
                "partner_name": partner_name,
                "transaction_type": tr.get("bankTransactionCode", ""),
                "narration": self.bankifai_get_note(tr),
                "category_id": self._get_bankifai_category_id(tr),
            })
            res.append(values)

            if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.sort_transactions", 'True')) and self.bankifai_account_id.account_type == 'ACCOUNT' and not 'balance_start' in statement_data:
                statement_data['balance_start'] = balance - amount
        return res, statement_data

    def _create_or_update_statement(
        self, data, statement_date_since, statement_date_until
    ):
        if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.use_cashflow_historical_balance", 'True')) and self.bankifai_account_id.account_type == 'ACCOUNT' and self.bankifai_connection_id.last_refresh_datetime.date() >= statement_date_since.date():

            bankifai_cashflow_id = self.bankifai_account_id.bankifai_cashflow_ids.filtered_domain([('cashflow_type', '=', 'historical'), ('date', '=', statement_date_since.date() - relativedelta(days=1))])

            if bankifai_cashflow_id:
                if not data:
                    data = ([], {})
                
                unfiltered_lines, statement_values = data
                statement_values['balance_start'] = bankifai_cashflow_id.balance

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
    
    def bankifai_get_payment_ref(self, tr):
        payment_ref_elements = [
            "txDescription",
            "txTransferAccountNumber",
        ]
        payment_refs = [str(tr[element]) for element in payment_ref_elements if tr.get(element)]

        if self.add_additional_information_in_ref:
            payment_refs += [str(additional_info.get("value", "")) for additional_info in tr.get("additionalInfo", []) if additional_info.get("value")]

        return " | ".join(payment_refs) if payment_refs else "/"


    def bankifai_get_note(self, tr):
        """Override to get different notes."""
        note_elements = [
            ("txOperationDate", "OperationDate: ", lambda element: element),
            ("txValueDate", "ValueDate: ", lambda element: element),
            ("txDescription", "Description: ", lambda element: element),
            ("txBalance", "Balance: ", lambda element: element),
            ("txAmount", "Amount: ", lambda element: element),
            ("txExchangeRate", "ExchangeRate: ", lambda element: element),
            ("txCurrency", "Currency: ", lambda element: element),
            ("txOriginalAmount", "OriginalAmount: ", lambda element: element),
            ("txSettled", "Settled: ", lambda element: element),
            ("txTransferSenderReceiver", "TransferSenderReceiver: ", lambda element: element),
            ("txTransferAccountNumber", "TransferAccountNumber: ", lambda element: element),
            ("category", "Category: ", lambda element: element.get('description', '')),
            ("additionalInfo", "AdditionalInfo: ", lambda element: " | ".join([f"{info.get('key', '')}: {info.get('value', '')}" for info in element]) if isinstance(element, list) else ""),
        ]
        notes = [str(label) + str(transformation(tr[key])) for key, label, transformation in note_elements if transformation(tr.get(key))]
        return "\n".join(notes)

    def _get_statement_filtered_lines(
        self,
        unfiltered_lines,
        statement_values,
        statement_date_since,
        statement_date_until,
    ):
        """Get lines from line data, but only for the right date."""
        if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.force_statement_line_update", 'False')):
            AccountBankStatementLine = self.env["account.bank.statement.line"]
            provider_tz = timezone(self.tz) if self.tz else utc
            journal = self.journal_id
            filtered_lines = []
            for line_values in unfiltered_lines:
                date = line_values["date"]
                if not isinstance(date, datetime):
                    date = fields.Datetime.from_string(date)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=utc)
                date = date.astimezone(utc).replace(tzinfo=None)
                if date < statement_date_since:
                    continue
                elif date >= statement_date_until:
                    continue
                date = date.replace(tzinfo=utc)
                date = date.astimezone(provider_tz).replace(tzinfo=None)
                line_values["date"] = date
                previous_unique_import_id = line_values.get("unique_import_id")
                journal._statement_line_import_update_unique_import_id(
                    line_values, self.account_number
                )
                unique_import_id = line_values.get("unique_import_id")
                if unique_import_id:
                    statement_line_id = AccountBankStatementLine.sudo().search(
                        [("unique_import_id", "=", unique_import_id), ('is_reconciled', '=', False)], limit=1
                    )
                    if statement_line_id:
                        statement_line_id.write(line_values)
                line_values["unique_import_id"] = previous_unique_import_id
        return super()._get_statement_filtered_lines(
            unfiltered_lines,
            statement_values,
            statement_date_since,
            statement_date_until,
        )