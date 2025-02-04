import logging
from odoo import models, api, fields, _
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    show_bankifai_button_in_dashboard = fields.Boolean(compute='_compute_show_bankifai_button_in_dashboard')
    show_bankifai_update_consent_in_dashboard = fields.Boolean(compute='_compute_show_bankifai_button_in_dashboard')
    show_bankifai_update_consent_error_in_dashboard = fields.Boolean(compute='_compute_show_bankifai_button_in_dashboard')
    expected_expiring_synchronization_date = fields.Date(related='online_bank_statement_provider_id.bankifai_connection_id.expected_expiring_synchronization_date')

    @api.depends()
    def _compute_show_bankifai_button_in_dashboard(self):
        for journal in self:
            show_button = False
            show_update_consent = False
            show_update_consent_error = False
            if journal.type == 'bank':
                if str2bool(self.env["ir.config_parameter"].sudo().get_param("account_statement_import_online_bankifai.show_easy_connection", 'True')) and (not journal.online_bank_statement_provider or journal.online_bank_statement_provider == 'dummy' or journal.bank_statements_source == 'undefined'):
                    show_button = True
                if journal.online_bank_statement_provider == 'bankifai' and journal.bank_statements_source == 'online':
                    if journal.bank_account_id and journal.online_bank_statement_provider_id.bankifai_connection_id and journal.online_bank_statement_provider_id.bankifai_user_id:
                        show_update_consent = True
                        if journal.online_bank_statement_provider_id.bankifai_connection_id.status_code == 'TOKEN_EXPIRED':
                            show_update_consent_error = True
                    else:
                        show_button = True

            journal.show_bankifai_button_in_dashboard = show_button
            journal.show_bankifai_update_consent_in_dashboard = show_update_consent
            journal.show_bankifai_update_consent_error_in_dashboard = show_update_consent_error

    
    
    def _get_action_create_bank_account(self):
        self.ensure_one()
        view_id = self.env.ref('account.setup_bank_account_wizard').id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create a Bank Account'),
            'res_model': 'account.setup.bank.manual.config',
            'target': 'new',
            'view_mode': 'form',
            'views': [[view_id, 'form']],
            'context': {'default_linked_journal_id': self.id, 'connecting_bank': True},
        }

    def action_connect_other_account(self):
        return self.env['res.company'].setting_init_bank_account_action()

    def action_select_bankifai_bank(self):
        if not self.bank_account_id:
            return self._get_action_create_bank_account()

        if not self.online_bank_statement_provider_id:
            self.write({
                'bank_statements_source': 'online',
                'online_bank_statement_provider': 'bankifai',
            })

        return self.online_bank_statement_provider_id.action_select_bankifai_bank()

    def _update_expected_expiring_synchronization_date(self):
        bank_sync_activity_type_id = self.env.ref(
            'account_statement_import_online_bankifai.bank_sync_activity_update_consent')
        account_journal_model_id = self.env['ir.model']._get_id('account.journal')

        new_activity_vals = []
        for journal in self:
            activity_ids = self.env['mail.activity'].search([
                ('res_id', '=', journal.id),
                ('res_model_id', '=', account_journal_model_id),
                ('activity_type_id', '=', bank_sync_activity_type_id.id),
            ])
            to_unlink_activity_ids = activity_ids.filtered(lambda activity: activity.date_deadline != journal.online_bank_statement_provider_id.bankifai_connection_id.expected_expiring_synchronization_date)
            to_maintain_activity_ids = activity_ids - to_unlink_activity_ids
            to_unlink_activity_ids.unlink()

            expected_expiring_synchronization_date = journal.online_bank_statement_provider_id.bankifai_connection_id.expected_expiring_synchronization_date
            if not to_maintain_activity_ids and expected_expiring_synchronization_date:
                new_activity_vals.append({
                    'res_id': journal.id,
                    'res_model_id': account_journal_model_id,
                    'date_deadline': expected_expiring_synchronization_date,
                    'summary': _("Bank Synchronization: Update your consent"),
                    'note': _("This bank connection is expected to expire on %s. Press the Update Credentials button a few days before to renew your consent.") % (expected_expiring_synchronization_date),
                    'activity_type_id': bank_sync_activity_type_id.id,
                    'user_id': journal.online_bank_statement_provider_id.bankifai_connection_id.create_uid.id,
                })
        self.env['mail.activity'].create(new_activity_vals)

    # OVERRIDED: Avoid errors, reconfigure instead
    def _update_providers(self):
        """Automatically create service.

        This method exists for compatibility reasons. The preferred method
        to create an online provider is directly through the menu,
        """
        OnlineBankStatementProvider = self.env["online.bank.statement.provider"]
        for journal in self.filtered("online_bank_statement_provider"):
            service = journal.online_bank_statement_provider
            if (
                journal.online_bank_statement_provider_id
                and service == journal.online_bank_statement_provider_id.service
            ):
                _logger.info(
                    "Journal %s already linked to service %s", journal.name, service
                )
                # Provider already exists.
                continue
            # Use existing or create new provider for service.
            provider = OnlineBankStatementProvider.search(
                [
                    ("journal_id", "=", journal.id),
                    # ("service", "=", service),
                ],
                limit=1,
            ) or OnlineBankStatementProvider.create(
                {
                    "journal_id": journal.id,
                    "service": service,
                }
            )

            if provider.service != service:
                provider.service = service

            journal.online_bank_statement_provider_id = provider
            _logger.info("Journal %s now linked to service %s", journal.name, service)