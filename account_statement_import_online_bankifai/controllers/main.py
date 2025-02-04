import werkzeug
import logging
import json
import time
from werkzeug.urls import url_encode

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class BankifAIController(http.Controller):

    @http.route("/dedomena/response", type="json", auth="public", csrf=False)
    def bankifai_response(self):
        _logger.info("Callback received with data: %s" %
                     json.dumps(request.httprequest.json))
        BankifAIConnection = request.env["bankifai.connection"].sudo()
        current_connection = BankifAIConnection.search(
            [
                ("connection_identification", "=",
                 request.httprequest.json["conId"]),
            ]
        )

        _logger.info(
            "Callback received for connection: %s - Updating it" % current_connection)
        current_connection._update_connection()
        return True
