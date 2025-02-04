# -*- coding: utf-8 -*-
from random import randint

from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountBankStatementLineCategory(models.Model):
    _name = "account.bank.statement.line.category"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(string="Name", translate=True)
    color = fields.Integer(string='Color', default=_get_default_color)
    code = fields.Char(string="Code")
    parent_id = fields.Many2one(
        comodel_name='account.bank.statement.line.category', string="Parent Category")
    bankifai_indentification = fields.Integer(string="BankifAI ID")
