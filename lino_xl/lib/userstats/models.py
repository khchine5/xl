# -*- coding: UTF-8 -*-
# Copyright 2018 Luc Saffre
# License: BSD (see file COPYING for details)

from builtins import object

from django.db import models

from lino.api import dd, rt, _


import datetime
from lino.modlib.summaries.mixins import Summary
# from atelier.utils import last_day_of_month
from lino.modlib.system.choicelists import PeriodEvents

class UserStat(Summary):
    
    class Meta(object):
        app_label = 'userstats'
        verbose_name = _("User Statistics entry")
        verbose_name_plural = _("User Statistics")

    summary_period = 'monthly'
    master = dd.ForeignKey('system.SiteConfig')
    active_users = models.IntegerField(_("Active users"))
    
    def reset_summary_data(self):
        self.active_users = 0
        
    # @classmethod
    # def get_summary_master_model(cls):
    #     return rt.models.system.SiteConfig
    
    def get_summary_collectors(self):
        # last_day_of_month(sd)
        qs = rt.models.users.User.objects.filter(username__isnull=False)

        if self.year:
            qs = PeriodEvents.active.add_filter(
                qs, datetime.date(self.year, self.month or 1, 1))
        yield (self.add_from_user, qs)

    def add_from_user(self, obj):
        self.active_users += 1


class UserStats(dd.Table):
    model = "userstats.UserStat"
    column_names = "year month active_users *"
    
