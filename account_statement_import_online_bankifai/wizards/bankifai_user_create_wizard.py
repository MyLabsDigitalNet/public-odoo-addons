from odoo import fields, models, _, Command
from odoo.exceptions import ValidationError

class BankifAIUserCreateWizard(models.TransientModel):
    _name = "bankifai.user.create.wizard"
    _description = "Wizard for reusing existing BankifAI user or create new one"
    _rec_name = "online_bank_statement_provider_id"

    online_bank_statement_provider_id = fields.Many2one(
        comodel_name="online.bank.statement.provider", string="Online Bank Statement Provider")
    bankifai_user_id = fields.Many2one(
        comodel_name="bankifai.user", string="BankifAI User")
    name = fields.Char(string='Name')
    clientId = fields.Char(string='Client ID')
    clientSecret = fields.Char(string='Client Secret')


    def link_existing_user(self):
        if not self.bankifai_user_id:
            raise ValidationError(_('Please select an existing user.'))

        self.online_bank_statement_provider_id.bankifai_user_id = self.bankifai_user_id
        return self.online_bank_statement_provider_id.action_select_bankifai_bank()

    def create_user(self):
        if not self.name or not self.clientId or not self.clientSecret:
            raise ValidationError(_('Please fill all the fields.'))

        existing_bankifai_user_id = self.env['bankifai.user'].search([('clientId', '=', self.clientId)])
        if existing_bankifai_user_id:
            raise ValidationError(_('The user %s has the same clientId. Please link this user or change the clientId.') % existing_bankifai_user_id.name)

        self.online_bank_statement_provider_id.bankifai_user_id = self.env['bankifai.user'].create({
            'name': self.name,
            'clientId': self.clientId,
            'clientSecret': self.clientSecret,
        })

        return self.online_bank_statement_provider_id.action_select_bankifai_bank()
