import logging
import requests
import json
import base64
from datetime import datetime
from operator import itemgetter
from collections import defaultdict
from werkzeug.urls import url_join
from dateutil.relativedelta import relativedelta

from odoo import fields, models, api, _
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class BankifAIConnection(models.Model):
    _name = 'bankifai.connection'
    _inherit = ["mail.thread"]
    _description = "BankifAI Connection"

    _sql_constraints = [
        (
            "valid_interval_number",
            "CHECK(interval_number > 0)",
            "Scheduled update interval must be greater than zero!",
        ),
    ]

    bankifai_user_id = fields.Many2one(comodel_name='bankifai.user', string='BankifAI User', ondelete='cascade')
    bankifai_account_ids = fields.One2many(comodel_name='bankifai.account', inverse_name='bankifai_connection_id', string="Aggregated Accounts", readonly=True)
    connection_identification = fields.Integer(string='Connection ID', readonly=True)
    team = fields.Integer(string='Team ID', readonly=True)
    operation_identification = fields.Char(string='Operation ID', readonly=True)
    last_session_identification = fields.Char(string='Last Session ID', readonly=True)
    last_refresh_date = fields.Char(string='Last Refresh Date', readonly=True)
    token_date = fields.Char(string='Last Update Token Date', readonly=True)
    entity_code = fields.Char(string='Entity Code', readonly=True)
    entity_name = fields.Char(string='Entity Name', readonly=True)
    #  ERROR, PENDING, UPDATING, OK
    status_code = fields.Char(string='Status Code', readonly=True)
    last_error_code = fields.Integer(string='Last Error Code', readonly=True)
    last_error_message = fields.Char(string='Last Error Message', readonly=True)
    token = fields.Char(string='Token', readonly=True)
    name = fields.Char(string='Name', readonly=True)
    company_name = fields.Char(string='Company', readonly=True)
    callback_url = fields.Char(string='Callback URL', readonly=True)
    online_bank_statement_provider_ids = fields.One2many(comodel_name='online.bank.statement.provider', inverse_name='bankifai_connection_id', string="Online Bank Statement Providers")
    is_active = fields.Boolean(string="Is active", compute='_compute_is_active', store=True)
    expected_expiring_synchronization_date = fields.Date(string="Consent Expire Date", help="Date when the consent for this connection expires", compute='_compute_expected_expiring_synchronization_date')

    # Computed from bankifai fields
    last_refresh_datetime = fields.Datetime(
        string='Last Refresh Datetime', compute='_compute_last_refresh_datetime')
    token_datetime = fields.Datetime(
        string='Last Update Token Datetime', compute='_compute_token_datetime')

    @api.depends('last_refresh_date')
    def _compute_last_refresh_datetime(self):
        for connection in self:
            connection.last_refresh_datetime = fields.Datetime.to_datetime(connection.last_refresh_date)

    @api.depends('token_date')
    def _compute_token_datetime(self):
        for connection in self:
            connection.token_datetime = fields.Datetime.to_datetime(connection.token_date)

    @api.depends('token_datetime')
    def _compute_expected_expiring_synchronization_date(self):
        for connection in self:
            connection.expected_expiring_synchronization_date = connection.token_datetime + relativedelta(days=int(self.env['ir.config_parameter'].sudo().get_param('account_statement_import_online_bankifai.days_consent_expected_duration', 90)))

    # CONNECTION REFRESH FIELDS
    interval_type = fields.Selection(
        selection=[
            ("minutes", "Minute(s)"),
            ("hours", "Hour(s)"),
            ("days", "Day(s)"),
            ("weeks", "Week(s)"),
        ],
        default="hours",
        required=True,
    )
    interval_number = fields.Integer(
        string="Scheduled update interval",
        default=6,
        required=True,
    )
    update_schedule = fields.Char(
        compute="_compute_update_schedule",
    )
    last_successful_run = fields.Datetime(
        string="Last successful refresh", readonly=True)
    next_run = fields.Datetime(string="Next scheduled refresh", default=fields.Datetime.now, required=True)

    @api.depends('online_bank_statement_provider_ids.active')
    def _compute_is_active(self):
        for connection in self:
            connection.is_active = any(
                connection.online_bank_statement_provider_ids.mapped('active'))

    @api.depends("is_active", "interval_type", "interval_number")
    def _compute_update_schedule(self):
        for connection in self:
            if not connection.is_active:
                connection.update_schedule = _("Inactive")
                continue

            connection.update_schedule = _("%(number)s %(type)s") % {
                "number": connection.interval_number,
                "type": list(
                    filter(
                        lambda x: x[0] == connection.interval_type,
                        self._fields["interval_type"].selection,
                    )
                )[0][1],
            }

    def _get_next_run_period(self):
        self.ensure_one()
        if self.interval_type == "minutes":
            return relativedelta(minutes=self.interval_number)
        elif self.interval_type == "hours":
            return relativedelta(hours=self.interval_number)
        elif self.interval_type == "days":
            return relativedelta(days=self.interval_number)
        elif self.interval_type == "weeks":
            return relativedelta(weeks=self.interval_number)
        
    def _can_be_refreshed_domain(self):
        return [("is_active", "=", True), ("next_run", "<=", fields.Datetime.now()), ('status_code', 'in', ['OK', 'ERROR'])]

    @api.model
    def _scheduled_refresh(self):
        _logger.info(_("Scheduled refresh of online bank connections..."))
        self.env['bankifai.user'].search([])._update_connections()
        connections = self.search(self._can_be_refreshed_domain())
        if connections:
            _logger.info(
                _("Refreshing bankifai connections: %(connection_names)s"),
                dict(connection_names=", ".join(connections.mapped("name"))),
            )
            for connection in connections.with_context(tracking_disable=True):
                connection._adjust_schedule()
                connection._refresh_connection()
                connection._schedule_next_run()
        _logger.info(
            _("Scheduled refresh of online bank connections complete."))

    def _schedule_next_run(self):
        self.ensure_one()
        self.last_successful_run = self.next_run
        self.next_run += self._get_next_run_period()

    def _adjust_schedule(self):
        """Make sure next_run is current.

        Current means adding one more period would put if after the
        current moment. This will be done at the end of the run.
        The net effect of this method and the adjustment after the run
        will be for the next_run to be in the future.
        """
        self.ensure_one()
        delta = self._get_next_run_period()
        now = fields.Datetime.now()
        next_run = self.next_run + \
            delta if self.next_run and self.next_run > self.last_refresh_datetime else self.last_refresh_datetime + delta
        while next_run < now:
            self.next_run = next_run
            next_run = self.next_run + delta

    @api.model
    def _get_connection_data(self, connection_data, data={}):
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

        # returned tupple format (should_be_updated function, new_data, data transformation function)
        connection_data_map = {
            'connection_identification': lambda conn_data: (_is_integer_updated, conn_data['conId'], lambda data: data),
            'team': lambda conn_data: (_is_integer_updated, conn_data['teamId'], lambda data: data),
            'operation_identification': lambda conn_data: (_is_string_updated, conn_data['conOperationId'], lambda data: data),
            'last_session_identification': lambda conn_data: (_is_string_updated, conn_data['conLastSessionId'], lambda data: data),
            'last_refresh_date': lambda conn_data: (_is_string_updated, conn_data['conLastRefreshDate'], lambda data: data),
            'token_date': lambda conn_data: (_is_string_updated, conn_data['conTokenDate'], lambda data: data),
            'entity_code': lambda conn_data: (_is_string_updated, conn_data['conEntityCode'], lambda data: data),
            'entity_name': lambda conn_data: (_is_string_updated, conn_data['conEntityName'], lambda data: data),
            'status_code': lambda conn_data: (_is_string_updated, conn_data['conStatus'], lambda data: data),
            'token': lambda conn_data: (_is_string_updated, conn_data['conToken'], lambda data: data),
            'name': lambda conn_data: (_is_string_updated, conn_data['conName'], lambda data: data),
            'last_error_code': lambda conn_data: (lambda old, new: (bool(old) and not bool(new)) or _is_integer_updated(old, new), conn_data['lastError']['errorCode'] if conn_data.get('lastError') else None, lambda data: data),
            'last_error_message': lambda conn_data: (lambda old, new: (bool(old) and not bool(new)) or _is_string_updated(old, new), conn_data['lastError']['errorMessage'] if conn_data.get('lastError') else None, lambda data: data),
            'company_name': lambda conn_data: (_is_string_updated, conn_data['conCompanyName'], lambda data: data),
            'callback_url': lambda conn_data: (_is_string_updated, conn_data['conCallbackUrl'], lambda data: data),
        }

        for key, function in connection_data_map.items():
            should_be_updated, new_data, transformation = function(
                connection_data)
            if should_be_updated(connection_data['record'][key], new_data):
                data[key] = transformation(new_data)

        return data

    def _request_connection(self):
        self.ensure_one()
        _response, data = self.bankifai_user_id._get_request(
            f"financialviewer/connection/{self.connection_identification}"
        )
        data['record'] = self
        return data

    def _refresh_connection(self):
        for connection in self:
            _response, data = self.bankifai_user_id._get_request(
                f"financialviewer/connection/{self.connection_identification}/refresh",
                request_type='put',
            )
            data['record'] = connection
            connection_data = connection._get_connection_data(data)
            connection.write(connection_data)

    def _update_connection(self):
        for connection in self:
            connection_data = connection._get_connection_data(
                connection._request_connection())
            connection.write(connection_data)

    def _request_accounts(self):
        accounts_by_connection = defaultdict(list)
        for connection in self:
            if connection.connection_identification not in accounts_by_connection.keys():
                _response, data = connection.bankifai_user_id._get_request(
                    "financialviewer/account"
                )
                for account in data:
                    accounts_by_connection[account.get('conId', 0)].append(account)
        return accounts_by_connection

    def _update_accounts(self):
        accounts_to_create = []
        accounts_to_unlink = self.env['bankifai.account']
        accounts_by_connection = self._request_accounts()
        for connection in self:
            bankifai_accounts_by_indentification = {
                bankifai_account_id.account_indentification: bankifai_account_id for bankifai_account_id in self.bankifai_account_ids}
            account_data_identifications = set()
            for account_data in accounts_by_connection.get(connection.connection_identification, []):
                account_identification = account_data.get('accountId', 0)
                account_data['record'] = bankifai_accounts_by_indentification.get(
                    account_identification, self.env['bankifai.account'])
                account_data_identifications.add(account_identification)
                if account_data['record']:
                    account_data['record'].sudo().write(
                        self.env['bankifai.account']._get_account_data(account_data))
                else:
                    accounts_to_create.append(self.env['bankifai.account']._get_account_data(
                        account_data, {'bankifai_connection_id': connection.id}))

            accounts_to_unlink |= self.bankifai_account_ids.filtered(
                lambda bankifai_account_id: bankifai_account_id.account_indentification not in account_data_identifications)
        accounts_to_unlink.sudo().unlink()
        self.env['bankifai.account'].sudo().create(accounts_to_create)
        self._finish_connection()

    def _update_cashflow_historical(self):
        self.bankifai_account_ids._update_cashflow_historical()

    def _update_cashflow_forecasts(self):
        self.bankifai_account_ids._update_cashflow_forecasts()

    def _get_matched_bankifai_account_ids(self, account_number):
        bankifai_account_ids = self.bankifai_account_ids.filtered(lambda bankifai_account: bankifai_account._check_account_and_card_number(account_number))
        return bankifai_account_ids

    def action_delete_connection(self):
        for connection in self:
            _response, data = connection.bankifai_user_id._get_request(
                f"financialviewer/connection/{connection.connection_identification}",
                request_type='delete',
            )
        self.bankifai_user_id._update_connections()

    def unlink(self):
        self.online_bank_statement_provider_ids.action_disconnect()
        super(BankifAIConnection, self).unlink()

    def _finish_connection(self, dry=False):
        """Once the requisiton to the bank institution has been made, and this is called
        from the controller assigned to the redirect URL, we check that the IBAN account
        of the linked journal is included in the accessible bank accounts, and if so,
        we set the rest of the needed data.

        A message in the chatter is logged both for sucessful or failed operation (this
        last one only if not in dry mode).

        :param: dry: If true, this is called as previous step before starting the whole
          process, so no fail message is logged in chatter in this case.
        """
        found_accounts = False

        # Avoid recursions
        if self.env.context.get('finishing_bankifai_connection', False):
            return

        self = self.with_context(finishing_bankifai_connection=True)

        for connection in self.filtered(lambda connection: connection.status_code == ('OK') and connection.online_bank_statement_provider_ids.filtered(lambda provider: not provider.bankifai_account_id)):
            connection._update_accounts()

            for online_bank_statement_provider_id in connection.online_bank_statement_provider_ids.filtered(lambda provider: not provider.bankifai_account_id):
                bankifai_account_id = fields.first(connection._get_matched_bankifai_account_ids(
                    online_bank_statement_provider_id.account_number))
                if bankifai_account_id:
                    found_accounts = True
                    online_bank_statement_provider_id.write(
                        {
                            'bankifai_account_id': bankifai_account_id.id,
                        }
                    )
                    online_bank_statement_provider_id.sudo().message_post(
                        body=_(
                            "Your account number %(iban_number)s is successfully attached.")
                        % {"iban_number": online_bank_statement_provider_id.journal_id.bank_account_id.display_name}
                    )

                elif not dry:
                    # _response, data = connection.bankifai_user_id._get_request(
                    #     f"financialviewer/connection/{connection.bankifai_connectionId}",
                    #     request_type='delete',
                    # )
                    online_bank_statement_provider_id.sudo().write(
                        {
                            'bankifai_account_id': False,
                            'bankifai_connection_id': False,
                        }
                    )
                    online_bank_statement_provider_id.sudo().message_post(
                        body=_(
                            "Your account number %(iban_number)s it's not in the IBAN "
                            "account numbers found %(accounts_iban)s, please check"
                        )
                        % {
                            "iban_number": online_bank_statement_provider_id.journal_id.bank_account_id.display_name,
                            "accounts_iban": " / ".join(connection.bankifai_account_ids.mapped('account_number')),
                        }
                    )
        return found_accounts

    def write(self, values):
        update_function_dict = defaultdict(
            lambda: self.env['bankifai.connection'])
        if 'token_date' in values:
            update_function_dict['_update_expected_expiring_synchronization_date'] |= self
        if 'status_code' in values:
            for connection in self:
                if connection.status_code == 'PENDING' and values['status_code'] == 'OK':
                    update_function_dict['_finish_connection'] |= connection
                elif connection.status_code == 'TOKEN_EXPIRED' and values['status_code'] in ['OK', 'UPDATING']:
                    update_function_dict['_update_expected_expiring_synchronization_date'] |= connection
                elif connection.status_code == 'UPDATING' and values['status_code'] == 'OK':
                    update_function_dict['_finish_connection'] |= connection
                    update_function_dict['_update_cashflow_historical'] |= connection
                    update_function_dict['_update_cashflow_forecasts'] |= connection
                elif values['status_code'] == 'ERROR':
                    pass  # try again
                elif values['status_code'] == 'TOKEN_EXPIRED':
                    pass  # reauthorize
        super(BankifAIConnection, self).write(values)

        for function, connections in update_function_dict.items():
            getattr(connections, function)()

    def _update_expected_expiring_synchronization_date(self):
        self.online_bank_statement_provider_ids.journal_id._update_expected_expiring_synchronization_date()

    def action_open_record(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'account_statement_import_online_bankifai.bankifai_connection_action')
        action['res_id'] = self.id
        action['views'] = [(self.env.ref(
            'account_statement_import_online_bankifai.bankifai_connection_view_form').id, 'form')]
        return action
