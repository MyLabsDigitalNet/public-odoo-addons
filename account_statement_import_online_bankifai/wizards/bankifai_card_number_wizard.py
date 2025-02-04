# Copyright 2024 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, _, Command
from odoo.exceptions import ValidationError

class BankifAIUserCreateWizard(models.TransientModel):
    _name = "bankifai.card.number.wizard"
    _description = "Wizard for intorudcing the card number for BankifAI"
    _rec_name = "journal_id"

    journal_id = fields.Many2one(comodel_name='account.journal', string="Journal")
    card_number = fields.Char(string="Card Number")

    def confirm(self):
        if not self.card_number:
            raise ValidationError(_("You must introduce a card number"))
        self.journal_id.write({'card_number': self.card_number})
        return self.journal_id.action_select_bankifai_bank()