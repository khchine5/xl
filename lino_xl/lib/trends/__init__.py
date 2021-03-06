# Copyright 2017 Luc Saffre
#
# License: BSD (see file COPYING for details)

"""
Adds the concept of trends.

"""

from lino import ad

from django.utils.translation import ugettext_lazy as _


class Plugin(ad.Plugin):
    "See :class:`lino.core.plugins.Plugin`."
    verbose_name = _("Trends")
    subject_model = None

    def on_site_startup(self, site):
        self.subject_model = site.models.resolve(self.subject_model)
        super(Plugin, self).on_site_startup(site)
        
    def setup_config_menu(self, site, user_type, m):
        mg = self.get_menu_group()
        m = m.add_menu(mg.app_label, mg.verbose_name)
        m.add_action('trends.TrendAreas')
        m.add_action('trends.TrendStages')

    def setup_explorer_menu(self, site, user_type, m):
        mg = self.get_menu_group()
        m = m.add_menu(mg.app_label, mg.verbose_name)
        m.add_action('trends.AllTrendEvents')
