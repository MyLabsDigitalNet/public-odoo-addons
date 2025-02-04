from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError, ValidationError

class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    category_id = fields.Many2one(comodel_name='account.bank.statement.line.category', string="Category")