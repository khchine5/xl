# -*- coding: UTF-8 -*-
# Copyright 2014-2017 Luc Saffre
#
# License: BSD (see file COPYING for details)
"""
Database models for this plugin.

"""

from __future__ import unicode_literals
from __future__ import print_function
import six

import logging
logger = logging.getLogger(__name__)

from os.path import join, dirname

import datetime
ONE_WEEK = datetime.timedelta(days=7)
ONE_DAY = datetime.timedelta(days=1)

from django.utils.translation import ugettext_lazy as _
from django.utils import translation
from django.conf import settings
from django.db import models
from django.db.utils import OperationalError, ProgrammingError
from django.db.models.signals import post_init
from django.contrib.contenttypes.models import ContentType
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
from django.core.exceptions import ValidationError

from lino.api import dd, rt ,gettext
from lino import mixins
from etgen.html import E
from lino.utils import join_elems
from lino.core.exceptions import UnresolvedChoice

from lino.modlib.gfks.mixins import Controllable
from lino.modlib.users.mixins import UserAuthored, My
from lino.modlib.users.choicelists import SiteAdmin
from lino.modlib.printing.mixins import PrintableType, TypedPrintable

davlink = settings.SITE.plugins.get('davlink', None)
has_davlink = davlink is not None and settings.SITE.use_java

from lino_xl.lib.postings.mixins import Postable
from lino_xl.lib.contacts.mixins import ContactRelated
from lino_xl.lib.outbox.mixins import Mailable, MailableType

from lino.modlib.office.roles import OfficeStaff, OfficeOperator

from .mixins import Certifiable
from .choicelists import Shortcuts
from .roles import ExcerptsUser, ExcerptsStaff


class ExcerptType(mixins.BabelNamed, PrintableType, MailableType):
    """The type of an excerpt. Every excerpt has a mandatory field
    :attr:`Excerpt.excerpt_type` which points to an :class:`ExcerptType`
    instance.
    
    .. attribute:: name

        The designation of this excerpt type.
        One field for every :attr:`language <lino.core.site.Site.language>`.

    .. attribute:: content_type

        The database model for which this excerpt type is to be used.

    .. attribute:: build_method

        See :attr:`lino.modlib.printing.mixins.PrintableType.build_method`.

    .. attribute:: template
 
        The main template to be used when printing an excerpt of this type.

    .. attribute:: body_template

        The body template to use when printing an excerpt of this type.

    .. attribute:: email_template

        The template to use when sending this an excerpt of this type
        by email.

    .. attribute:: shortcut

        Optional pointer to a shortcut field.  If this is not empty, then
        the given shortcut field will manage excerpts of this type.

        See also :class:`Shortcuts`.
        See also :class:`lino_xl.lib.excerpts.choicelists.Shortcuts`.

    """
    # templates_group = 'excerpts/Excerpt'

    class Meta:
        app_label = 'excerpts'
        abstract = dd.is_abstract_model(__name__, 'ExcerptType')
        verbose_name = _("Excerpt Type")
        verbose_name_plural = _("Excerpt Types")

    certifying = models.BooleanField(
        verbose_name=_("Certifying"),
        default=False,
        help_text=_("Whether an excerpt of this type is a unique printout."))

    remark = models.TextField(verbose_name=_("Remark"), blank=True)

    body_template = models.CharField(
        max_length=200,
        verbose_name=_("Body template"),
        blank=True, help_text="The body template to be used when \
        rendering a printable of this type. This is a list of files \
        with extension `.body.html`.")

    content_type = dd.ForeignKey(
        'contenttypes.ContentType',
        verbose_name=_("Model"),
        related_name='excerpt_types',
        # null=True, blank=True,
        help_text=_("The model that can issue printouts of this type."))
    """The model on which excerpts of this type are going to work."""

    primary = models.BooleanField(
        _("Primary"),
        default=False,
        help_text=_(
            "Whether this is the default type to use for this model. "
            "There's at most one primary type per model. "
            "Enabling this field will automatically make the other "
            "types non-primary."))

    backward_compat = models.BooleanField(
        _("Backward compatible"),
        default=False,
        help_text=_("Check this to have `this` in template context "
                    "point to owner instead of excerpt."))

    print_recipient = models.BooleanField(
        _("Print recipient"),
        default=True,
        help_text=_("Whether to print a recipient field in document."))

    print_directly = models.BooleanField(_("Print directly"), default=True)

    shortcut = Shortcuts.field(blank=True)

    def unused_full_clean(self, *args, **kwargs):
        if self.certifying:
            if not self.primary:
                raise ValidationError(
                    _("Cannot set %(c)s without %(p)s") % dict(
                        c=_("Certifying"), p=_("Primary")))
            mc = self.content_type.model_class()
            if not issubclass(mc, Certifiable):
                raise ValidationError(
                    _("Cannot set %(c)s for non.certifiable "
                      "model %(m)s") % dict(
                        c=_("Certifying"), m=mc._meta.verbose_name))
        super(ExcerptType, self).full_clean(*args, **kwargs)

    def update_siblings(self):
        updated = 0
        if self.primary:
            for o in self.content_type.excerpt_types.exclude(id=self.id):
                if o.primary:
                    o.primary = False
                    o.save()
                    updated += 1
        return updated

    def save(self, *args, **kwargs):
        # It is important to ensure that there is really only one
        # primary ExcerptType per model because
        # :func:`set_excerpts_actions` will install these as action on
        # the model.
        super(ExcerptType, self).save(*args, **kwargs)
        self.update_siblings()

    def after_ui_save(self, ar, cw):
        super(ExcerptType, self).after_ui_save(ar, cw)
        if self.primary:
            ar.set_response(refresh_all=True)

    @classmethod
    def get_template_groups(cls):
        raise Exception("""Not used by ExcerptType. \
We override everything in Excerpt to not call the class method.""")

    @dd.chooser(simple_values=True)
    def template_choices(cls, build_method, content_type):
        tplgroups = [
            content_type.model_class().get_template_group(), 'excerpts']
        return cls.get_template_choices(build_method, tplgroups)

    @dd.chooser(simple_values=True)
    def body_template_choices(cls, content_type):
        # 20140617 don't remember why the "excerpts" group was useful here
        # tplgroups = [model_group(content_type.model_class()), 'excerpts']
        # return dd.plugins.jinja.list_templates('.body.html', *tplgroups)

        tplgroup = content_type.model_class().get_template_group()
        return dd.plugins.jinja.list_templates('.body.html', tplgroup, 'excerpts')

    @dd.chooser(simple_values=True)
    def email_template_choices(cls, content_type):
        tplgroup = content_type.model_class().get_template_group()
        return dd.plugins.jinja.list_templates('.eml.html', tplgroup, 'excerpts')

    @classmethod
    def get_for_model(cls, model):
        "Return the primary ExcerptType for the given model."
        ct = ContentType.objects.get_for_model(dd.resolve_model(model))
        return cls.objects.get(primary=True, content_type=ct)

    @classmethod
    def update_for_model(cls, model, **kw):
        obj = cls.get_for_model(model)
        for k, v in kw.items():
            setattr(obj, k, v)
        # obj.full_clean()
        # obj.save()
        return obj

    def get_or_create_excerpt(self, ar):
        obj = ar.selected_rows[0]
        model = self.content_type.model_class()
        if not isinstance(obj, model):
            raise Exception("%s is not an instance of %s" % (obj, model))
        Excerpt = rt.models.excerpts.Excerpt
        ex = None
        if self.certifying:
            qs = Excerpt.objects.filter(
                excerpt_type=self,
                owner_id=obj.pk,
                owner_type=ContentType.objects.get_for_model(obj.__class__))
            qs = qs.order_by('id')
            if qs.count() > 0:
                if isinstance(obj, Certifiable):
                    ex = qs[0]
                else:
                    qs.delete()
                    # Otherwise end-users would have no possibility to
                    # clear the cache, which means that they would get
                    # always the first version of a printed document.
        if ex is None:
            akw = dict(
                user=ar.get_user(),
                owner=obj,
                excerpt_type=self)
            akw = obj.get_excerpt_options(ar, **akw)
            ex = Excerpt(**akw)
            ex.on_create(ar)
            ex.full_clean()
            ex.save()

        if self.certifying and isinstance(obj, Certifiable):
            obj.printed_by = ex
            obj.full_clean()
            obj.save()

        return ex

    def get_action_name(self):
        if self.primary:
            return 'do_print'
        else:
            return 'create_excerpt' + str(self.pk)

    @dd.displayfield(_("Model"))
    def content_type_display(self, ar):
        if ar is None:
            return ''
        model = self.content_type.model_class()
        label = "{0} ({1})".format(
            dd.full_model_name(model), model._meta.verbose_name)
        return ar.obj2html(self.content_type, label)


class ExcerptTypes(dd.Table):
    """
    Displays all rows of :class:`ExcerptType`.
    """
    model = 'excerpts.ExcerptType'
    required_roles = dd.login_required(ExcerptsStaff)
    column_names = ("content_type_display primary certifying name "
                    "build_method  template body_template *")
    order_by = ["content_type__app_label", "content_type__model", "name"]

    insert_layout = """
    name
    content_type primary certifying
    build_method template body_template
    """

    detail_layout = """
    id name
    content_type:15 build_method:15 template:15 \
      body_template:15 email_template:15 shortcut
    primary print_directly certifying print_recipient \
      backward_compat attach_to_email
    # remark:60x5
    excerpts.ExcerptsByType
    """

    @classmethod
    def get_choices_text(self, obj, request, field):
        if field.name == 'content_type':
            return "%s (%s)" % (
                dd.full_model_name(obj.model_class()),
                obj)
        return obj.get_choices_text(request, self, field)


class CreateExcerpt(dd.Action):
    """Create an excerpt in order to print this data record.
    """
    icon_name = 'printer'
    label = _('Print')
    sort_index = 50  # like "Print"
    combo_group = "creacert"

    def __init__(self, etype, *args, **kwargs):
        self.excerpt_type = etype
        super(CreateExcerpt, self).__init__(*args, **kwargs)

    def run_from_ui(self, ar, **kw):
        et = self.excerpt_type
        ex = et.get_or_create_excerpt(ar)
        # logger.info(
        #     "20180114 excerpts.CreateExcerpt %s, %s",
        #     et, et.print_directly)
        if et.print_directly:
            ex.do_print.run_from_ui(ar, **kw)
        else:
            ar.goto_instance(ex)


class BodyTemplateContentField(dd.VirtualField):

    editable = True

    def __init__(self, *args, **kw):
        if settings.SITE.confdirs.LOCAL_CONFIG_DIR is None:
            self.editable = False  # No local config dir
        rt = dd.RichTextField(*args, **kw)
        dd.VirtualField.__init__(self, rt, None)

    def value_from_object(self, obj, ar):
        fn = obj.get_body_template_filename()
        if not fn:
            return "(%s)" % _(
                "Excerpt type \"%s\" has no body_template") % obj.excerpt_type
        if six.PY2:
            return open(fn).read().decode('utf8')
        else:
            return open(fn).read()

    def set_value_in_object(self, ar, obj, value):
        if ar is None or value is None:
            return
        fn = obj.get_body_template_name()
        if not fn:
            return
            # raise Warning(
            #     "No `body_template_name` while saving to %s" % dd.obj2str(obj))

        lcd = settings.SITE.confdirs.LOCAL_CONFIG_DIR
        if lcd is None:
            # raise Warning("No local config directory. "
            #               "Contact your system administrator.")
            return
        local_file = join(lcd.name, fn)
        settings.SITE.makedirs_if_missing(dirname(local_file))
        value = value.encode('utf-8')
        logger.info("Wrote body_template_content %s", local_file)
        open(local_file, "w").write(value)

##
##


@dd.python_2_unicode_compatible
class Excerpt(TypedPrintable, UserAuthored,
              Controllable, mixins.ProjectRelated,
              ContactRelated, Mailable, Postable):
    """A printable document that describes some aspect of the current
    situation.

    .. attribute:: excerpt_type

        The type of this excerpt (ForeignKey to :class:`ExcerptType`).

    .. attribute:: owner

      The object being printed by this excerpt.
      See :attr:`Controllable.owner
      <lino.modlib.gfks.mixins.Controllable.owner>`.

    .. attribute:: company

      The optional company of the :attr:`recipient` of this
      excerpt.  See :attr:`ContactRelated.company
      <lino_xl.lib.contacts.mixins.ContactRelated.company>`.

    .. attribute:: contact_person

      The optional contact person of the :attr:`recipient` of this
      excerpt.  See :attr:`ContactRelated.contact_person
      <lino_xl.lib.contacts.mixins.ContactRelated.contact_person>`.

    .. attribute:: recipient

      The recipient of this excerpt.  See
      :attr:`ContactRelated.recipient
      <lino_xl.lib.contacts.mixins.ContactRelated.recipient>`

    .. attribute:: language

      The language used for printing this excerpt.

    .. attribute:: date

    .. attribute:: time

    .. method:: get_address_html

        See
        :meth:`lino_xl.lib.contacts.mixins.ContactRelated.get_address_html`.

        Return the address of the :attr:`recipient` of this excerpt.

    """

    manager_roles_required = dd.login_required(OfficeStaff)
    # manager_level_field = 'office_level'
    allow_cascaded_delete = "owner"

    class Meta:
        app_label = 'excerpts'
        abstract = dd.is_abstract_model(__name__, 'Excerpt')
        verbose_name = _("Excerpt")
        verbose_name_plural = _("Excerpts")

    excerpt_type = dd.ForeignKey('excerpts.ExcerptType')

    body_template_content = BodyTemplateContentField(_("Body template"))

    language = dd.LanguageField()

    # if dd.is_installed('outbox'):
    #     mails_by_owner = dd.ShowSlaveTable('outbox.MailsByController')

    def get_body_template(self):
        """Return the body template to use for this excerpt."""
        owner = self.owner
        # owner is None e.g. if is a broken GFK
        if owner is not None:
            assert self.__class__ is not owner.__class__
            tplname = owner.get_body_template()
            if tplname:
                return tplname
        return self.excerpt_type.body_template

    def get_body_template_filename(self):
        tplname = self.get_body_template()
        if not tplname:
            return None
        mc = self.excerpt_type.content_type.model_class()
        tplgroup = mc.get_template_group()
        return rt.find_config_file(tplname, tplgroup)

    def get_body_template_name(self):
        tplname = self.get_body_template()
        if not tplname:
            return None
        mc = self.excerpt_type.content_type.model_class()
        tplgroup = mc.get_template_group()
        return tplgroup + '/' + tplname

    def disabled_fields(self, ar):
        rv = super(Excerpt, self).disabled_fields(ar)
        rv = rv | set(['excerpt_type', 'project'])
        if self.build_time:
            rv |= self.PRINTABLE_FIELDS
        return rv

    def __str__(self):
        if self.build_time:
            return naturaltime(self.build_time)
            # return _("%(owner)s (printed %(time)s)") % dict(
            #     owner=self.owner, time=naturaltime(self.build_time))
        return _("Unprinted %s #%s") % (self._meta.verbose_name, self.pk)

    def get_mailable_type(self):
        return self.excerpt_type

    def get_mailable_subject(self):
        return six.text_type(self.owner)  # .get_mailable_subject()

    def get_template_groups(self):
        ptype = self.get_printable_type()
        if ptype is None:
            raise Exception("20140520 Must have excerpt_type.")
        grp = ptype.content_type.model_class().get_template_group()
        return [grp, 'excerpts']

    def filename_root(self):
        # mainly because otherwise we would need to move files around on
        # existing sites
        et = self.excerpt_type
        if et is None or not et.certifying:
            return super(Excerpt, self).filename_root()
        assert et.certifying
        o = self.owner
        if o is None:
            return super(Excerpt, self).filename_root()
        name = o._meta.app_label + '.' + o.__class__.__name__
        if not et.primary:
            name += '.' + str(et.pk)
        name += '-' + str(o.pk)
        return name

    def get_print_templates(self, bm, action):
        """Overrides
        :meth:`lino.modlib.printing.mixins.Printable.get_print_templates`.

        When printing an excerpt, the controlling database objects
        gets a chance to decide which template to use.

        """
        et = self.excerpt_type
        if et is not None and et.certifying:
            if isinstance(self.owner, Certifiable):
                tpls = self.owner.get_excerpt_templates(bm)
                if tpls is not None:
                    return tpls
        return super(Excerpt, self).get_print_templates(bm, action)
        # ptype = self.get_printable_type()
        # # raise Exception("20150710 %s" % self.owner)
        # if ptype is not None and ptype.template:
        #     return [ptype.template]
        # # return [bm.get_default_template(self)]
        # return [dd.plugins.excerpts.get_default_template(bm, self.owner)]

    # def get_recipient(self):
    #     rec = super(Excerpt, self).get_recipient()
    #     if rec is None and hasattr(self.owner, 'recipient'):
    #         return self.owner.recipient
    #     return rec

    # recipient = property(get_recipient)
        
    def get_printable_type(self):
        return self.excerpt_type

    def get_print_language(self):
        return self.language

    @dd.chooser()
    def excerpt_type_choices(cls, owner):
        # logger.info("20150702 %s", owner)
        qs = rt.models.excerpts.ExcerptType.objects.order_by('name')
        if owner is None:
            # e.g. when choosing on the *parameter* field
            # return qs.filter(content_type__isnull=True)
            return qs.filter()
        ct = ContentType.objects.get_for_model(owner.__class__)
        return qs.filter(content_type=ct)

    @property
    def date(self):
        "Used in templates"
        if self.build_time:
            return self.build_time.date()
        return dd.today()

    @property
    def time(self):
        "Used in templates"
        if self.build_time:
            return self.build_time.time()
        return timezone.now()

    @dd.virtualfield(dd.HtmlBox(_("Preview")))
    def preview(self, ar):
        if ar is None:
            return ''
        lang = self.get_print_language() or \
               settings.SITE.DEFAULT_LANGUAGE.django_code
        with translation.override(lang):
            ctx = self.get_printable_context(ar)
            return ar.html_text(ctx['body'])
            # return '<div class="htmlText">%s</div>' % ctx['body']

    def before_printable_build(self, bm):
        super(Excerpt, self).before_printable_build(bm)
        if self.owner is not None:
            return self.owner.before_printable_build(bm)
        
    def get_printable_context(self, ar=None, **kw):
        """Adds a series of names to the context used when rendering printable
        documents.  Extends
        :meth:`lino.core.model.Model.get_printable_context`.

        """
        if self.owner is not None:
            kw = self.owner.get_printable_context(ar, **kw)
        kw = super(Excerpt, self).get_printable_context(**kw)
        kw.update(obj=self.owner)
        kw.update(excerpt=self)
        body = ''
        # logger.info("20180114 get_printable_context() %s", self)
        if self.excerpt_type_id is not None:
            etype = self.excerpt_type
            if etype.backward_compat:
                kw.update(this=self.owner)

            tplname = self.get_body_template_name()
            # logger.info("20180114 tplname is %s -",
            #             tplname)
            if tplname and ar is not None:
                body = settings.SITE.plugins.jinja.render_jinja(
                    ar, tplname, kw)
            
                # env = settings.SITE.plugins.jinja.renderer.jinja_env
                # template = env.get_template(tplname)
                # # logger.info("body template %s (%s)", tplname, template)
                # body = ar.render_jinja(template, **kw)
                # logger.info("20160311 body template %s -> %s",
                #             tplname, body)

        kw.update(body=body)
        return kw

    @classmethod
    def on_analyze(cls, site):
        cls.PRINTABLE_FIELDS = dd.fields_list(
            cls,
            "project excerpt_type  "
            "body_template_content "
            "company contact_person language "
            "user build_method")
        super(Excerpt, cls).on_analyze(site)


#TODO: why not use full_clean() for the following?        
@dd.receiver(post_init, sender=Excerpt)
def post_init_excerpt(sender, instance=None, **kwargs):
    """This is called for every new Excerpt object and it sets certain
    default values.

    For the default language, note that the :attr:`owner` overrides
    the :attr:`recipient`. This rule is important e.g. for printing
    aid confirmations in Lino Welfare.

    """
    self = instance
    if not self.owner_id:
        # When creating an Excerpt by double-clicking in
        # ExcerptsByProject, then the `project` field gets filled
        # automatically, but we also want to set the `owner` field to
        # the project.
        if self.project_id:
            self.owner = self.project

    # if isinstance(self.owner, ContactRelated):
    #     self.company = self.owner.company
    #     self.contact_person = self.owner.contact_person
    #     self.contact_role = self.owner.contact_role
    #     # print("on_create 20150212", self)

    if not self.language:
        if self.owner_id and self.owner:  # owner might still be None
                                          # if it is a broken GFK
            self.language = self.owner.get_print_language()
        if not self.language:
            rec = self.recipient
            if rec is not None:
                self.language = rec.get_print_language()
        if not self.language:
            self.language = settings.SITE.DEFAULT_LANGUAGE.django_code


if has_davlink or settings.SITE.webdav_protocol:

    class ExcerptDetail(dd.DetailLayout):
        # window_size = (80, 20)
        window_size = (80, 'auto')
        main = "general config"
        general = dd.Panel(
            """
            id excerpt_type:25 project
            user:10 build_method
            company contact_person language
            owner build_time
            # outbox.MailsByController
            """, label=_("General"))
        config = dd.Panel(
            "body_template_content",
            label=_("Configure"),
            required_roles=dd.login_required(SiteAdmin))

else:

    class ExcerptDetail(dd.DetailLayout):
        # window_size = (80, 20)
        window_size = (80, 'auto')
        main = """
        id excerpt_type:25 project
        user:10 build_method
        company contact_person language
        owner build_time
        # outbox.MailsByController
        """

if dd.is_installed('contacts'):

    dd.update_field(Excerpt, 'company',
                    verbose_name=_("Recipient (Organization)"))
    dd.update_field(Excerpt, 'contact_person',
                    verbose_name=_("Recipient (Person)"))


class Excerpts(dd.Table):
    """Base class for all tables on :class:`Excerpt`."""
    # label = _("Excerpts history")
    icon_name = 'script'
    required_roles = dd.login_required((ExcerptsUser, OfficeOperator))

    model = 'excerpts.Excerpt'
    detail_layout = ExcerptDetail()
    insert_layout = """
    excerpt_type project
    company contact_person
    """
    column_names = ("id excerpt_type owner project "
                    "company language build_time *")
    # order_by = ['-build_time', 'id']
    order_by = ['-id']
    auto_fit_column_widths = True
    allow_create = False

    parameters = mixins.ObservedDateRange(
        excerpt_type=dd.ForeignKey(
            'excerpts.ExcerptType', blank=True, null=True),
        pcertifying=dd.YesNo.field(_("Certifying excerpts"), blank=True))
    params_layout = """
    start_date end_date pcertifying
    user excerpt_type"""

    # simple_parameters = ['user', 'excerpt_type']

    @classmethod
    def get_simple_parameters(cls):
        s = list(super(Excerpts, cls).get_simple_parameters())
        s.append('excerpt_type')
        return s

    @classmethod
    def get_request_queryset(cls, ar):
        qs = super(Excerpts, cls).get_request_queryset(ar)
        pv = ar.param_values

        if pv.pcertifying == dd.YesNo.yes:
            qs = qs.filter(excerpt_type__certifying=True)
        elif pv.pcertifying == dd.YesNo.no:
            qs = qs.filter(excerpt_type__certifying=False)

        return qs


# class ExcerptsByX(Excerpts):
    # window_size = (70, 20)


class AllExcerpts(Excerpts):
    required_roles = dd.login_required(ExcerptsStaff)
    column_names = ("id excerpt_type owner project "
                    "company language build_time *")


class MyExcerpts(My, Excerpts):
    column_names = "build_time excerpt_type project *"
    order_by = ['-build_time', 'id']


class ExcerptsByType(Excerpts):
    master_key = 'excerpt_type'
    column_names = "build_time owner project user *"
    order_by = ['-build_time', 'id']

            
class ExcerptsByOwner(Excerpts):
    """Shows all excerpts whose :attr:`owner <Excerpt.owner>` field is
    this.

    """
    
    master_key = 'owner'
    help_text = _("History of excerpts based on this data record.")
    label = _("Existing excerpts")
    column_names = "build_time excerpt_type user project *"
    order_by = ['-build_time', 'id']
    display_mode = 'summary'
    auto_fit_column_widths = True
    MORE_LIMIT = 5

    @classmethod
    def get_table_summary(self, obj, ar):
        items = []

        def add(title, flt):
            links = []
            sar = self.request(master_instance=obj, filter=flt)
            # logger.info("20141009 %s", sar.data_iterator.query)
            n = sar.get_total_count()
            if n:
                for i, ex in enumerate(sar):
                    txt = self.format_excerpt(ex)
                    if ex.build_time is not None:
                        txt += " (%s)" % naturaltime(ex.build_time)
                    links.append(ar.obj2html(ex, txt))
                    if i >= self.MORE_LIMIT:
                        # links.append(ar.href_to_request(sar, _("more")))
                        links.append('...')
                        break

                items.append(E.li(title, " : ", *join_elems(links, sep=', ')))

        # qs = sar.data_iterator
        Q = models.Q
        add(gettext("not printed"), Q(build_time__isnull=True))
        add(gettext("Today"), Q(build_time__gte=dd.today() - ONE_DAY))
        t7 = dd.today() - ONE_WEEK
        add(gettext("Last week"),
            Q(build_time__lte=dd.today(), build_time__gte=t7))
        add(gettext("Older"), Q(build_time__lt=t7))
        return E.ul(*items)

    @classmethod
    def format_excerpt(self, ex):
        return six.text_type(ex.excerpt_type)


if settings.SITE.project_model is None:

    class ExcerptsByProject(object):
        pass
        # needed for building blog
        
else:
    
    class ExcerptsByProject(ExcerptsByOwner):
        master_key = 'project'
        column_names = "build_time excerpt_type user owner *"
        order_by = ['-build_time', 'id']

        @classmethod
        def format_excerpt(self, ex):
            if ex.owner == ex.project:
                return six.text_type(ex.excerpt_type)
            return six.text_type(ex.owner)


@dd.receiver(dd.pre_analyze)
def set_excerpts_actions(sender, **kw):
    """
    Installs (1) print management actions on models for which there is
    an excerpt type and (2) the excerpt shortcut fields defined in
    :class:`lino_xl.lib.excerpts.choicelists.Shortcuts`.

    Note that excerpt types for a model with has MTI children, the
    action will be installed on children as well.  For example a
    :class:`lino_avanti.lib.avanti.Client` in
    :mod:`lino_book.projects.adg` can get printed either as a
    :xfile:`TermsConditions.odt` or as a :xfile:`final
    report.body.html`.

    """
    # logger.info("20180114 %s.set_excerpts_actions()", __name__)
    # in case ExcerptType is overridden
    ExcerptType = sender.modules.excerpts.ExcerptType
    Excerpt = sender.modules.excerpts.Excerpt

    try:
        etypes = [(obj, obj.content_type)
                  for obj in ExcerptType.objects.all()]
    except (OperationalError, ProgrammingError, UnresolvedChoice) as e:
        dd.logger.debug("Failed to set excerpts actions : %s", e)
        # Happens e.g. when the database has not yet been migrated
        etypes = []

    for atype, ct in etypes:
        if ct is not None:
            bm = ct.model_class()
            if bm is None:
                # e.g. database contains types for models that existed
                # before but have been removed
                continue
            for m in rt.models_by_base(bm):
                an = atype.get_action_name()
                if not hasattr(m, an):
                    m.define_action(**{an: CreateExcerpt(
                        atype, six.text_type(atype))})
                # dd.logger.info("Added print action to %s", m)

                # if atype.certifying and not issubclass(m, Certifiable):
                #     m.define_action(
                #         clear_printed=ClearCache())

    # An attestable model must also inherit
    # :class:`lino.mixins.printable.BasePrintable` or some subclass
    # thereof.

    for i in Shortcuts.items():

        def f(obj, ar):
            if ar is None:
                return ''
            if obj is None:
                return E.div()
            try:
                et = ExcerptType.objects.get(shortcut=i)
            except ExcerptType.DoesNotExist:
                return E.div()
            items = []
            if True:
                sar = ar.spawn(
                    ExcerptsByOwner,
                    master_instance=obj,
                    param_values=dict(excerpt_type=et))
                n = sar.get_total_count()
                if n > 0:
                    ex = sar.sliced_data_iterator[0]
                    items.append(ar.obj2html(ex, _("Last")))

                    ba = sar.bound_action
                    btn = sar.renderer.action_button(
                        obj, sar, ba, "%s (%d)" % (_("All"), n),
                        icon_name=None)
                    items.append(btn)
    
                ia = getattr(obj, et.get_action_name())
                btn = ar.instance_action_button(
                    ia, _("Create"), icon_name=None)
                items.append(btn)

            else:
                ot = ContentType.objects.get_for_model(obj.__class__)
                qs = Excerpt.objects.filter(
                    owner_id=obj.pk, owner_type=ot, excerpt_type=et)
                if qs.count() > 0:
                    ex = qs[0]
                    txt = ExcerptsByOwner.format_excerpt(ex)
                    items.append(ar.obj2html(ex, txt))
            return E.div(*join_elems(items, ', '))
    
        vf = dd.VirtualField(dd.DisplayField(i.text), f)
        dd.inject_field(i.model_spec, i.name, vf)


