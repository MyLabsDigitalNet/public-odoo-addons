# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement"

    def _update_balance_start_with_cashflow(self):
        bankifai_cashflows_by_date_and_account = self.journal_id.online_bank_statement_provider_id.bankifai_account_id._get_cashflow_by_date_and_account()
        for statement in self:
            bankifai_account_id = statement.journal_id.online_bank_statement_provider_id.bankifai_account_id
            if statement.date and bankifai_account_id:
                cashflow = bankifai_cashflows_by_date_and_account.get(
                    bankifai_account_id.id, {}).get((statement.date - relativedelta(days=1)).strftime(DF))
                if cashflow and cashflow.has_historical:
                    statement.balance_start = cashflow.cashflow_balance
        return True
