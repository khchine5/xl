# -*- coding: UTF-8 -*-
# Copyright 2008-2018 Rumma & Ko Ltd
# License: BSD (see file COPYING for details)


"""Database models for this plugin.

"""

from __future__ import unicode_literals, print_function
import six

from builtins import str

import logging
logger = logging.getLogger(__name__)

import datetime
from dateutil.relativedelta import relativedelta

from django.db import models

from atelier.utils import last_day_of_month

from lino.api import dd, rt, _
from lino import mixins
from lino.utils import mti
from etgen.html import E
from lino.mixins.periods import DateRange
from lino.modlib.users.mixins import UserAuthored
from lino.modlib.printing.mixins import PrintableType
from lino.modlib.checkdata.choicelists import Checker

from lino_xl.lib.accounts.utils import DEBIT, CREDIT, ZERO
from lino_xl.lib.accounts.fields import DebitOrCreditField
from lino_xl.lib.contacts.choicelists import PartnerEvents
from lino.modlib.system.choicelists import ObservedEvent



from .utils import get_due_movements, check_clearings_by_partner
from .choicelists import (FiscalYears, VoucherTypes, VoucherStates,
                          PeriodStates, JournalGroups, TradeTypes)
from .mixins import ProjectRelated, VoucherNumber, JournalRef, PeriodRangeObservable
from .roles import VoucherSupervisor
# from .mixins import FKMATCH
from .ui import *


class LedgerInfo(dd.Model):
    class Meta:
        app_label = 'ledger'

    allow_cascaded_delete = 'user'
    user = dd.OneToOneField('users.User', primary_key=True)
    entry_date = models.DateField(
        _("Last entry date"), null=True, blank=True)
    
    @classmethod
    def get_for_user(cls, user):
        try:
            return cls.objects.get(user=user)
        except cls.DoesNotExist:
            return cls(user=user)

@dd.python_2_unicode_compatible
class Journal(mixins.BabelNamed,
              mixins.Sequenced,
              mixins.Referrable,
              PrintableType):

    class Meta:
        app_label = 'ledger'
        verbose_name = _("Journal")
        verbose_name_plural = _("Journals")

    trade_type = TradeTypes.field(blank=True)
    voucher_type = VoucherTypes.field()
    journal_group = JournalGroups.field()
    auto_check_clearings = models.BooleanField(
        _("Check clearing"), default=True)
    auto_fill_suggestions = models.BooleanField(
        _("Fill suggestions"), default=True)
    force_sequence = models.BooleanField(
        _("Force chronological sequence"), default=False)
    account = dd.ForeignKey('accounts.Account', blank=True, null=True)
    partner = dd.ForeignKey('contacts.Company', blank=True, null=True)
    printed_name = dd.BabelCharField(
        _("Printed document designation"), max_length=100, blank=True)
    dc = DebitOrCreditField(_("Primary booking direction"))
    yearly_numbering = models.BooleanField(
        _("Yearly numbering"), default=True)
    must_declare = models.BooleanField(default=True)
    # invert_due_dc = models.BooleanField(
    #     _("Invert booking direction"),
    #     help_text=_("Whether to invert booking direction of due movement."),
    #     default=True)


    def get_doc_model(self):
        """The model of vouchers in this Journal.

        """
        # print self,DOCTYPE_CLASSES, self.doctype
        return self.voucher_type.model
        #~ return DOCTYPES[self.doctype][0]

    def get_doc_report(self):
        return self.voucher_type.table_class
        #~ return DOCTYPES[self.doctype][1]

    def get_voucher(self, year=None, number=None, **kw):
        cl = self.get_doc_model()
        kw.update(journal=self, accounting_period__year=year, number=number)
        return cl.objects.get(**kw)

    def create_voucher(self, **kw):
        """Create an instance of this Journal's voucher model
        (:meth:`get_doc_model`).

        """
        cl = self.get_doc_model()
        kw.update(journal=self)
        try:
            doc = cl()
            # ~ doc = cl(**kw) # wouldn't work. See Django ticket #10808
            #~ doc.journal = self
            for k, v in kw.items():
                setattr(doc, k, v)
            #~ print 20120825, kw
        except TypeError:
            #~ print 20100804, cl
            raise
        doc.on_create(None)
        #~ doc.full_clean()
        #~ doc.save()
        return doc

    def get_allowed_accounts(self, **kw):
        if self.trade_type:
            return self.trade_type.get_allowed_accounts(**kw)
        # kw.update(chart=self.chart)
        return rt.models.accounts.Account.objects.filter(**kw)

    def get_next_number(self, voucher):
        # ~ self.save() # 20131005 why was this?
        cl = self.get_doc_model()
        flt = dict()
        if self.yearly_numbering:
            flt.update(accounting_period__year=voucher.accounting_period.year)
        d = cl.objects.filter(journal=self, **flt).aggregate(
            models.Max('number'))
        number = d['number__max']
        #~ logger.info("20121206 get_next_number %r",number)
        if number is None:
            return 1
        return number + 1

    def __str__(self):
        # s = super(Journal, self).__str__()
        s = dd.babelattr(self, 'name')
        if self.ref:
            s += " (%s)" % self.ref
            #~ return '%s (%s)' % (d.BabelNamed.__unicode__(self),self.ref or self.id)
        return s
            #~ return self.ref +'%s (%s)' % mixins.BabelNamed.__unicode__(self)
            #~ return self.id +' (%s)' % mixins.BabelNamed.__unicode__(self)

    def save(self, *args, **kw):
        #~ self.before_save()
        r = super(Journal, self).save(*args, **kw)
        self.after_save()
        return r

    def after_save(self):
        pass

    def full_clean(self, *args, **kw):
        if self.dc is None:
            if self.trade_type:
                self.dc = self.trade_type.dc
            elif self.account:
                self.dc = self.account.type.dc
            else:
                self.dc = DEBIT  # cannot be NULL

        if not self.name:
            self.name = self.id
        #~ if not self.pos:
            #~ self.pos = self.__class__.objects.all().count() + 1
        super(Journal, self).full_clean(*args, **kw)

    def disable_voucher_delete(self, doc):
        # print "pre_delete_voucher", doc.number, self.get_next_number()
        if self.force_sequence:
            if doc.number + 1 != self.get_next_number(doc):
                return _("%s is not the last voucher in journal"
                         % str(doc))

    def get_template_groups(self):
        """Here we override the class method by an instance method.  This
        means that we must also override all other methods of
        Printable who call the *class* method.  This is currently only
        :meth:`template_choices`.

        """
        return [self.voucher_type.model.get_template_group()]

    @dd.chooser(simple_values=True)
    def template_choices(cls, build_method, voucher_type):
        # Overrides PrintableType.template_choices to not use the class
        # method `get_template_groups`.

        if not voucher_type:
            return []
        #~ print 20131006, voucher_type
        template_groups = [voucher_type.model.get_template_group()]
        return cls.get_template_choices(build_method, template_groups)


#
#
#


@dd.python_2_unicode_compatible
class AccountingPeriod(DateRange, mixins.Referrable):
    class Meta:
        app_label = 'ledger'
        verbose_name = _("Accounting period")
        verbose_name_plural = _("Accounting periods")
        ordering = ['ref']

    preferred_foreignkey_width = 10
    
    state = PeriodStates.field(default=PeriodStates.as_callable('open'))
    year = FiscalYears.field(blank=True)
    remark = models.CharField(_("Remark"), max_length=250, blank=True)

    @classmethod
    def get_available_periods(cls, entry_date):
        """Return a queryset of peruiods available for booking."""
        if entry_date is None:  # added 20160531
            entry_date = dd.today()
        fkw = dict(start_date__lte=entry_date, end_date__gte=entry_date)
        return rt.models.ledger.AccountingPeriod.objects.filter(**fkw)

    @classmethod
    def get_ref_for_date(cls, d):
        """Return a text to be used as :attr:`ref` for a new period.

        Alternative implementation for usage on a site with movements
        before year 2000::

            @classmethod
            def get_ref_for_date(cls, d):
                if d.year < 2000:
                    y = str(d.year - 1900)
                elif d.year < 2010:
                    y = "A" + str(d.year - 2000)
                elif d.year < 2020:
                    y = "B" + str(d.year - 2010)
                elif d.year < 2030:
                    y = "C" + str(d.year - 2020)
                return y + "{:0>2}".format(d.month)

        """
        if dd.plugins.ledger.fix_y2k:
            return FiscalYears.from_int(d.year).value \
                + "{:0>2}".format(d.month)

        return "{0.year}-{0.month:0>2}".format(d)

    """The template used for building the :attr:`ref` of an
    :class:`AccountingPeriod`.

    `Format String Syntax
    <https://docs.python.org/2/library/string.html#formatstrings>`_

    """

    @classmethod
    def get_periods_in_range(cls, p1, p2):
        return cls.objects.filter(ref__gte=p1.ref, ref__lte=p2.ref)
    
    @classmethod
    def get_period_filter(cls, fieldname, p1, p2, **kwargs):
        if p1 is None:
            return kwargs
        if p2 is None:
            kwargs[fieldname] = p1
        else:
            periods = cls.get_periods_in_range(p1, p2)
            kwargs[fieldname+'__in'] = periods
        return kwargs

    @classmethod
    def get_default_for_date(cls, d):
        ref = cls.get_ref_for_date(d)
        obj = rt.models.ledger.AccountingPeriod.get_by_ref(ref, None)
        if obj is None:
            values = dict(start_date=d.replace(day=1))
            values.update(end_date=last_day_of_month(d))
            values.update(ref=ref)
            obj = AccountingPeriod(**values)
            obj.full_clean()
            obj.save()
        return obj

    def full_clean(self, *args, **kwargs):
        if self.start_date is None:
            self.start_date = dd.today().replace(day=1)
        if not self.year:
            self.year = FiscalYears.from_date(self.start_date)
        super(AccountingPeriod, self).full_clean(*args, **kwargs)

    def __str__(self):
        if not self.ref:
            return dd.obj2str(self)
            # "{0} {1} (#{0})".format(self.pk, self.year)
        return self.ref

AccountingPeriod.set_widget_options('ref', width=6)
  
class PaymentTerm(mixins.BabelNamed, mixins.Referrable):
              

    class Meta:
        app_label = 'ledger'
        verbose_name = _("Payment term")
        verbose_name_plural = _("Payment terms")

    days = models.IntegerField(_("Days"), default=0)
    months = models.IntegerField(_("Months"), default=0)
    end_of_month = models.BooleanField(_("End of month"), default=False)

    printed_text = dd.BabelTextField(
        _("Printed text"), blank=True, format='plain')
    

    def get_due_date(self, date1):
        assert isinstance(date1, datetime.date), \
            "%s is not a date" % date1
        d = date1 + relativedelta(months=self.months, days=self.days)
        if self.end_of_month:
            d = last_day_of_month(d)
        return d


@dd.python_2_unicode_compatible
class Voucher(UserAuthored, mixins.Registrable, PeriodRangeObservable):
    manager_roles_required = dd.login_required(VoucherSupervisor)
    
    class Meta:
        app_label = 'ledger'
        verbose_name = _("Voucher")
        verbose_name_plural = _("Vouchers")

    journal = JournalRef()
    entry_date = models.DateField(_("Entry date"))
    voucher_date = models.DateField(_("Voucher date"))
    accounting_period = dd.ForeignKey(
        'ledger.AccountingPeriod', blank=True)
    number = VoucherNumber(_("No."), blank=True, null=True)
    narration = models.CharField(_("Narration"), max_length=200, blank=True)
    state = VoucherStates.field(
        default=VoucherStates.as_callable('draft'))
    workflow_state_field = 'state'

    #~ @classmethod
    #~ def create_journal(cls,id,**kw):
        #~ doctype = get_doctype(cls)
        #~ jnl = Journal(doctype=doctype,id=id,**kw)
        #~ return jnl

    @property
    def currency(self):
        """This is currently used only in some print templates.

        """
        return dd.plugins.ledger.currency_symbol

    # @classmethod
    # def setup_parameters(cls, **fields):
    #     fields.setdefault(
    #         'accounting_period', dd.ForeignKey(
    #             'ledger.AccountingPeriod', blank=True, null=True))
    #     return super(Voucher, cls).setup_parameters(**fields)

    # @classmethod
    # def get_simple_parameters(cls):
    #     s = super(Voucher, cls).get_simple_parameters()
    #     s.add('accounting_period')
    #     return s

    @dd.displayfield(_("No."))
    def number_with_year(self, ar):
        return "{0}/{1}".format(self.number, self.accounting_period.year)

    @classmethod
    def quick_search_filter(model, search_text, prefix=''):
        """Overrides :meth:`lino.core.model.Model.quick_search_filter`.

        Examples:

        123 -> voucher number 123 in current year

        123/2014 -> voucher number 123 in 2014

        """
        # logger.info(
        #     "20160612 Voucher.quick_search_filter(%s, %r, %r)",
        #     model, search_text, prefix)
        parts = search_text.split('/')
        if len(parts) == 2:
            kw = {
                prefix + 'number': parts[0],
                prefix + 'accounting_period__year': parts[1]}
            return models.Q(**kw)
        if search_text.isdigit() and not search_text.startswith('0'):
            kw = {
                prefix + 'number': int(search_text),
                prefix + 'accounting_period__year':
                FiscalYears.from_date(dd.today())}
            return models.Q(**kw)
        return super(Voucher, model).quick_search_filter(search_text, prefix)

    def full_clean(self, *args, **kwargs):
        if self.entry_date is None:
            self.entry_date = dd.today()
        if self.voucher_date is None:
            self.voucher_date = self.entry_date
        if not self.accounting_period_id:
            self.accounting_period = AccountingPeriod.get_default_for_date(
                self.entry_date)
        if self.number is None:
            self.number = self.journal.get_next_number(self)
        super(Voucher, self).full_clean(*args, **kwargs)

    def on_create(self, ar):
        super(Voucher, self).on_create(ar)
        if self.entry_date is None:
            if ar is None:
                self.entry_date = dd.today()
            else:
                info = LedgerInfo.get_for_user(ar.get_user())
                self.entry_date = info.entry_date or dd.today()
        
    def entry_date_changed(self, ar):
        self.accounting_period = AccountingPeriod.get_default_for_date(
            self.entry_date)
        self.voucher_date = self.entry_date
        self.accounting_period_changed(ar)
        info = LedgerInfo.get_for_user(ar.get_user())
        info.entry_date = self.entry_date
        info.full_clean()
        info.save()

    def accounting_period_changed(self, ar):
        """If user changes the :attr:`accounting_period`, then the `number`
        might need to change.

        """
        self.number = self.journal.get_next_number(self)

    def get_due_date(self):
        return self.entry_date

    def get_trade_type(self):
        return self.journal.trade_type

    def get_printed_name(self):
        return dd.babelattr(self.journal, 'printed_name')

    def get_partner(self):
        """
        Return the partner related to this voucher. Overridden by
        PartnerRelated vouchers.
        """
        return None

    def after_ui_save(self, ar, cw):
        super(Voucher, self).after_ui_save(ar, cw)
        p = self.get_partner()
        if p is None:
            return
        tt = self.get_trade_type()
        account = tt.get_partner_invoice_account(p)
        if account is None:
            return
        if self.items.exists():
            return
        i = self.add_voucher_item(account=account)
        i.full_clean()
        i.save()

        
    @classmethod
    def get_journals(cls):
        vt = VoucherTypes.get_for_model(cls)
        return Journal.objects.filter(voucher_type=vt).order_by('seqno')

    @dd.chooser()
    def unused_accounting_period_choices(cls, entry_date):
        # deactivated because it also limits the choices of the
        # parameter field (which is a Lino bug)
        return rt.models.ledger.AccountingPeriod.get_available_periods(
            entry_date)

    @dd.chooser()
    def journal_choices(cls):
        # logger.info("20140603 journal_choices %r", cls)
        return cls.get_journals()

    @classmethod
    def create_journal(cls, trade_type=None, account=None, **kw):
        vt = VoucherTypes.get_for_model(cls)
        if isinstance(trade_type, six.string_types):
            trade_type = TradeTypes.get_by_name(trade_type)
        if isinstance(account, six.string_types):
            account = rt.models.accounts.Account.get_by_ref(account)
        if account is not None:
            kw.update(account=account)
        return Journal(trade_type=trade_type, voucher_type=vt, **kw)

    def __str__(self):
        if self.number is None:
            return "{0}#{1}".format(self.journal.ref, self.id)
        if self.journal.yearly_numbering:
            return "{0} {1}/{2}".format(self.journal.ref, self.number,
                                        self.accounting_period.year)
        return "{0} {1}".format(self.journal.ref, self.number)
        # if self.journal.ref:
        #     return "%s %s" % (self.journal.ref,self.number)
        # return "#%s (%s %s)" % (self.number,self.journal,self.year)

    def get_default_match(self):
        return str(self)
        # return "%s#%s" % (self.journal.ref, self.id)
        # return "%s%s" % (self.id, self.journal.ref)

    # def get_voucher_match(self):
    #     return str(self)  # "{0}{1}".format(self.journal.ref, self.number)
        
    def set_workflow_state(self, ar, state_field, newstate):
        """"""
        if newstate.name == 'registered':
            self.register_voucher(ar)
        elif newstate.name == 'draft':
            self.deregister_voucher(ar)
        super(Voucher, self).set_workflow_state(ar, state_field, newstate)

        # doit(ar)

        # if newstate.name == 'registered':
        #     ar.confirm(
        #         doit,
        #         _("Are you sure you want to register "
        #           "voucher {0}?").format(self))
        # else:
        #     doit(ar)

    # def before_state_change(self, ar, old, new):
    #     if new.name == 'registered':
    #         self.register_voucher(ar)
    #     elif new.name == 'draft':
    #         self.deregister_voucher(ar)
    #     super(Voucher, self).before_state_change(ar, old, new)

    def register_voucher(self, ar, do_clear=True):
        """
        Delete any existing movements and re-create them
        """
        # dd.logger.info("20151211 cosi.Voucher.register_voucher()")
        # self.year = FiscalYears.from_date(self.entry_date)
        # dd.logger.info("20151211 movement_set.all().delete()")

        def doit(partners):
            seqno = 0
            # dd.logger.info("20151211 gonna call get_wanted_movements()")
            movements = self.get_wanted_movements()
            # dd.logger.info("20151211 gonna save %d movements", len(movements))
            # self.full_clean()
            # self.save()
            
            fcu = dd.plugins.ledger.force_cleared_until
            for m in movements:
                seqno += 1
                m.seqno = seqno
                if fcu and self.entry_date <= fcu:
                    m.cleared = True
                m.full_clean()
                m.save()
                if m.partner:
                    partners.add(m.partner)

        self.do_and_clear(doit, do_clear)

    def deregister_voucher(self, ar, do_clear=True):

        def doit(partners):
            pass
        self.do_and_clear(doit, do_clear)

    def do_and_clear(self, func, do_clear):
        """Delete all movements of this voucher, then run the given callable
        `func`, passing it a set with all partners who had at least
        one movement in this voucher. The function is expected to add
        more partners to this set.  Then call `check_clearings` for
        all these partners.

        """
        existing_mvts = self.movement_set.all()
        partners = set()
        # accounts = set()
        if not self.journal.auto_check_clearings:
            do_clear = False
        if do_clear:
            for m in existing_mvts.filter(
                    account__clearable=True, partner__isnull=False):
                partners.add(m.partner)
        existing_mvts.delete()
        func(partners)
        if do_clear:
            for p in partners:
                check_clearings_by_partner(p)
            # for a in accounts:
            #     check_clearings_by_account(a)
        
        # dd.logger.info("20151211 Done cosi.Voucher.register_voucher()")

    def disable_delete(self, ar=None):
        msg = self.journal.disable_voucher_delete(self)
        if msg is not None:
            return msg
        return super(Voucher, self).disable_delete(ar)

    def get_wanted_movements(self):
        raise NotImplementedError()

    def create_movement(self, item, acc_tuple, project, dc, amount, **kw):
        """Create a movement for this voucher.

        The specified `item` may be `None` if this the movement is
        caused by more than one item. It is used by
        :class:`DatedFinancialVoucher
        <lino_xl.lib.finan.mixins.DatedFinancialVoucher>`.

        """
        # dd.logger.info("20151211 ledger.create_movement()")
        account, ana_account = acc_tuple
        if account is None and item is not None:
            raise Warning("No account specified for {}".format(item))
        if not isinstance(account, rt.models.accounts.Account):
            raise Warning("{} is not an Account object".format(account))
        kw['voucher'] = self
        kw['account'] = account
        if ana_account is not None:
            kw['ana_account'] = ana_account
        kw['value_date'] = self.entry_date
        if account.clearable:
            kw.update(cleared=False)
        else:
            kw.update(cleared=True)

        if dd.plugins.ledger.project_model:
            kw['project'] = project

        if amount < 0:
            amount = - amount
            dc = not dc
        kw['amount'] = amount
        kw['dc'] = dc

        b = rt.models.ledger.Movement(**kw)
        return b

    #~ def get_row_permission(self,ar,state,ba):
        #~ """
        #~ Only invoices in an editable state may be edited.
        #~ """
        #~ if not ba.action.readonly and self.state is not None and not self.state.editable:
            #~ return False
        #~ return super(Voucher,self).get_row_permission(ar,state,ba)

    def get_mti_leaf(self):
        return mti.get_child(self, self.journal.voucher_type.model)

    # def obj2html(self, ar):
    def obj2href(self, ar):
        return ar.obj2html(self.get_mti_leaf())

    #~ def add_voucher_item(self,account=None,**kw):
        #~ if account is not None:
            #~ if not isinstance(account,accounts.Account):
            #~ if isinstance(account,six.string_types):
                #~ account = self.journal.chart.get_account_by_ref(account)
            #~ kw['account'] = account
    def add_voucher_item(self, account=None, **kw):
        if account is not None:
            if isinstance(account, six.string_types):
                account = rt.models.accounts.Account.get_by_ref(account)
            kw['account'] = account
        kw.update(voucher=self)
        #~ logger.info("20131116 %s",self.items.model)
        return self.items.model(**kw)
        #~ return super(AccountInvoice,self).add_voucher_item(**kw)

    def get_bank_account(self):
        """Return the `sepa.Account` object to which this voucher is to be
        paid. This is needed by
        :class:`lino_xl.lib.ledger.utils.DueMovement`.

        """
        return None
        # raise NotImplementedError()

Voucher.set_widget_options('number_with_year', width=8)


@dd.python_2_unicode_compatible
class Movement(ProjectRelated, PeriodRangeObservable):
    allow_cascaded_delete = ['voucher']

    class Meta:
        app_label = 'ledger'
        verbose_name = _("Movement")
        verbose_name_plural = _("Movements")

    observable_period_field = 'voucher__accounting_period'
    
    voucher = dd.ForeignKey('ledger.Voucher')

    partner = dd.ForeignKey(
        'contacts.Partner',
        related_name="%(app_label)s_%(class)s_set_by_partner",
        blank=True, null=True)

    seqno = models.IntegerField(_("Seq.No."))

    account = dd.ForeignKey('accounts.Account')
    amount = dd.PriceField(default=0)
    dc = DebitOrCreditField()

    match = models.CharField(_("Match"), blank=True, max_length=20)

    # match = MatchField(blank=True, null=True)

    cleared = models.BooleanField(_("Cleared"), default=False)
    # 20160327: rename "satisfied" to "cleared"

    value_date = models.DateField(_("Value date"), null=True, blank=True)

    @dd.chooser(simple_values=True)
    def match_choices(cls, partner, account):
        qs = cls.objects.filter(
            partner=partner, account=account, cleared=False)
        qs = qs.order_by('value_date')
        return qs.values_list('match', flat=True)

    def select_text(self):
        v = self.voucher.get_mti_leaf()
        if v is None:
            return str(self.voucher)
        return "%s (%s)" % (v, v.entry_date)

    @dd.virtualfield(dd.PriceField(_("Debit")))
    def debit(self, ar):
        if self.dc:
            return None
        return self.amount

    @dd.virtualfield(dd.PriceField(_("Credit")))
    def credit(self, ar):
        if self.dc:
            return self.amount
        return None

    @dd.displayfield(_("Voucher"))
    def voucher_link(self, ar):
        if ar is None:
            return ''
        return ar.obj2html(self.voucher.get_mti_leaf())

    @dd.displayfield(_("Voucher partner"))
    def voucher_partner(self, ar):
        if ar is None:
            return ''
        voucher = self.voucher.get_mti_leaf()
        if voucher is None:
            return ''
        p = voucher.get_partner()
        if p is None:
            return ''
        return ar.obj2html(p)

    @dd.displayfield(_("Match"))
    def match_link(self, ar):
        if ar is None or not self.match:
            return ''
        sar = rt.models.ledger.MovementsByMatch.request(
            master_instance=self.match, parent=ar)
        return sar.ar2button(label=self.match)

    #~ @dd.displayfield(_("Matched by"))
    #~ def matched_by(self,ar):
        #~ elems = [obj.voucher_link(ar) for obj in Movement.objects.filter(match=self)]
        #~ return E.div(*elems)

    def get_siblings(self):
        return self.voucher.movement_set.all()
        #~ return self.__class__.objects.filter().order_by('seqno')

    def __str__(self):
        return "%s.%d" % (str(self.voucher), self.seqno)

    # def get_match(self):
    #     return self.match or str(self.voucher)

    @classmethod
    def get_balance(cls, dc, qs):
        bal = ZERO
        for mvt in qs:
            if mvt.dc == dc:
                bal += mvt.amount
            else:
                bal -= mvt.amount
        return bal

    @classmethod
    def balance_info(cls, dc, **kwargs):
        qs = cls.objects.filter(**kwargs)
        qs = qs.order_by('value_date')
        bal = ZERO
        s = ''
        for mvt in qs:
            amount = mvt.amount
            if mvt.dc == dc:
                bal -= amount
                s += ' -' + str(amount)
            else:
                bal += amount
                s += ' +' + str(amount)
            s += " ({0}) ".format(mvt.voucher)
            # s += " ({0} {1}) ".format(
            #     mvt.voucher,
            #     dd.fds(mvt.voucher.voucher_date))
        if bal:
            return s + "= " + str(bal)
        return ''
        if False:
            from lino_xl.lib.cal.utils import day_and_month
            mvts = []
            for dm in get_due_movements(CREDIT, partner=self.pupil):
                s = dm.match
                s += " [{0}]".format(day_and_month(dm.due_date))
                s += " ("
                s += ', '.join([str(i.voucher) for i in dm.debts])
                if len(dm.payments):
                    s += " - "
                    s += ', '.join([str(i.voucher) for i in dm.payments])
                s += "): {0}".format(dm.balance)
                mvts.append(s)
            return '\n'.join(mvts)


Movement.set_widget_options('voucher_link', width=12)


class MatchRule(dd.Model):

    class Meta:
        app_label = 'ledger'
        verbose_name = _("Match rule")
        verbose_name_plural = _("Match rules")
        unique_together = ['account', 'journal']

    account = dd.ForeignKey('accounts.Account')
    journal = JournalRef()

    @dd.chooser()
    def unused_account_choices(self, journal):
        # would be nice, but doesn't work because matchrules are
        # usually entered via MatchRulesByJournal where journal is
        # always None.
        if journal:
            fkw = {journal.trade_type.name + '_allowed': True}
            return rt.models.accounts.Account.objects.filter(**fkw)
        print("20151221 journal is None")
        return []


for tt in TradeTypes.objects():
    dd.inject_field(
        'accounts.Account',
        tt.name + '_allowed',
        models.BooleanField(verbose_name=tt.text, default=False))


dd.inject_field(
    'contacts.Partner',
    'payment_term',
    dd.ForeignKey(
        'ledger.PaymentTerm',
        blank=True, null=True,
        help_text=_("The default payment term for "
                    "sales invoices to this customer.")))


class VoucherChecker(Checker):
    "Check for wrong ledger movements"
    verbose_name = _("Check integrity of ledger movements")
    messages = dict(
        missing=_("Missing movement {0}."),
        unexpected=_("Unexpected movement {0}."),
        diff=_("Movement {0} : {1} {2} != {3}."),
    )

    def get_checkable_models(self):
        for m in rt.models_by_base(Voucher):
            if m is not Voucher:
                yield m

    def get_checkdata_problems(self, obj, fix=False):
        if obj.__class__ is rt.models.ledger.Voucher:
            return

        def m2k(obj):
            return obj.seqno

        wanted = dict()
        seqno = 0
        fcu = dd.plugins.ledger.force_cleared_until
        for m in obj.get_wanted_movements():
            seqno += 1
            m.seqno = seqno
            if fcu and obj.entry_date <= fcu:
                m.cleared = True
            m.full_clean()
            wanted[m2k(m)] = m

        for em in obj.movement_set.all():
            wm = wanted.pop(m2k(em), None)
            if wm is None:
                yield (False, self.messages['unexpected'].format(em))
                return
            for k in ('partner_id', 'account_id', 'dc', 'amount',
                      'value_date'):
                emv = getattr(em, k)
                wmv = getattr(wm, k)
                if emv != wmv:
                    yield (False, self.messages['diff'].format(
                        em, k, emv, wmv))
                    return
                    
        if wanted:
            for missing in wanted.values():
                yield (False, self.messages['missing'].format(missing))
                return

            
VoucherChecker.activate()


class PartnerHasOpenMovements(ObservedEvent):
    text = _("Has open movements")

    def add_filter(self, qs, pv):
        qs = qs.filter(movement__cleared=False)
        if pv.end_date:
            qs = qs.filter(movement__value_date__lte=pv.end_date)
        if pv.start_date:
            qs = qs.filter(movement__value_date__gte=pv.start_date)
        return qs.distinct()

PartnerEvents.add_item_instance(
    PartnerHasOpenMovements("has_open_movements"))


