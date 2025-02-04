import requests
import json
import base64
from operator import itemgetter
from werkzeug.urls import url_join
from dateutil.relativedelta import relativedelta

from odoo import fields, models, api, _

DEDOMENA_ENDPOINT = "https://dedomena-backend-852411909563.europe-west6.run.app"

REQUESTS_TIMEOUT=60


class BankifAIUser(models.Model):
    _name = 'bankifai.user'
    _inherit = ["mail.thread"]
    _description = "BankifAI User"

    name = fields.Char(string='Name', required=True)
    clientId = fields.Char(string='Client ID', required=True)
    clientSecret = fields.Char(string='Client Secret', required=True)
    access_token = fields.Char(string='Access Token', readonly=True)
    token_expiration = fields.Datetime(string='Token Expiration', readonly=True)
    bankifai_connection_ids = fields.One2many(comodel_name='bankifai.connection', inverse_name='bankifai_user_id', string='BankifAI Connections')

    online_bank_statement_provider_ids = fields.One2many(comodel_name='online.bank.statement.provider', inverse_name='bankifai_user_id', string="Online Bank Statement Providers")

    def _get_headers(self, basic=False):
        """Generic method for providing the needed request headers."""
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
        }
        if not basic:
            authorization = f"Bearer {self._get_token()}"
        else:
            authorization = "Basic " + \
                base64.b64encode(f"{self.clientId}:{self.clientSecret}".encode(
                    'utf-8')).decode('utf-8')

        headers['Authorization'] = authorization
        return headers

    def _get_request(
        self, endpoint, request_type="get", params=None, data=None, basic_auth=False
    ):
        content = {}
        url = url_join(DEDOMENA_ENDPOINT, endpoint)
        response = getattr(requests, request_type)(
            url,
            data=data,
            params=params,
            headers=self._get_headers(basic=basic_auth),
            timeout=REQUESTS_TIMEOUT,
        )
        if response.status_code in [200, 201]:
            content = json.loads(response.text)
        return response, content

    def _get_token(self, force_refresh=False):
        """Resolve and return the corresponding BankifAI token for doing the requests."""
        self.ensure_one()
        now = fields.Datetime.now()
        if force_refresh or not self.access_token or now > self.token_expiration:
            response, data = self._get_request('user/token', basic_auth=True)
            expiration_date = now + \
                relativedelta(seconds=data.get("expiresIn", 0))
            vals = {
                "access_token": data.get("accessToken", False),
                "token_expiration": expiration_date,
            }
            self.sudo().write(vals)
        return self.access_token

    def _request_connections(self):
        self.ensure_one()
        _response, data = self._get_request(
            f"financialviewer/connection"
        )
        return data

    def _update_connections(self):
        connections_to_create = []
        connections_to_unlink = self.env['bankifai.connection']
        for user in self:
            connections_data = user._request_connections()
            bankifai_connections_by_indentification = { bankifai_connection_id.connection_identification: bankifai_connection_id for bankifai_connection_id in user.bankifai_connection_ids }
            connections_data_identifications = set()
            for connection_data in connections_data:
                connection_identification = connection_data.get('conId', 0)
                connection_data['record'] = bankifai_connections_by_indentification.get(
                    connection_identification, self.env['bankifai.connection'])
                connections_data_identifications.add(connection_identification)
                if connection_data['record']:
                    connection_data['record'].sudo().write(self.env['bankifai.connection']._get_connection_data(connection_data))
                else:
                    connections_to_create.append(self.env['bankifai.connection']._get_connection_data(
                        connection_data, {'bankifai_user_id': user.id}))

            connections_to_unlink |= user.bankifai_connection_ids.filtered(
                lambda bankifai_connection_id: bankifai_connection_id.connection_identification not in connections_data_identifications)
        connections_to_unlink.sudo().unlink()
        self.env['bankifai.connection'].sudo().create(connections_to_create)
        self.bankifai_connection_ids._finish_connection()

    def write(self, vals):
        if 'clientId' in vals:
            vals['access_token'] = False
        super(BankifAIUser, self).write(vals)
