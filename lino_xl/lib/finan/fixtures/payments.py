# -*- coding: UTF-8 -*-
# Copyright 2012-2017 Luc Saffre
# License: BSD (see file COPYING for details)


"""Creates fictive demo bookings to monthly payment orders and bank
statements.  Bank statements of last month are not yet entered into
database

Used e.g. in :mod:`lino_book.projects.apc`.

"""

from __future__ import unicode_literals

import datetime
from dateutil.relativedelta import relativedelta as delta

from decimal import Decimal
from unipath import Path

from django.conf import settings
from lino.utils import Cycler
from lino.api import dd, rt
from etgen.sepa.validate import validate_pain001
from lino_xl.lib.sepa.fixtures.sample_ibans import IBANS

finan = dd.resolve_app('finan')

REQUEST = settings.SITE.login()  # BaseRequest()
MORE_THAN_A_MONTH = datetime.timedelta(days=40)

# most payments are arriving as suggested, i.e. the customer pays the
# full ammount. But there are exceptions: 5% discount taken at
# payment, no payment a t all, partly payments of 70%, or (very
# accidentally) 2% too much.

PAYMENT_DIFFS = [None] * 4
PAYMENT_DIFFS += [-0.05]
PAYMENT_DIFFS += [None] * 3
PAYMENT_DIFFS += [-1.00]
PAYMENT_DIFFS += [None] * 2
PAYMENT_DIFFS += [-0.30]
PAYMENT_DIFFS += [0.02]
PAYMENT_DIFFS = Cycler(PAYMENT_DIFFS)

IBAN_CYCLERS = dict()

def add_demo_account(partner):
    # raise Exception("20171009")
    if partner.country is None:
        return None
    Account = rt.models.sepa.Account
    qs = Account.objects.filter(partner=partner)
    acct = qs.first()
    if acct is None:
        ibans = IBAN_CYCLERS.get(partner.country)
        if ibans is None:
            ibans = Cycler([
                x for x in IBANS if x.startswith(
                    partner.country.isocode)])
            IBAN_CYCLERS[partner.country] = ibans
        acct = Account(partner=partner, iban=ibans.pop(), primary=True)
        acct.bic = "BBRUBEBB"
        acct.full_clean()
        acct.save()
    return acct

def objects(refs="PMO BNK"):

    Journal = rt.models.ledger.Journal
    Company = rt.models.contacts.Company
    
    USERS = Cycler(settings.SITE.user_model.objects.all())
    OFFSETS = Cycler(12, 20, 28)

    START_YEAR = dd.plugins.ledger.start_year
    end_date = settings.SITE.demo_date(-30)
    site_company = settings.SITE.site_config.site_company

    ses = rt.login('robin')

    qs = Company.objects.filter(country__isnull=False)
    # if qs.count() < 10:
    #     raise Exception("20171009")
    for p in qs:
        add_demo_account(p)


    for ref in refs.split():
        # if ref == 'BNK':
        #     continue  # temp 20171007
        jnl = Journal.objects.get(ref=ref)
        sug_table = jnl.voucher_type.table_class.suggestions_table
        if ref == 'PMO':
            assert site_company is not None
            if site_company.country is None:
                raise Exception(
                    "Oops, site company {} has no country".format(
                        site_company))

            acct = add_demo_account(site_company)
            jnl.sepa_account = acct
            yield jnl
            
        offset = OFFSETS.pop()
        date = datetime.date(START_YEAR, 1, 1)
        while date < end_date:
            voucher = jnl.create_voucher(
                user=USERS.pop(),
                entry_date=date + delta(days=offset))
            yield voucher

            # start action request for do_fill:
            ba = sug_table.get_action_by_name('do_fill')
            ar = ba.request(master_instance=voucher)
            # select all rows:
            suggestions = sug_table.request(voucher)
            ar.selected_rows = list(suggestions)
            # run the action:
            ar.run()

            # some items differ from what was suggested:
            if ref == 'BNK':
                for item in voucher.items.all():
                    pd = PAYMENT_DIFFS.pop()
                    if pd:
                        pd = Decimal(pd)
                        item.amount += item.amount * pd
                        if item.amount:
                            item.save()
                        else:
                            item.delete()
            # if no items have been created (or if they have been
            # deleted by PAYMENT_DIFFS), remove the empty voucher:
            if voucher.items.count() == 0:
                voucher.delete()
            else:
                # if ref == 'PMO':
                #     voucher.execution_date = voucher.entry_date
                #     assert voucher.execution_date is not None
                voucher.register(REQUEST)
                voucher.save()

                # For payment orders we also write the XML file
                if ref == 'PMO':
                    rv = voucher.write_xml.run_from_session(ses)
                    if not rv['success']:
                        raise Exception("20170630")
                    if False:
                        # not needed here because write_xml validates
                        fn = Path(settings.SITE.cache_dir + rv['open_url'])
                        if not fn.exists():
                            raise Exception("20170630")
                        validate_pain001(fn)

            date += delta(months=1)
        # JOURNAL_BANK = Journal.objects.get(ref="BNK")
        # bs = JOURNAL_BANK.create_voucher(
        #     user=USERS.pop(),
        #     date=date + delta(days=28))
        # yield bs
        # suggestions = finan.SuggestionsByBankStatement.request(bs)
        # ba = suggestions.actor.get_action_by_name('do_fill')
        # ar = ba.request(master_instance=bs)
        # ar.selected_rows = [x for x in suggestions]
        # ar.run()
        # bs.register(REQUEST)
        # bs.save()

