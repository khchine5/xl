# -*- coding: UTF-8 -*-
# Copyright 2012-2018 Rumma & Ko Ltd
#
# License: BSD (see file COPYING for details)
"""
Read Belgian eID cards and store that data in the database.

"""

# When this plugin is installed, you can still easily disable it by
# setting :attr:`use_java <lino.core.site.Site.use_java>` to `False`
# in your :xfile:`settings.py`.

# When this plugin is activated, then you must also add the `.jar` files
# required by :ref:`eidreader` into your media directory, in a
# subdirectory named "eidreader".  TODO: move :ref:`eidreader` to a
# `static` directory in the Lino repository.

# An (untested) alternative implementation of the same functionality is
# :mod:`lino_xl.lib.eid_jslib.beid` which overrides this plugin and does
# the same except that it uses `eidjslib` instead of :ref:`eidreader`.


from os.path import join
from lino.api import ad, _


class Plugin(ad.Plugin):  # was: use_eidreader
    """See :class:`lino.core.Plugin`.

    .. attribute:: holder_model

        The one and only model on this site which implements
        :class:`BeIdCardHolder`.

        This is available only after site startup.

    .. attribute:: data_collector_dir

        When this is a non-empty string containing a directory name on the
        server, then Lino writes the raw data of every eid card into a
        text file in this directory.

    .. attribute:: read_only_simulate

        Whether to just simulate.

    """

    site_js_snippets = ['beid/eidreader.js']
    media_name = 'eidreader'
    data_collector_dir = None
    data_cache_dir = None
    eidreader_timeout = 15
    read_only_simulate = False

    def on_site_startup(self, kernel):
        
        from lino_xl.lib.beid.mixins import BeIdCardHolder
        from lino.core.utils import models_by_base

        super(Plugin, self).on_site_startup(kernel)

        if self.data_cache_dir is None:
            self.data_cache_dir = self.site.cache_dir.child('media').child('cache').child('beid')
            # self.data_cache_dir = join(
            #     self.site.cache_dir, 'media', 'beidtmp')
        self.site.makedirs_if_missing(self.data_cache_dir)
        
        cmc = list(models_by_base(BeIdCardHolder, toplevel_only=True))
        if len(cmc) == 1:
            self.holder_model = cmc[0]
            return
        if len(cmc) == 0:
            self.site.logger.warning(
                "You have lino_xl.lib.beid installed, "
                "but there is no implementation of BeIdCardHolder.")
            return
        msg = "There must be exactly one BeIdCardHolder model " \
              "in your Site! You have {}. ".format(cmc)
        # from django.apps import apps
        # msg += "\nYour models are:\n {}".format(
        #     '\n'.join([str(m) for m in apps.get_models()]))
        # from django.conf import settings
        # msg += "\nYour plugins are:\n {}".format(settings.INSTALLED_APPS)
        # [p.app_label
        #       for p in self.site.installed_plugins]))
        raise Exception(msg)

        
    def get_body_lines(self, site, request):
        if not site.use_java:
            return
        if site.beid_protocol:
            return
        # p = self.build_media_url('EIDReader.jar')
        # p = self.build_media_url('eidreader.jnlp')
        p = self.build_lib_url()
        p = request.build_absolute_uri(p)
        yield '<applet name="EIDReader" code="src.eidreader.EIDReader.class"'
        # yield '        archive="%s"' % p
        yield '        codebase="%s">' % p
        # seems that you may not use another size than
        # yield '        width="0" height="0">'
        # ~ yield '<param name="separate_jvm" value="true">' # 20130913
        yield '<param name="permissions" value="all-permissions">'
        # yield '<param name="jnlp_href" value="%s">' % p
        yield '<param name="jnlp_href" value="eidreader.jnlp">'
        yield '</applet>'

    def get_patterns(self):
        from django.conf.urls import url
        from . import views
        urls = [ url('^eid/(?P<uuid>.+)', views.EidStore.as_view()) ]
        return urls

