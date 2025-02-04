from odoo import fields, models


class BankifAIConnectionExistingWizard(models.TransientModel):
    _name = "bankifai.connection.existing.wizard"
    _description = "Wizard for reusing existing BankifAI connection"
    _rec_name = "online_bank_statement_provider_id"

    online_bank_statement_provider_id = fields.Many2one(
        comodel_name="online.bank.statement.provider", string="Online Bank Statement Provider")
    bankifai_connection_id = fields.Many2one(
        comodel_name="bankifai.connection", required=True, string="BankifAI Connection")
    available_bankifai_connection_ids = fields.Many2many(
        comodel_name="bankifai.connection", string="Availble BankifAI Connections")

    def link_existing(self):
        self.online_bank_statement_provider_id._set_bankifai_connection_id(
            self.bankifai_connection_id, dry=True)

    def new_link(self):
        return self.online_bank_statement_provider_id.action_open_bankifai_widget()
