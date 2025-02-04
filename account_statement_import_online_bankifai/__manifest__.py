{
    "name": "Online Bank Statements: BankifAI",
    "version": "16.0.1.0.0",
    "category": "Account",
    "author": "Adrián Bernal Bermejo, Ekodo (MyLabs Digital Net SL)",
    "website": "https://qsimov.ekodo.es",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "base",
        "web",
        "account_statement_base",
        "account_statement_import_online",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/online_bank_statement_provider_views.xml",
        "views/bankifai_user_views.xml",
        "views/bankifai_connection_views.xml",
        "views/bankifai_account_views.xml",
        "views/bankifai_cashflow_views.xml",
        "views/account_journal_dashboard_views.xml",
        "views/account_bank_statement_line_views.xml",
        "wizards/bankifai_connection_existing_wizard_views.xml",
        "wizards/bankifai_user_create_wizard_views.xml",
        "data/bankifai_account.xml",
        "data/config_parameter.xml",
        "data/mail_activity_type_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_statement_import_online_bankifai/static/src/js/*",
        ],
    },
    "images": [
        "static/description/icon.png",
        "static/description/main_screenshot.png",
],
}
