# -*- coding: UTF-8 -*-
# Copyright 2012-2017 Luc Saffre
# License: BSD (see file COPYING for details)

"""
Declaration fields.
"""

from __future__ import unicode_literals

# from django.db import models
# from django.conf import settings
#from django.utils.translation import string_concat
from lino_xl.lib.accounts.utils import DEBIT, CREDIT

from lino.api import dd, rt, _

from lino_xl.lib.vat.choicelists import DeclarationFieldsBase
from lino_xl.lib.vat.choicelists import VatColumns
from lino_xl.lib.vat.choicelists import VatRegimes, VatAreas, VatRules
from lino_xl.lib.accounts.choicelists import CommonAccounts

NAT = VatAreas.national
EU = VatAreas.eu
INT = VatAreas.international

VatRegimes.clear()
add = VatRegimes.add_item
add('10', _("Private person"), 'normal', NAT)
add('11', _("Private person (reduced)"), 'reduced', NAT)
add('20', _("Subject to VAT"), 'subject', NAT)
add('25', _("Co-contractor"), 'cocontractor', NAT)
add('30', _("Intra-community"), 'intracom', EU)
add('31', _("Delay in collection"), 'delayed', EU) # report de perception
add('40', _("Inside EU"), 'inside', EU)
add('50', _("Outside EU"), 'outside', INT)
add('60', _("Exempt"), 'exempt', item_vat=False)
if False:
    add('70', _("Germany"), 'de')
    add('71', _("Luxemburg"), 'lu')

VatColumns.clear()
add = VatColumns.add_item
add('00', _("Sales basis 0"))
add('01', _("Sales basis 1"))
add('02', _("Sales basis 2"))
add('03', _("Sales basis 3"))
add('54', _("VAT due"))
add('55', _("VAT returnable"))
add('59', _("VAT deductible"))
add('81', _("Purchase of goods"))
add('82', _("Purchase of services"))
add('83', _("Purchase of investments"))


VatRules.clear()
add = VatRules.add_item
# country_code = dd.plugins.countries.country_code
# if country_code == "BE":
add('010', 'normal',  '0.21', NAT, 'sales',     None,       CommonAccounts.vat_due)
add('020', 'reduced', '0.07', NAT, 'sales',     None,       CommonAccounts.vat_due)
add('030', 'normal',  '0.21', NAT, 'purchases', None,       CommonAccounts.vat_deductible)
add('040', 'reduced', '0.07', NAT, 'purchases', None,       CommonAccounts.vat_deductible)
add('050', 'normal',  '0.21', EU,  'purchases', 'intracom', CommonAccounts.vat_deductible, CommonAccounts.vat_returnable)
add('060', 'reduced', '0.07', EU,  'purchases', 'intracom', CommonAccounts.vat_deductible, CommonAccounts.vat_returnable)
add('070', 'normal',  '0.21', EU,  'sales',     'intracom', CommonAccounts.vat_due, CommonAccounts.vat_returnable)
add('080', 'reduced', '0.07', EU,  'sales',     'intracom', CommonAccounts.vat_due, CommonAccounts.vat_returnable)
add('900')

# if country_code == "EE":
#     add('010', 'normal', 'EE', None, '0.20')
#     add('010', 'reduced', 'EE', None, '0.09')

# if country_code == "NL":
#     add('010', 'normal', 'NL', None, '0.21')
#     add('010', 'reduced', 'NL', None, '0.06')

# if country_code == "DE":
#     add('010', 'normal', 'DE', None, '0.19')
#     add('010', 'reduced', 'DE', None, '0.07')

# if country_code == "FR":
#     add('010', 'normal', 'FR', None, '0.20')
#     add('010', 'reduced', 'FR', None, '0.10')
#     # in FR there are more VAT classes, we currently don't support them
#     # add('010', 'reduced', 'FR', None, None, '0.055')
#     # add('010', 'reduced', 'FR', None, None, '0.021')


class DeclarationFields(DeclarationFieldsBase):
    pass

# afld = DeclarationFields.add_account_field
sfld = DeclarationFields.add_sum_field
mfld = DeclarationFields.add_mvt_field
wfld = DeclarationFields.add_writable_field

# (II) sales base 
mfld("00", DEBIT, '00', _("Sales 0%"))
mfld("01", DEBIT, '01', _("Sales 6%"))
mfld("02", DEBIT, '02', _("Sales 12%"))
mfld("03", DEBIT, '03', _("Sales 20%"))
mfld("44", DEBIT, "00 01 02 03", _("Sales located inside EU"),
      vat_regimes="inside")
mfld("45", DEBIT, "00 01 02 03",  _("Sales to co-contractors"),
      vat_regimes="cocontractor")
mfld("46", DEBIT, "00 01 02 03", _("Sales intracom and ABC"),
      vat_regimes="intracom")
mfld("47", DEBIT, "00 01 02 03", _("Sales 47"),
      vat_regimes="intracom")
mfld("48", CREDIT, "00 01 02 03", _("CN sales 48"))
mfld("49", CREDIT, "00 01 02 03", _("CN sales 49"))

# (III) purchases base

mfld("81", CREDIT, '81', _("Ware"))
mfld("82", CREDIT, '82', _("Services"))
mfld("83", CREDIT, '83', _("Investments"))

mfld("84", DEBIT, "81 82 83", 
      _("CN purchases on operations in 86 and 88"),
      vat_regimes="intracom", both_dc=False)
mfld("85", DEBIT, "81 82 83", _("CN purchases on other operations"),
      vat_regimes="!intracom !delayed")
mfld("86", CREDIT, "81 82 83",
      _("IC purchases and ABC sales"), 
      vat_regimes="intracom")
mfld("87", CREDIT, "81 82 83", _("Other purchases in Belgium"),
      vat_regimes="cocontractor")
mfld("88", CREDIT, "81 82 83", _("IC services"),
      vat_regimes="delayed")

# (IV) DUE TAXES

mfld("54", DEBIT, '54', _("Due VAT for 01, 02 and 03"),
     vat_regimes="!intracom !delayed !cocontractor", is_payable=True)
mfld("55", DEBIT, '54', _("Due VAT for 86 and 88"),
     vat_regimes="intracom", is_payable=True)
mfld("56", DEBIT, '54',
      _("Due VAT for 87 except those covered by 57"),
     vat_regimes="cocontractor", is_payable=True)
mfld("57", DEBIT, '54',
      _("Due VAT for 87 except those covered by 57"),
      vat_regimes="delayed", is_payable=True)
wfld("61", DEBIT, None, _("Miscellaneous corrections due"),
     is_payable=True)

sfld("XX", DEBIT, None, _("Total of due taxes"),
     "54 55 56 57")

# (V) DEDUCTIBLE TAXES
# ...
mfld("59", DEBIT, '59', _("Deductible VAT from purchase invoices"),
     "81 82 83", is_payable=True)
wfld("62", DEBIT, None, _("Miscellaneous corrections deductible"),
     is_payable=True)
mfld("64", DEBIT, '59', _("VAT on sales CN"), is_payable=True)

sfld("YY", DEBIT, None, _("Total of deductible taxes"),
     "59 62 64")

# Actually only one of them
sfld("71", DEBIT, None, _("Total to pay"), "XX YY")
sfld("72", CREDIT, None, _("Total to pay"), "XX YY")

# print("20170711b {}".format(DeclarationFields.get_list_items()))
