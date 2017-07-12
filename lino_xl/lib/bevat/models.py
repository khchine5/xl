# Copyright 2012-2017 Luc Saffre
# License: BSD (see file COPYING for details)


"""Database models for this plugin.

"""

from __future__ import unicode_literals

# from decimal import Decimal

# from django.db import models
# from django.conf import settings

from lino.api import dd, _

from lino_xl.lib.vat.mixins import VatDeclaration

# vat = dd.resolve_app('vat')
# ledger = dd.resolve_app('ledger')

# ZERO = Decimal()

from .choicelists import DeclarationFields

# print("20170711a {}".format(DeclarationFields.get_list_items()))

class Declaration(VatDeclaration):
    
    fields_list = DeclarationFields
    
    class Meta:
        app_label = 'bevat'
        verbose_name = _("Belgian VAT declaration")
        verbose_name_plural = _("Belgian VAT declarations")
        
# if dd.is_installed('declarations'): # avoid autodoc failure
#     # importing the country module will fill DeclarationFields
#     import_module(dd.plugins.declarations.country_module)

# dd.inject_field('ledger.Voucher',
#                 'declared_in',
#                 models.ForeignKey(Declaration,
#                                   blank=True, null=True))

# dd.inject_field('accounts.Account',
#                 'declaration_field',
#                 DeclarationFields.field(blank=True, null=True))

# dd.inject_field('ledger.Journal',
#                 'declared',
#                 models.BooleanField(default=True))

for fld in DeclarationFields.get_list_items():
    dd.inject_field('bevat.Declaration', fld.name, fld.get_model_field())

