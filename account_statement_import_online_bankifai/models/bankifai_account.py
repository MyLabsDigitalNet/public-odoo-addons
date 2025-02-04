import requests
import json
import base64
from collections import defaultdict
from werkzeug.urls import url_join
from dateutil.relativedelta import relativedelta

from odoo import fields, models, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, float_compare, float_is_zero, float_round, str2bool


class BankifAIAccount(models.Model):
    _name = 'bankifai.account'
    _description = "BankifAI Account"

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    account_type = fields.Char(string="Account Type")
    account_subtype = fields.Char(string="Account Subtype")
    account_indentification = fields.Integer(string="BankifAI Account ID")
    account_provider_identification = fields.Char(string="BankifAI Account Provider ID")
    account_number = fields.Char(string="Account Number")
    account_name = fields.Char(string="Account Name")
    account_company_name = fields.Char(string="Account Company Name")
    account_currency = fields.Char(string="Account Currency")
    account_available_balance = fields.Monetary(string="Available Balance")
    account_current_balance = fields.Monetary(string="Current Balance")
    card_limit_balance = fields.Monetary(string="Card Limit Balance")
    card_disposed_balance = fields.Monetary(string="Card Disposed Balance")
    card_linked_account = fields.Char(string="Card Linked Account")  # TODO: compute account id
    card_next_payment_date = fields.Char(string="Card Next Payment Date")  # TODO: compute date
    card_status = fields.Char(string="Card Status")
    card_annual_interest = fields.Float(string="Card Annual Interest")
    card_tae = fields.Float(string="Card TAE")
    bankifai_connection_id = fields.Many2one(comodel_name='bankifai.connection', string="BankifAI Connection", ondelete='cascade')
    
    bankifai_cashflow_ids = fields.One2many(comodel_name='bankifai.cashflow', inverse_name='bankifai_account_id', string='BankifAI Cashflows')

    currency_id = fields.Many2one(comodel_name='res.currency', compute='_compute_res_currency', store=True)

    @api.depends('account_name', 'account_number')
    def _compute_name(self):
        for account in self:
            account.name = f'{account.account_name} - {account.account_number}'

    @api.depends('account_currency')
    def _compute_res_currency(self):
        currencies_cache = {}
        for account in self:
            currency = currencies_cache.get(account.account_currency, False)
            if not currency and account.account_currency:
                currency = self.env['res.currency'].search(
                    [("name", "=", account.account_currency)])
                currencies_cache[account.account_currency] = currency
            account.currency_id = currency

    def _request_transactions(self, date_since, date_until):
        """Method for requesting BankifAI transactions."""
        now = fields.Datetime.now()
        if now > date_since and now < date_until:
            date_until = now
        _response, data = self.bankifai_connection_id.bankifai_user_id._get_request(
            "financialviewer/transaction",
            params={
                "accountIds": ",".join(map(str, self.mapped('account_indentification'))),
                "valueDateFrom": date_since.strftime(DF),
                "valueDateTo": date_until.strftime(DF),
                "sortBy": "txValueDate",
                "order": "ASC",
            },
        )

        transactions = data.get("transactions", {})

        if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.sort_transactions", 'True')):
            transactions = self._sort_transactions(transactions)
        
        return transactions

    @api.model
    def _sort_transactions(self, transactions):
        if len(transactions) < 2:
            return transactions
        transactions_by_balance = defaultdict(list)
        first_transacction = False
        ordered_transactions = []
        for tr in transactions:
            transactions_by_balance[round(tr['txBalance'], 2)].append(tr)
        for tr in transactions:
            previous_balance = round(tr['txBalance'] - tr['txAmount'], 2)
            transactions_list = transactions_by_balance[previous_balance]
            if transactions_list:
                previous_tr = transactions_list.pop()
                previous_tr['next'] = tr
            else:
                first_transacction = tr
        while first_transacction:
            ordered_transactions.append(first_transacction)
            first_transacction = first_transacction.get('next', False)
        if len(transactions) > len(ordered_transactions):
            return transactions
        return ordered_transactions

    def _check_account_and_card_number(self, acc_numbers):
        self.ensure_one()
        match_number = False
        if not isinstance(acc_numbers, list):
            acc_numbers = [acc_numbers]
        for number in acc_numbers:
            if not isinstance(number, str) or not number.strip():
                continue
            if self.account_type == 'ACCOUNT':
                match_number |= self.account_number.upper() == number.upper()
            elif self.account_type == 'CARD':
                left_card_numbers_check = int(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.left_card_numbers_check", 4))
                rigth_card_numbers_check = int(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.rigth_card_numbers_check", 4))
                match_number |= self.account_number.upper()[:left_card_numbers_check] == number.upper()[:left_card_numbers_check] and self.account_number.upper()[-rigth_card_numbers_check:] == number.upper()[-rigth_card_numbers_check:]
        return match_number

    def _get_account_data(self, account_data, data={}):
        def _is_id_updated(old, new):
            return bool(new) and old.id != new

        def _is_integer_updated(old, new):
            if new is None:
                return False
            return bool(new) and int(old) != int(new)

        def _is_string_updated(old, new):
            return bool(new) and (old or '').lower() != new.lower()

        def _is_array_updated(old, new):
            return bool(new) and set(old) != set(new)

        def _is_float_updated(old, new):
            if new is None:
                return False
            return float_compare(float(old), float(new), precision_digits=2)

        # returned tupple format (should_be_updated function, new_data, data transformation function)
        account_data_map = {
            'account_type': lambda conn_data: (_is_string_updated, conn_data['accountType'], lambda data: data),
            'account_subtype': lambda conn_data: (_is_string_updated, conn_data['accountSubtype'], lambda data: data),
            'account_indentification': lambda conn_data: (_is_integer_updated, conn_data['accountId'], lambda data: data),
            'account_provider_identification': lambda conn_data: (_is_string_updated, conn_data['accountProviderId'], lambda data: data),
            'account_number': lambda conn_data: (_is_string_updated, conn_data['accountNumber'], lambda data: data),
            'account_name': lambda conn_data: (_is_string_updated, conn_data['accountName'], lambda data: data),
            'account_company_name': lambda conn_data: (_is_string_updated, conn_data['accountCompanyName'], lambda data: data),
            'account_currency': lambda conn_data: (_is_string_updated, conn_data['accountCurrency'], lambda data: data),
            'account_available_balance': lambda conn_data: (_is_float_updated, conn_data['accountAvailableBalance'], lambda data: data),
            'account_current_balance': lambda conn_data: (_is_float_updated, conn_data['accountCurrentBalance'], lambda data: data),
            'card_limit_balance': lambda conn_data: (_is_float_updated, conn_data['cardLimitBalance'], lambda data: data),
            'card_disposed_balance': lambda conn_data: (_is_float_updated, conn_data['cardDisposedBalance'], lambda data: data),
            'card_linked_account': lambda conn_data: (_is_string_updated, conn_data['cardLinkedAccount'], lambda data: data),
            'card_next_payment_date': lambda conn_data: (_is_string_updated, conn_data['cardNextPaymentDate'], lambda data: data),
            'card_status': lambda conn_data: (_is_string_updated, conn_data['cardStatus'], lambda data: data),
            'card_annual_interest': lambda conn_data: (_is_float_updated, conn_data['cardAnnualInterest'], lambda data: data),
            'card_tae': lambda conn_data: (_is_float_updated, conn_data['cardTae'], lambda data: data),
        }

        for key, function in account_data_map.items():
            should_be_updated, new_data, transformation = function(
                account_data)
            # use sudo to avoid rules check because we are only reading and the checks have been done before
            if should_be_updated(account_data['record'][key], new_data):
                data[key] = transformation(new_data)

        return data
    
    def _request_cashflow_historical(self):
        cashflows_by_account = {}
        accounts_by_bankifai_user = defaultdict(lambda: self.env['bankifai.account'])
        for account in self:
            accounts_by_bankifai_user[account.bankifai_connection_id.bankifai_user_id] |= account
        for bankifai_user_id, bankifai_account_ids in accounts_by_bankifai_user.items():
            _response, data = bankifai_user_id._get_request(
                "financialviewer/cashflow",
                params={
                    "accountIds": ",".join(map(str, bankifai_account_ids.mapped('account_indentification'))),
                },
            )
            cashflows_by_account.update(data)
        return cashflows_by_account
    
    def _request_cashflow_forecasts(self):
        cashflows_by_account = {}
        accounts_by_bankifai_user = defaultdict(lambda: self.env['bankifai.account'])
        for account in self:
            accounts_by_bankifai_user[account.bankifai_connection_id.bankifai_user_id] |= account
        for bankifai_user_id, bankifai_account_ids in accounts_by_bankifai_user.items():
            _response, data = bankifai_user_id._get_request(
                "financialviewer/cashflow/forecast",
                params={
                    "accountIds": ",".join(map(str, bankifai_account_ids.mapped('account_indentification'))),
                },
            )
            cashflows_by_account.update(data)
        return cashflows_by_account

    def _update_cashflow_historical(self):
        cashflows_to_create = []
        cashflows_by_accounts = self._request_cashflow_historical()
        for account in self:
            bankifai_cashflows_by_date = { bankifai_cashflow_id.date.strftime(DF): bankifai_cashflow_id for bankifai_cashflow_id in self.bankifai_cashflow_ids }
            for cashflow_data in cashflows_by_accounts.get(str(account.account_indentification), []):
                cashflow_data['has_historical'] = True
                cashflow_date = cashflow_data.get('cashflow_date')
                cashflow_data['record'] = bankifai_cashflows_by_date.get(cashflow_date, self.env['bankifai.cashflow'])
                if cashflow_data['record']:
                    cashflow_data['record'].sudo().write(self.env['bankifai.cashflow']._get_cashflow_data(cashflow_data))
                else:
                    cashflows_to_create.append(self.env['bankifai.cashflow']._get_cashflow_data(cashflow_data, {'bankifai_account_id': account.id}))

        self.env['bankifai.cashflow'].sudo().create(cashflows_to_create)

    def _update_cashflow_forecasts(self):
        cashflows_to_create = []
        cashflows_by_accounts = self._request_cashflow_forecasts()
        for account in self:
            bankifai_cashflows_by_date = { bankifai_cashflow_id.date.strftime(DF): bankifai_cashflow_id for bankifai_cashflow_id in self.bankifai_cashflow_ids }
            for cashflow_data in cashflows_by_accounts.get(str(account.account_indentification), []):
                cashflow_data['has_forecast'] = True
                cashflow_date = cashflow_data.get('date')
                cashflow_data['record'] = bankifai_cashflows_by_date.get(cashflow_date, self.env['bankifai.cashflow'])
                if cashflow_data['record']:
                    cashflow_data['record'].sudo().write(self.env['bankifai.cashflow']._get_cashflow_forecast_data(cashflow_data))
                else:
                    cashflows_to_create.append(self.env['bankifai.cashflow']._get_cashflow_forecast_data(cashflow_data, {'bankifai_account_id': account.id}))

        self.env['bankifai.cashflow'].sudo().create(cashflows_to_create)