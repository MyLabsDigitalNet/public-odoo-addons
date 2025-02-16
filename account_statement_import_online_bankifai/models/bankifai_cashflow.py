import requests
import json
import base64
from werkzeug.urls import url_join
from dateutil.relativedelta import relativedelta

from odoo import fields, models, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, float_compare, float_is_zero


class BankifAIAccount(models.Model):
    _name = 'bankifai.cashflow'
    _description = "BankifAI Cashflow"
    _order = 'date desc'

    _sql_constraints = [
        (
            "cashflow_date_uniq",
            "unique(bankifai_account_id, cashflow_date)",
            "There must be only one cashflow per day per acount!",
        ),
    ]

    bankifai_account_id = fields.Many2one(
        comodel_name='bankifai.account', string='BankifAI Account', ondelete='cascade')
    date = fields.Date(string='Date', compute='_compute_date', store=True)
    cashflow_date = fields.Char(string='Cashflow Date')

    has_historical = fields.Boolean(string='Has historial data')
    cashflow_balance = fields.Monetary(string='Historical Cashflow Balance')
    cashflow_income = fields.Monetary(string='Historical Cashflow Income')
    cashflow_expense = fields.Monetary(string='Historical Cashflow Expense')

    has_forecast = fields.Boolean(string="Has forecasted data")
    balance = fields.Monetary(string='Forecasted Balance')
    balance_day_max = fields.Monetary(string='Forecasted Day Max Balance')
    balance_day_min = fields.Monetary(string='Forecasted Day Min Balance')
    balances_dayofweek_max = fields.Monetary(
        string='Forecasted Day of Week Max Balance')
    balances_dayofweek_min = fields.Monetary(
        string='Forecasted Day of Week Min Balance')
    expenses_day_max = fields.Monetary(string='Forecasted Day Max Expenses')
    expenses_day_min = fields.Monetary(string='Forecasted Day Min Expenses')
    expenses_dayofweek_max = fields.Monetary(
        string='Forecasted Day of Week Max Expenses')
    expenses_dayofweek_min = fields.Monetary(
        string='Forecasted Day of Week Min Expenses')
    incomes_day_max = fields.Monetary(string='Forecasted Day Max Incomes')
    incomes_day_min = fields.Monetary(string='Forecasted Day Min Incomes')
    incomes_dayofweek_max = fields.Monetary(
        string='Forecasted Day of Week Max Incomes')
    incomes_dayofweek_min = fields.Monetary(
        string='Forecasted Day of Week Min Incomes')
    pred05 = fields.Monetary(string='Forecasted Balance Interval 5%')
    pred95 = fields.Monetary(string='Forecasted Balance Interval 95%')

    currency_id = fields.Many2one(related='bankifai_account_id.currency_id')

    @api.depends('cashflow_date')
    def _compute_date(self):
        for cashflow in self:
            cashflow.date = fields.Datetime.to_datetime(cashflow.cashflow_date)

    def _get_cashflow_data(self, cashflow_data, custom_data={}):
        def _is_string_updated(old, new):
            return bool(new) and (old or '').lower() != new.lower()

        def _is_float_updated(old, new):
            if new is None:
                return False
            return float_compare(float(old), float(new), precision_digits=2)

        def _is_boolean_updated(old, new):
            if new is None:
                return False
            return new != old

        # returned tupple format (should_be_updated function, new_data, data transformation function)
        cashflow_data_map = {
            'cashflow_date': lambda conn_data: (_is_string_updated, conn_data['cashflow_date'], lambda data: data),
            'cashflow_balance': lambda conn_data: (_is_float_updated, conn_data['cashflow_balance'], lambda data: data),
            'cashflow_income': lambda conn_data: (_is_float_updated, conn_data['cashflow_income'], lambda data: data),
            'cashflow_expense': lambda conn_data: (_is_float_updated, conn_data['cashflow_expense'], lambda data: data),
            'has_historical': lambda conn_data: (_is_boolean_updated, conn_data['has_historical'], lambda data: data),
        }

        data = {}
        for key, function in cashflow_data_map.items():
            should_be_updated, new_data, transformation = function(
                cashflow_data)
            # use sudo to avoid rules check because we are only reading and the checks have been done before
            if should_be_updated(cashflow_data['record'][key], new_data):
                data[key] = transformation(new_data)

        data.update(custom_data)
        return data

    def _get_cashflow_forecast_data(self, cashflow_data, data={}):
        def _is_string_updated(old, new):
            return bool(new) and (old or '').lower() != new.lower()

        def _is_float_updated(old, new):
            if new is None:
                return False
            return float_compare(float(old), float(new), precision_digits=2)

        def _is_boolean_updated(old, new):
            if new is None:
                return False
            return new != old

        # returned tupple format (should_be_updated function, new_data, data transformation function)
        cashflow_data_map = {
            'cashflow_date': lambda conn_data: (_is_string_updated, conn_data['date'], lambda data: data),
            'balance': lambda conn_data: (_is_float_updated, conn_data['balance'], lambda data: data),
            'balance_day_max': lambda conn_data: (_is_float_updated, conn_data['balance_day_max'], lambda data: data),
            'balance_day_min': lambda conn_data: (_is_float_updated, conn_data['balance_day_min'], lambda data: data),
            'balances_dayofweek_max': lambda conn_data: (_is_float_updated, conn_data['balances_dayofweek_max'], lambda data: data),
            'balances_dayofweek_min': lambda conn_data: (_is_float_updated, conn_data['balances_dayofweek_min'], lambda data: data),
            'expenses_day_max': lambda conn_data: (_is_float_updated, conn_data['expenses_day_max'], lambda data: data),
            'expenses_day_min': lambda conn_data: (_is_float_updated, conn_data['expenses_day_min'], lambda data: data),
            'expenses_dayofweek_max': lambda conn_data: (_is_float_updated, conn_data['expenses_dayofweek_max'], lambda data: data),
            'expenses_dayofweek_min': lambda conn_data: (_is_float_updated, conn_data['expenses_dayofweek_min'], lambda data: data),
            'incomes_day_max': lambda conn_data: (_is_float_updated, conn_data['incomes_day_max'], lambda data: data),
            'incomes_day_min': lambda conn_data: (_is_float_updated, conn_data['incomes_day_min'], lambda data: data),
            'incomes_dayofweek_max': lambda conn_data: (_is_float_updated, conn_data['incomes_dayofweek_max'], lambda data: data),
            'incomes_dayofweek_min': lambda conn_data: (_is_float_updated, conn_data['incomes_dayofweek_min'], lambda data: data),
            'pred05': lambda conn_data: (_is_float_updated, conn_data['pred05'], lambda data: data),
            'pred95': lambda conn_data: (_is_float_updated, conn_data['pred95'], lambda data: data),
            'has_forecast': lambda conn_data: (_is_boolean_updated, conn_data['has_forecast'], lambda data: data),
        }

        for key, function in cashflow_data_map.items():
            should_be_updated, new_data, transformation = function(
                cashflow_data)
            # use sudo to avoid rules check because we are only reading and the checks have been done before
            if should_be_updated(cashflow_data['record'][key], new_data):
                data[key] = transformation(new_data)

        return data

    def _get_cashflow_by_date(self):
        return {bankifai_cashflow_id.date.strftime(DF): bankifai_cashflow_id for bankifai_cashflow_id in self}
