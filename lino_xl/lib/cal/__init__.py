# Copyright 2013-2017 Luc Saffre
#
# License: BSD (see file COPYING for details)

"""This is Lino's calendar module. See :doc:`/specs/cal`.

.. autosummary::
   :toctree:

    utils
    workflows
    fixtures.std
    fixtures.demo
    fixtures.demo2

"""

from lino.api import ad, _
from dateutil.relativedelta import relativedelta


class Plugin(ad.Plugin):
    verbose_name = _("Calendar")

    needs_plugins = ['lino.modlib.gfks', 'lino.modlib.printing',
                     # 'lino.modlib.notify',
                     'lino_xl.lib.xl']

    # partner_model = 'contacts.Partner'
    partner_model = 'contacts.Person'
    ignore_dates_before = None
    ignore_dates_after = None

    def on_init(self):
        tod = self.site.today()
        # self.ignore_dates_after = tod.replace(year=tod.year+5, day=28)
        # above code should not fail on February 29 of a leap year.
        self.ignore_dates_after = tod + relativedelta(years=5)

    def on_site_startup(self, site):
        self.partner_model = site.models.resolve(self.partner_model)
        super(Plugin, self).on_site_startup(site)
        
    def setup_main_menu(self, site, user_type, m):
        m = m.add_menu(self.app_label, self.verbose_name)
        m.add_action('cal.MyEntries')  # string spec to allow overriding
        m.add_action('cal.OverdueAppointments')
        m.add_action('cal.MyUnconfirmedAppointments')

        # m.add_separator('-')
        # m  = m.add_menu("tasks",_("Tasks"))
        m.add_action('cal.MyTasks')
        # m.add_action(MyTasksToDo)
        m.add_action('cal.MyGuests')
        m.add_action('cal.MyPresences')
        m.add_action('cal.MyOverdueAppointments')

    def setup_config_menu(self, site, user_type, m):
        m = m.add_menu(self.app_label, self.verbose_name)
        m.add_action('cal.Calendars')
        # m.add_action('cal.MySubscriptions')
        m.add_action('cal.AllRooms')
        m.add_action('cal.Priorities')
        m.add_action('cal.RecurrentEvents')
        # m.add_action(AccessClasses)
        # m.add_action(EventStatuses)
        # m.add_action(TaskStatuses)
        # m.add_action(EventTypes)
        m.add_action('cal.GuestRoles')
        # m.add_action(GuestStatuses)
        m.add_action('cal.EventTypes')
        m.add_action('cal.EventPolicies')
        m.add_action('cal.RemoteCalendars')
        m.add_action('cal.DailyPlannerRows')

    def setup_explorer_menu(self, site, user_type, m):
        m = m.add_menu(self.app_label, self.verbose_name)
        m.add_action('cal.AllEntries')
        m.add_action('cal.Tasks')
        m.add_action('cal.AllGuests')
        m.add_action('cal.Subscriptions')
        # m.add_action(Memberships)
        m.add_action('cal.EntryStates')
        m.add_action('cal.GuestStates')
        m.add_action('cal.TaskStates')
        # m.add_action(RecurrenceSets)

    def get_dashboard_items(self, user):
        if user.authenticated:
            yield self.site.models.cal.MyTasks
            yield self.site.models.cal.MyEntries
            yield self.site.models.cal.MyOverdueAppointments
            yield self.site.models.cal.MyUnconfirmedAppointments
            yield self.site.models.cal.DailyPlanner
        else:
            yield self.site.models.cal.PublicEntries
