# Copyright 2017 Luc Saffre
# License: BSD (see file COPYING for details)

"""Belgian VAT declaration fields.

Based on `165-625-directives-2016.pdf
<https://finances.belgium.be/sites/default/files/downloads/165-625-directives-2016.pdf>`__
and `finances.belgium.be
<https://finances.belgium.be/fr/entreprises/tva/declaration/declaration_periodique>`__

"""

from __future__ import unicode_literals

from lino.api import dd, rt, _
from from lino_xl.lib.bevat.choicelists import  DeclarationFields

