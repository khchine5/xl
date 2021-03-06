# -*- coding: UTF-8 -*-
# Copyright 2016-2018 Rumma & Ko Ltd
# License: BSD (see file COPYING for details)


from __future__ import unicode_literals

from lino.api import dd, rt, _


class StartInvoicing(dd.Action):
    show_in_bbar = False
    icon_name = 'basket'
    sort_index = 52
    label = _("Create invoices")
    select_rows = False
    http_method = 'POST'

    def get_options(self, ar):
        return {}

    def run_from_ui(self, ar, **kw):
        options = self.get_options(ar)
        plan = rt.models.invoicing.Plan.start_plan(ar.get_user(), **options)
        ar.goto_instance(plan)


class StartInvoicingForJournal(StartInvoicing):
    show_in_bbar = True

    def get_options(self, ar):
        jnl = ar.master_instance
        assert isinstance(jnl, rt.models.ledger.Journal)
        return dict(journal=jnl, partner=None)


class StartInvoicingForPartner(StartInvoicing):
    show_in_bbar = True
    select_rows = True

    def get_options(self, ar):
        partner = ar.selected_rows[0]
        assert isinstance(partner, rt.models.contacts.Partner)
        return dict(partner=partner)


class UpdatePlan(dd.Action):
    label = _("Update plan")
    icon_name = 'lightning'

    def run_from_ui(self, ar, **kw):
        plan = ar.selected_rows[0]
        plan.items.all().delete()
        plan.fill_plan(ar)
        ar.success(refresh=True)


class ExecutePlan(dd.Action):
    label = _("Execute plan")
    icon_name = 'money'

    def run_from_ui(self, ar, **kw):
        plan = ar.selected_rows[0]
        for item in plan.items.filter(selected=True, invoice__isnull=True):
            item.create_invoice(ar)
        ar.success(refresh=True)


class ExecuteItem(ExecutePlan):
    label = _("Execute item")
    show_in_workflow = True
    show_in_bbar = False
    

    def get_action_permission(self, ar, obj, state):
        if obj.invoice_id:
            return False
        return super(ExecuteItem, self).get_action_permission(ar, obj, state)
        
    def run_from_ui(self, ar, **kw):
        for item in ar.selected_rows:
            if item.invoice_id:
                raise Warning("Invoice was already generated")
            item.create_invoice(ar)
        ar.success(refresh=True)


class ToggleSelection(dd.Action):
    label = _("Toggle selections")

    def run_from_ui(self, ar, **kw):
        plan = ar.selected_rows[0]
        for item in plan.items.all():
            item.selected = not item.selected
            item.save()
        ar.success(refresh=True)

