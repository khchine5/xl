# -*- coding: UTF-8 -*-
# Copyright 2012-2017 Luc Saffre
# License: BSD (see file COPYING for details)

from __future__ import unicode_literals
from __future__ import print_function

from django.db import models
from atelier.utils import is_string
from decimal import Decimal
from lino.api import dd, _
from etgen.html import E, forcetext
from lino_xl.lib.ledger.roles import LedgerStaff
from lino_xl.lib.ledger.choicelists import TradeTypes

from lino_xl.lib.accounts.utils import DCLABELS, ZERO


class VatClasses(dd.ChoiceList):
    verbose_name = _("VAT class")
    verbose_name_plural = _("VAT classes")
    required_roles = dd.login_required(LedgerStaff)

add = VatClasses.add_item
add('0', _("Exempt"), 'exempt')    # post stamps, ...
add('1', _("Reduced"), 'reduced')  # food, books,...
add('2', _("Normal"), 'normal')    # everything else


class VatAreas(dd.ChoiceList):
    verbose_name = _("VAT area")
    verbose_name_plural = _("VAT areas")
    required_roles = dd.login_required(LedgerStaff)
    EU_COUNTRY_CODES = set("BE FR DE NL LU EE DK NO SE IT".split())
    
    @classmethod
    def get_for_country(cls, country=None):
        if country is None:
            isocode = dd.plugins.countries.country_code
        else:
            isocode = country.isocode
        if isocode == dd.plugins.countries.country_code:
            return cls.national
        if isocode in cls.EU_COUNTRY_CODES:
            return cls.eu
        return cls.international
    
add = VatAreas.add_item
add('10', _("National"), 'national')
add('20', _("EU"), 'eu')
add('30', _("International"), 'international')

class VatColumns(dd.ChoiceList):
    # to be populated by bevat, bevats, ...
    verbose_name = _("VAT column")
    verbose_name_plural = _("VAT columns")
    required_roles = dd.login_required(LedgerStaff)
    show_values = True

    
class VatRegime(dd.Choice):
    item_vat = True
    vat_area = None

    def __init__(self, value, text, name, vat_area=None, item_vat=True):
        super(VatRegime, self).__init__(value, text, name)
        self.vat_area = vat_area
        self.item_vat = item_vat

    def is_allowed_for(self, vat_area):
        if self.vat_area is None:
            return True
        return self.vat_area == vat_area


class VatRegimes(dd.ChoiceList):
    verbose_name = _("VAT regime")
    verbose_name_plural = _("VAT regimes")
    item_class = VatRegime
    required_roles = dd.login_required(LedgerStaff)

# NAT = VatAreas.national
# EU = VatAreas.eu

# add = VatRegimes.add_item
# add('10', _("Private person"), 'normal')
# add('20', _("Subject to VAT"), 'subject', NAT)
# add('30', _("Intra-community"), 'intracom', EU)
# re-populated in bevat and bevats.
# See also lino_xl.lib.vat.Plugin.default_vat_regime

# @dd.python_2_unicode_compatible
class DeclarationField(dd.Choice):
    """
    Base class for all fields of VAT declarations.

    .. attribute:: both_dc
    .. attribute:: editable
    .. attribute:: fieldnames

       An optional space-separated list of names of other declaration
       fields to be observed by this field.
                   
    .. attribute:: vat_regimes
    .. attribute:: vat_classes
    .. attribute:: vat_columns
                   
    .. attribute:: exclude_vat_regimes
    .. attribute:: exclude_vat_classes
    .. attribute:: exclude_vat_columns
    .. attribute:: is_payable
    
    """
    editable = False
    vat_regimes = None
    exclude_vat_regimes = None
    vat_classes = None
    exclude_vat_classes = None
    vat_columns = None
    exclude_vat_columns = None
    is_payable = False
    
    def __init__(self, value, dc,
                 vat_columns=None,
                 # is_base,
                 text=None,
                 fieldnames='',
                 both_dc=True,
                 vat_regimes=None, vat_classes=None,
                 **kwargs):
        name = "F" + value
        # text = string_concat("[{}] ".format(value), text)
        self.help_text = text
        super(DeclarationField, self).__init__(
            value, "[{}]".format(value), name, **kwargs)
        
        # self.is_base = is_base
        self.fieldnames = fieldnames
        self.vat_regimes = vat_regimes
        self.vat_classes = vat_classes
        self.vat_columns = vat_columns
        self.dc = dc
        self.both_dc = both_dc

    def attach(self, choicelist):
        self.observed_fields = set()
        for n in self.fieldnames.split():
            f = choicelist.get_by_value(n)
            if f is None:
                raise Exception(
                    "Invalid observed field {} for {}".format(
                        n, self))
            self.observed_fields.add(f)

        if is_string(self.vat_regimes):
            vat_regimes = self.vat_regimes
            self.vat_regimes = set()
            self.exclude_vat_regimes = set()
            for n in vat_regimes.split():
                if n.startswith('!'):
                    s = self.exclude_vat_regimes
                    n = n[1:]
                else:
                    s = self.vat_regimes
                v = VatRegimes.get_by_name(n)
                if v is None:
                    raise Exception(
                        "Invalid VAT regime {} for field {}".format(
                            v, self.value))
                s.add(v)
            if len(self.vat_regimes) == 0:
                self.vat_regimes = None
            
        if is_string(self.vat_classes):
            vat_classes = self.vat_classes
            self.vat_classes = set()
            self.exclude_vat_classes = set()
            for n in vat_classes.split():
                if n.startswith('!'):
                    s = self.exclude_vat_classes
                    n = n[1:]
                else:
                    s = self.vat_classes
                v = VatClasses.get_by_name(n)
                if v is None:
                    raise Exception(
                        "Invalid VAT class {} for field {}".format(
                            v, self.value))
                s.add(v)
            if len(self.vat_classes) == 0:
                self.vat_classes = None
                
        if is_string(self.vat_columns):
            vat_columns = self.vat_columns
            self.vat_columns = set()
            self.exclude_vat_columns = set()
            for n in vat_columns.split():
                if n.startswith('!'):
                    s = self.exclude_vat_columns
                    n = n[1:]
                else:
                    s = self.vat_columns
                v = VatColumns.get_by_value(n)
                if v is None:
                    raise Exception(
                        "Invalid VAT column {} for field {}".format(
                            v, self.value))
                s.add(v)
            if len(self.vat_columns) == 0:
                self.vat_columns = None
            
            
            
        super(DeclarationField, self).attach(choicelist)
            
        
    def get_model_field(self):
        return dd.PriceField(
            self.text, default=Decimal, editable=self.editable,
            help_text=self.help_text)
    
    # def __str__(self):
    #     # return force_text(self.text, errors="replace")
    #     # return self.text
    #     return "[{}] {}".format(self.value, self.text)

    def collect_from_movement(self, dcl, mvt, field_values, payable_sums):
        pass
    
    def collect_from_sums(self, dcl, sums, payable_sums):
        pass

class SumDeclarationField(DeclarationField):
    
    def collect_from_sums(self, dcl, field_values, payable_sums):
        tot = Decimal()
        for f in self.observed_fields:
            v = field_values[f.name]
            if f.dc == self.dc:
                tot += v
            else:
                tot += v
        field_values[self.name] = tot
        
class WritableDeclarationField(DeclarationField):
    editable = True
    def collect_from_sums(self, dcl, field_values, payable_sums):
        if self.is_payable:
            amount = field_values[self.name]
            if amount:
                if self.dc == dcl.journal.dc:
                    amount = - amount
                k = ((dcl.journal.account, None), None, None, None)
                payable_sums.collect(k, amount)

class MvtDeclarationField(DeclarationField):
    
    def collect_from_movement(self, dcl, mvt, field_values, payable_sums):
        # if not mvt.account.declaration_field in self.observed_fields:
        #     return 0
        if self.vat_classes is not None:
            if not mvt.vat_class in self.vat_classes:
                return
            if mvt.vat_class in self.exclude_vat_classes:
                return
        if self.vat_columns is not None:
            if not mvt.account.vat_column in self.vat_columns:
                return
            if mvt.account.vat_column in self.exclude_vat_columns:
                return
        if self.vat_regimes is not None:
            if not mvt.vat_regime in self.vat_regimes:
                return
            if mvt.vat_regime in self.exclude_vat_regimes:
                return
        if mvt.dc == self.dc:
            amount = mvt.amount
        elif self.both_dc:
            amount = -mvt.amount
        else:
            return
        if not amount:
            return
        field_values[self.name] += amount
        if self.is_payable:
            if self.dc == dcl.journal.dc:
                amount = - amount
            k = ((mvt.account, None), mvt.project, mvt.vat_class, mvt.vat_regime)
            payable_sums.collect(k, amount)
            # k = (dcl.journal.account, None, None, None)
            # payable_sums.collect(k, amount)
    

# class AccountDeclarationField(MvtDeclarationField):
#     pass
    # def __init__(self, value, dc, vat_columns, *args, **kwargs):
    #     # kwargs.update(fieldnames=value)
    #     kwargs.update(vat_columns=vat_columns)
    #     super(AccountDeclarationField, self).__init__(
    #         value, dc, *args, **kwargs)



class DeclarationFieldsBase(dd.ChoiceList):
    verbose_name_plural = _("Declaration fields")
    item_class = DeclarationField
    column_names = "value name text description *"
    
    # @classmethod    
    # def add_account_field(cls, *args, **kwargs):
    #     cls.add_item_instance(
    #         AccountDeclarationField(*args, **kwargs))
        
    @classmethod    
    def add_mvt_field(cls, *args, **kwargs):
        cls.add_item_instance(
            MvtDeclarationField(*args, **kwargs))
        
    @classmethod    
    def add_sum_field(cls, *args, **kwargs):
        cls.add_item_instance(
            SumDeclarationField(*args, **kwargs))


    @classmethod    
    def add_writable_field(cls, *args, **kwargs):
        cls.add_item_instance(
            WritableDeclarationField(*args, **kwargs))
        

    @dd.displayfield(_("Description"))
    def description(cls, fld, ar):
        if ar is None:
            return ''
        elems = [fld.help_text, E.br()]
        def x(label, lst, xlst):
            if lst is None:
                return
            spec = ' '.join([i.name or i.value for i in lst])
            if xlst is not None:
                spec += ' ' + ' '.join([
                    "!"+(i.name or i.value) for i in xlst])
            spec = spec.strip()
            if spec:
                elems.extend([label, " ", spec, E.br()])

        x(_("columns"), fld.vat_columns, fld.exclude_vat_columns)
        x(_("regimes"), fld.vat_regimes, fld.exclude_vat_regimes)
        x(_("classes"), fld.vat_classes, fld.exclude_vat_classes)


        elems += [
            fld.__class__.__name__, ' ',
            DCLABELS[fld.dc], 
            "" if fld.both_dc else " only",
            E.br()]

        if fld.observed_fields:
            elems += [
                _("Sum of"), ' ',
                ' '.join([i.name for i in fld.observed_fields]),
                E.br()]

        return E.div(*forcetext(elems))
    


class VatRule(dd.Choice):

    start_date = None
    end_date= None
    vat_area = None
    trade_type = None
    vat_class = None
    vat_regime = None
    rate = ZERO
    can_edit = False
    vat_account = None
    vat_returnable = False
    vat_returnable_account = None
    
    def __init__(self, value,
                 vat_class=None, rate=None,
                 vat_area=None, trade_type=None,
                 vat_regime=None, vat_account=None,
                 vat_returnable_account=None, vat_returnable=None):
        kw = dict()
        if rate is not None:
            kw.update(rate=Decimal(rate))
        if vat_returnable is not None:
            kw.update(vat_returnable=vat_returnable)
        if trade_type:
            kw.update(trade_type=TradeTypes.get_by_name(trade_type))
        if vat_regime:
            kw.update(vat_regime=VatRegimes.get_by_name(vat_regime))
        if vat_class:
            kw.update(vat_class=VatClasses.get_by_name(vat_class))
        if vat_account:
            kw.update(vat_account=vat_account)
        if vat_returnable_account:
            kw.update(
                vat_returnable_account=vat_returnable_account)
        # text = "{trade_type} {vat_area} {vat_class} {rate}".format(**kw)
        super(VatRule, self).__init__(value, value, **kw)
        
    # def __str__(self):
    #     kw = dict(
    #         trade_type=self.trade_type,
    #         vat_regime=self.vat_regime,
    #         vat_class=self.vat_class,
    #         rate=self.rate,
    #         vat_area=self.vat_area, seqno=self.seqno)
    #     return "{trade_type} {vat_area} {vat_class} {rate}".format(**kw)

class VatRules(dd.ChoiceList):
    verbose_name = _("VAT rule")
    verbose_name_plural = _("VAT rules")
    item_class = VatRule
    column_names = "value text description"

    @classmethod
    def get_vat_rule(
            cls, vat_area,
            trade_type=None, vat_regime=None, vat_class=None,
            date=None, default=models.NOT_PROVIDED):
        for i in cls.get_list_items():
            if i.vat_area is not None and vat_area != i.vat_area:
                continue
            if i.trade_type is not None and trade_type != i.trade_type:
                continue
            if i.vat_class is not None and vat_class != i.vat_class:
                continue
            if i.vat_regime is not None and vat_regime != i.vat_regime:
                continue
            if date is not None:
                if i.start_date and i.start_date > date:
                    continue
                if i.end_date and i.end_date < date:
                    continue
            return i
        if default is models.NOT_PROVIDED:
            msg = _("No VAT rule for ({!r},{!r},{!r},{!r},{!r})").format(
                    trade_type, vat_class, vat_area, vat_regime, 
                    dd.fds(date))
            if False:
                dd.logger.info(msg)
            else:
                raise Warning(msg)
        return default

    @dd.displayfield(_("Description"))
    def description(cls, rule, ar):
        if ar is None:
            return ''
        lst = []
        lst.append(str(rule.rate))
        lst.append(str(rule.trade_type))
        lst.append(str(rule.vat_regime))
        lst.append(str(rule.vat_area))
        lst.append(str(rule.vat_class))
        lst.append(str(rule.vat_account))
        lst.append(str(rule.vat_returnable))
        lst.append(str(rule.vat_returnable_account))
        return ', '.join(lst)

    
