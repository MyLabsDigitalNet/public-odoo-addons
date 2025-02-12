===================================
Online Bank Statements: BankifAI
===================================

.. |badge1| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3
.. |badge2| image:: https://img.shields.io/badge/github-MyLabsDigitalNet%2Fpublic--odoo--addons-lightgray.png?logo=github
    :target: https://github.com/MyLabsDigitalNet/public-odoo-addons/tree/18.0/account_statement_import_online_bankifai
    :alt: MyLabsDigitalNet/public-odoo-addons


|badge1| |badge2|

This module provides online bank statements from `BankifAI <https://qsimov.ekodo.es/>`_.

**Table of contents**

.. contents::
   :local:

Configuration
=============

To configure online bank statements provider:

#. We recommend to install the module ``account_usability`` to enable the accounting Dashboard.
#. Go to *Invoicing/Accounting*
#. Click the button *BankifAI Synchronization* in a bank/card jorunal.
#. Follow the instructions to conencto your bank account.

or, to configure it manually:

#. Go to *Invoicing > Configuration > Bank Accounts*
#. Open bank account to configure and edit it
#. Set *Bank Feeds* to *Online*
#. Select *Bankifai* as online bank statements provider in
   *Online Bank Statements (OCA)* section
#. Save the bank account
#. Click on provider and configure provider-specific settings.

or, alternatively:

#. Go to *Invoicing > Overview*
#. Open settings of the corresponding journal account
#. Switch to *Bank Account* tab
#. Set *Bank Feeds* to *Online*
#. Select *Bankifai* as online bank statements provider in
   *Online Bank Statements (OCA)* section
#. Save the bank account
#. Click on provider and configure provider-specific settings.

To obtain *Client ID* and *Client Secret*:

#. Open `BankifAI <https://qsimov.ekodo.es/>`_ ang click *Buy Now*.

Check also ``account_bank_statement_import_online`` configuration instructions
for more information.

Usage
=====

To pull historical bank statements:

#. Go to *Invoicing > Configuration > Bank Accounts*
#. Select specific bank accounts
#. Launch *Actions > Online Bank Statements Pull Wizard*
#. Configure date interval and click *Pull*

If historical data is not needed, then just simply wait for the scheduled
activity "Pull Online Bank Statements" to be executed for getting new
transactions.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/MyLabsDigitalNet/public-odoo-addons/issues>`_.
In case of trouble, please check there if your issue has already been reported.
If you spotted it first, help us to smash it by providing a detailed and welcomed
`feedback <https://github.com/MyLabsDigitalNet/public-odoo-addons/issues/new?body=module:%20account_statement_import_online_bankifai%0Aversion:%2018.0%0A%0A**Steps%20to%20reproduce**%0A-%20...%0A%0A**Current%20behavior**%0A%0A**Expected%20behavior**>`_.

Do not contact contributors directly about support or help with technical issues.

Credits
=======

Authors
~~~~~~~

* `MyLabs Digital Net (EKODO) <https://mylabs.es/>`__:

  * Adrián Bernal