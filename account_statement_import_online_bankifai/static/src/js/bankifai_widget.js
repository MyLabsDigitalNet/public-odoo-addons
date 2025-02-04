/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"
import { _t } from 'web.core';

const { Component } = owl;
const { onMounted, onWillStart } = owl.hooks;

class BankifAIWidget extends Component {
    setup(env) {
        this.orm = useService('orm');
        this.dialogService = useService('dialog');
        this.actionService = useService("action");
        this.online_bank_statement_provider = { id: this.props.action.context.active_online_bank_statement_provider_id }
        this.bankifai_connection = { id: false, status_code: false }

        this.maxRefreshTries = 2;
        this.refreshTries = 0;
        this._addBankifAIEventListeners();

        onWillStart(async () => {
            await this._loadData()
        });

        onMounted(() => {
            this.ddmIframe = document.getElementById('ddm-iframe');

            this._iframeTokenPost();
            if (this.props.action.context.update_consent || this.bankifai_connection.status_code == 'TOKEN_EXPIRED') {
                this._iframeRefreshConnection();
            }
            this._show_iframe();
        });
    }

    _show_iframe() {
        this.ddmIframe.style.display = "block";
    }

    _hidde_iframe() {
        this.ddmIframe.style.display = "none";
    }

    _close_iframe_dialog() {
        this._hidde_iframe();
        this.__owl__.parent.__owl__.parent.close();
    }

    async _loadData() {
        var online_bank_statement_providers = await this.orm.read('online.bank.statement.provider', [this.online_bank_statement_provider.id], ['id', 'bankifai_connection_id', 'bankifai_callback_url']);
        this.online_bank_statement_provider = online_bank_statement_providers[0]
        if (this.online_bank_statement_provider.bankifai_connection_id) {
            var bankifai_connections = await this.orm.read('bankifai.connection', [this.online_bank_statement_provider.bankifai_connection_id[0]], ['id', 'connection_identification', 'status_code']);
            this.bankifai_connection = bankifai_connections[0]
            this.bankifai_connection.status_code = 'TOKEN_EXPIRED'
        } else {
            this.bankifai_connection = { id: false, status_code: false }
        }
    }

    _addBankifAIEventListeners() {
        var self = this;
        window.removeEventListener("message", window.bankifaiEventListener);
        window.bankifaiEventListener = async function (event) {
            // TODO: take url from ir.parameter
            if (event.origin !== "https://aggregator-ui-6gzihy27ea-ew.a.run.app")
                return;
            if (event.data.type === "ddm-invalid-token") {
                if (self.refreshTries < self.maxRefreshTries) {
                    self.refreshTries++;
                    await self._iframeTokenPost(true);
                } else {
                    self._show_error_dialog();
                }
            }
            if (event.data.type === "ddm-success-aggregation") {
                if (event.data.connectionId) {
                    self.orm.call('online.bank.statement.provider', 'bankifai_susccess_agregation', [self.online_bank_statement_provider.id], { bankifai_connection_identification: event.data.connectionId });
                    self._show_success_dialog()
                }
            }
            if (event.data.type === "ddm-limit-exceeded") {
                self._show_limit_exceeded_dialog()
            }

        };

        window.addEventListener("message", window.bankifaiEventListener);
    }

    _show_success_dialog() {
        this.closeDialog = this.dialogService.add(ConfirmationDialog,
            {
                title: _t("Success Connection"),
                body: _t("The bank has been connected"),
            },
            {
                onClose: () => {
                    this._close_iframe_dialog();
                },
            }
        );

    }
    _show_limit_exceeded_dialog() {
        this.closeDialog = this.dialogService.add(ConfirmationDialog,
            {
                title: _t("Límite de conexiones alcanzado"),
                body: _t("Límite de conexiones alcanzado"),
            },
            {
                onClose: () => {
                    this._close_iframe_dialog();
                },
            }
        );
    }

    _show_error_dialog() {
        this.closeDialog = this.dialogService.add(ConfirmationDialog,
            {
                title: _t("Error de conexión"),
                body: _t("Error"),
            },
            {
                onClose: () => {
                    this._close_iframe_dialog();
                },
            }
        );
    }

    async _iframeTokenPost(force_refresh = false) {
        var token = await this._getBankifAIToken(force_refresh = force_refresh);
        this.ddmIframe.contentWindow.postMessage({
            type: "ddm-init",
            token: "Bearer " + token,
            callbackUrl: this.online_bank_statement_provider.bankifai_callback_url // Add Odoo URL
        }, "*");
        this.ddmIframe.style.display = "block";
    }

    async _getBankifAIToken(force_refresh = false) {
        var token = await this.orm.call('online.bank.statement.provider', 'bankifai_get_token', [this.online_bank_statement_provider.id, force_refresh = force_refresh]);
        return token;
    }

    async _iframeRefreshConnection(force_refresh = false) {
        this.ddmIframe.contentWindow.postMessage({
            type: "ddm-refresh-connection",
            connectionId: this.bankifai_connection.connection_identification,
        }, "*");
    }
}

BankifAIWidget.template = "ekodo_bankifai.BankifAIWidget";

registry.category('actions').add('bankifai_widget', BankifAIWidget);

