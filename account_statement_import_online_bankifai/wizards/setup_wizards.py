from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class SetupBarBankConfigWizard(models.TransientModel):
    _inherit = 'account.setup.bank.manual.config'

    def validate(self):
        """ Called by the validation button of this wizard. Serves as an
        extension hook in account_bank_statement_import.
        """
        action = super(SetupBarBankConfigWizard, self).validate()
        if self.env.context.get('connecting_bank', False):
            return self.linked_journal_id.action_select_bankifai_bank()
        return action
