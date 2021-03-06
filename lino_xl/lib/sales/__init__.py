# Copyright 2014-2018 Rumma & Ko Ltd
# License: BSD (see file COPYING for details)

"""Adds functionality for handling sales.
See :doc:`/specs/sales`.


.. autosummary::
    :toctree:

    fixtures.std
    fixtures.demo_bookings

"""

from lino.api import ad
from django.utils.translation import ugettext_lazy as _


class Plugin(ad.Plugin):
    "See :class:`lino.core.plugin.Plugin`."

    verbose_name = _("Product invoices")

    needs_plugins = ['lino_xl.lib.products', 'lino_xl.lib.vat']

    def setup_reports_menu(self, site, user_type, m):
        mg = site.plugins.accounts
        # mg = site.plugins.vat
        m = m.add_menu(mg.app_label, mg.verbose_name)
        m.add_action('sales.DueInvoices')
        m.add_action('sales.PrintableInvoicesByJournal')

    def setup_config_menu(self, site, user_type, m):
        mg = site.plugins.vat
        m = m.add_menu(mg.app_label, mg.verbose_name)
        m.add_action('sales.PaperTypes')
       
    def setup_explorer_menu(self, site, user_type, m):
        mg = site.plugins.vat
        m = m.add_menu(mg.app_label, mg.verbose_name)
        # m = m.add_menu(self.app_label, self.verbose_name)
        m.add_action('sales.Invoices')
        m.add_action('sales.InvoiceItems')
