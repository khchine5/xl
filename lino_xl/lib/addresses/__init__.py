# Copyright 2014-2017 Luc Saffre
#
# License: BSD (see file COPYING for details)

"""Adds functionality and models to handle multiple addresses per
:class:`lino_xl.lib.contacts.models.Partner`. When this module is
installed, your application usually has a "Manage addresses" button
per partner.

.. autosummary::
   :toctree:

    choicelists
    mixins
    models
    fixtures.demo2

Some unit test cases are
:mod:`lino.projects.min2.tests.test_addresses`.

"""

from lino.api import ad, _


class Plugin(ad.Plugin):
    "See :class:`lino.core.Plugin`."
    verbose_name = _("Addresses")
    partner_model = 'contacts.Partner'

    def on_site_startup(self, site):
        super(Plugin, self).on_site_startup(site)
        if self.partner_model is None:
            return
        from lino_xl.lib.addresses.mixins import AddressOwner
        self.partner_model = site.models.resolve(self.partner_model)
        
        # TODO: raise an exception if the specified model does not
        # implement AddressOwner. Currently it causes failures in book
        
        # if not issubclass(self.partner_model, AddressOwner):
        #     raise Exception("partner_model is not an AddressOwner")
        
    def setup_explorer_menu(self, site, user_type, m):
        # mg = self.get_menu_group()
        mg = site.plugins.contacts
        m = m.add_menu(mg.app_label, mg.verbose_name)
        m.add_action('addresses.AddressTypes')
        m.add_action('addresses.Addresses')

