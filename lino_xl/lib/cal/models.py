# -*- coding: UTF-8 -*-
# Copyright 2011-2018 Rumma & Ko Ltd
# License: BSD (see file COPYING for details)


from __future__ import unicode_literals
from builtins import str
import six

import datetime

from django.db import models
from django.db.models import Q
from django.conf import settings
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone

from lino import mixins
from lino.api import dd, rt, _, pgettext

from .choicelists import (
    DurationUnits, Recurrencies, Weekdays, AccessClasses, PlannerColumns)
from .utils import setkw, dt2kw, when_text

from lino.modlib.checkdata.choicelists import Checker
from lino.modlib.printing.mixins import TypedPrintable
from lino.modlib.printing.mixins import Printable
from lino.modlib.users.mixins import UserAuthored, Assignable
from lino_xl.lib.postings.mixins import Postable
from lino_xl.lib.outbox.mixins import MailableType, Mailable
from lino_xl.lib.contacts.mixins import ContactRelated
from lino.modlib.office.roles import OfficeStaff
from .workflows import (TaskStates, EntryStates, GuestStates)
from .actions import UpdateGuests
    
from .mixins import Component
from .mixins import EventGenerator, RecurrenceSet, Reservation
from .mixins import Ended
from .mixins import MoveEntryNext, UpdateEntries, UpdateEntriesByEvent
from .actions import ShowEntriesByDay

from .ui import ConflictingEvents

DEMO_START_YEAR = 2013


class CalendarType(object):

    def validate_calendar(self, cal):
        pass


class LocalCalendar(CalendarType):
    label = "Local Calendar"


class GoogleCalendar(CalendarType):
    label = "Google Calendar"

    def validate_calendar(self, cal):
        if not cal.url_template:
            cal.url_template = \
                "https://%(username)s:%(password)s@www.google.com/calendar/dav/%(username)s/"

CALENDAR_CHOICES = []
CALENDAR_DICT = {}


def register_calendartype(name, instance):
    CALENDAR_DICT[name] = instance
    CALENDAR_CHOICES.append((name, instance.label))

register_calendartype('local', LocalCalendar())
register_calendartype('google', GoogleCalendar())


class DailyPlannerRow(mixins.BabelDesignated, mixins.Sequenced):
    
    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'PlannerRow')
        verbose_name = _("Planner row")
        verbose_name_plural = _("Planner rows")
        ordering = ['seqno']

    start_time = models.TimeField(
        blank=True, null=True,
        verbose_name=_("Start time"))
    end_time = models.TimeField(
        blank=True, null=True,
        verbose_name=_("End time"))


from lino.mixins.periods import ObservedDateRange
from etgen.html import E
from lino.utils import join_elems

class DailyPlannerRows(dd.Table):
    model = 'cal.DailyPlannerRow'
    column_names = "seqno designation start_time end_time"
    required_roles = dd.login_required(OfficeStaff)

class DailyPlanner(DailyPlannerRows):
    label = _("Daily planner")
    editable = False
    parameters = dict(
        date=models.DateField(
                _("Date"), help_text=_("Date to show")),
        user=dd.ForeignKey('users.User', null=True, blank=True))

    @classmethod
    def param_defaults(cls, ar, **kw):
        kw = super(DailyPlanner, cls).param_defaults(ar, **kw)
        kw.update(date=dd.today())
        # kw.update(end_date=dd.today())
        # kw.update(user=ar.get_user())
        return kw
    
    @classmethod
    def setup_columns(self):
        names = ''
        for i, vf in enumerate(self.get_ventilated_columns()):
            self.add_virtual_field('vc' + str(i), vf)
            names += ' ' + vf.name + ':20'

        self.column_names = "overview {}".format(names)
        
        #~ logger.info("20131114 setup_columns() --> %s",self.column_names)

    @classmethod
    def get_ventilated_columns(cls):

        Event = rt.models.cal.Event

        def fmt(e):
            t = str(e.start_time)[:5]
            u = e.user
            if u is None:
                return "{} {}".format(
                    t, e.room)
                return t
            u = u.initials or u.username or str(u)
            return "{} {}".format(t, u)
        

        def w(pc, verbose_name):
            def func(fld, obj, ar):
                # obj is the DailyPlannerRow instance
                pv = ar.param_values
                qs = Event.objects.filter(event_type__planner_column=pc)
                if pv.user:
                    qs = qs.filter(user=pv.user)
                if pv.date:
                    qs = qs.filter(start_date=pv.date)
                if obj.start_time:
                    qs = qs.filter(start_time__gte=obj.start_time,
                                   start_time__isnull=False)
                if obj.end_time:
                    qs = qs.filter(start_time__lt=obj.end_time,
                                   start_time__isnull=False)
                if not obj.start_time and not obj.end_time:
                    qs = qs.filter(start_time__isnull=True)
                qs = qs.order_by('start_time')
                chunks = [e.obj2href(ar, fmt(e)) for e in qs]
                return E.p(*join_elems(chunks))
            return dd.VirtualField(dd.HtmlBox(verbose_name), func)
            
        for pc in PlannerColumns.objects():
            yield w(pc, pc.text)



    

    
class RemoteCalendar(mixins.Sequenced):

    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'RemoteCalendar')
        verbose_name = _("Remote Calendar")
        verbose_name_plural = _("Remote Calendars")
        ordering = ['seqno']

    type = models.CharField(_("Type"), max_length=20,
                            default='local',
                            choices=CALENDAR_CHOICES)
    url_template = models.CharField(_("URL template"),
                                    max_length=200, blank=True)  # ,null=True)
    username = models.CharField(_("Username"),
                                max_length=200, blank=True)  # ,null=True)
    password = dd.PasswordField(_("Password"),
                                max_length=200, blank=True)  # ,null=True)
    readonly = models.BooleanField(_("read-only"), default=False)

    def get_url(self):
        if self.url_template:
            return self.url_template % dict(
                username=self.username,
                password=self.password)
        return ''

    def save(self, *args, **kw):
        ct = CALENDAR_DICT.get(self.type)
        ct.validate_calendar(self)
        super(RemoteCalendar, self).save(*args, **kw)


class Room(mixins.BabelNamed, ContactRelated):
    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'Room')
        verbose_name = _("Room")
        verbose_name_plural = _("Rooms")

    description = dd.RichTextField(_("Description"), blank=True)

dd.update_field(
    Room, 'company', verbose_name=_("Responsible"))    
dd.update_field(
    Room, 'contact_person', verbose_name=_("Contact person"))    

class Priority(mixins.BabelNamed):
    class Meta:
        app_label = 'cal'
        verbose_name = _("Priority")
        verbose_name_plural = _('Priorities')
    ref = models.CharField(max_length=1)


@dd.python_2_unicode_compatible
class EventType(mixins.BabelNamed, mixins.Sequenced, MailableType):
    templates_group = 'cal/Event'

    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'EventType')
        verbose_name = _("Calendar entry type")
        verbose_name_plural = _("Calendar entry types")
        ordering = ['seqno']

    description = dd.RichTextField(
        _("Description"), blank=True, format='html')
    is_appointment = models.BooleanField(_("Appointment"), default=True)
    all_rooms = models.BooleanField(_("Locks all rooms"), default=False)
    locks_user = models.BooleanField(_("Locks the user"), default=False)

    start_date = models.DateField(
        verbose_name=_("Start date"),
        blank=True, null=True)
    event_label = dd.BabelCharField(
        _("Entry label"), max_length=200, blank=True)
    # , default=_("Calendar entry"))
    # default values for a Babelfield don't work as expected

    max_conflicting = models.PositiveIntegerField(
        _("Simultaneous entries"), default=1)
    max_days = models.PositiveIntegerField(
        _("Maximum days"), default=1)
    transparent = models.BooleanField(_("Transparent"), default=False)

    planner_column = PlannerColumns.field(blank=True)

    def __str__(self):
        # when selecting an Event.event_type it is more natural to
        # have the event_label. It seems that the current `name` field
        # is actually never used.
        return settings.SITE.babelattr(self, 'event_label') \
            or settings.SITE.babelattr(self, 'name')


class GuestRole(mixins.BabelNamed):
    templates_group = 'cal/Guest'

    class Meta:
        app_label = 'cal'
        verbose_name = _("Guest Role")
        verbose_name_plural = _("Guest Roles")


def default_color():
    d = Calendar.objects.all().aggregate(models.Max('color'))
    n = d['color__max'] or 0
    return n + 1


class Calendar(mixins.BabelNamed):

    COLOR_CHOICES = [i + 1 for i in range(32)]

    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'Calendar')
        verbose_name = _("Calendar")
        verbose_name_plural = _("Calendars")

    description = dd.RichTextField(_("Description"), blank=True, format='html')

    color = models.IntegerField(
        _("color"), default=default_color,
        validators=[MinValueValidator(1), MaxValueValidator(32)]
    )
    # choices=COLOR_CHOICES)


class Subscription(UserAuthored):

    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'Subscription')
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
        unique_together = ['user', 'calendar']

    manager_roles_required = dd.login_required(OfficeStaff)

    calendar = dd.ForeignKey(
        'cal.Calendar', help_text=_("The calendar you want to subscribe to."))

    is_hidden = models.BooleanField(
        _("hidden"), default=False,
        help_text=_("""Whether this subscription should "
        "initially be displayed as a hidden calendar."""))


class Task(Component):
    class Meta:
        app_label = 'cal'
        verbose_name = _("Task")
        verbose_name_plural = _("Tasks")
        abstract = dd.is_abstract_model(__name__, 'Task')

    due_date = models.DateField(
        blank=True, null=True,
        verbose_name=_("Due date"))
    due_time = models.TimeField(
        blank=True, null=True,
        verbose_name=_("Due time"))
    # ~ done = models.BooleanField(_("Done"),default=False) # iCal:COMPLETED
    # iCal:PERCENT
    percent = models.IntegerField(_("Duration value"), null=True, blank=True)
    state = TaskStates.field(
        default=TaskStates.as_callable('todo'))  # iCal:STATUS

    # def before_ui_save(self, ar, **kw):
    #     if self.state == TaskStates.todo:
    #         self.state = TaskStates.started
    #     return super(Task, self).before_ui_save(ar, **kw)

    # def on_user_change(self,request):
        # if not self.state:
            # self.state = TaskState.todo
        # self.user_modified = True

    def is_user_modified(self):
        return self.state != TaskStates.todo

    @classmethod
    def on_analyze(cls, lino):
        # lino.TASK_AUTO_FIELDS = dd.fields_list(cls,
        cls.DISABLED_AUTO_FIELDS = dd.fields_list(
            cls, """start_date start_time summary""")
        super(Task, cls).on_analyze(lino)

    # def __unicode__(self):
        # ~ return "#" + str(self.pk)

class EventPolicy(mixins.BabelNamed, RecurrenceSet):
    class Meta:
        app_label = 'cal'
        verbose_name = _("Recurrency policy")
        verbose_name_plural = _('Recurrency policies')
        abstract = dd.is_abstract_model(__name__, 'EventPolicy')

    event_type = dd.ForeignKey(
        'cal.EventType', null=True, blank=True)



class RecurrentEvent(mixins.BabelNamed, RecurrenceSet, EventGenerator,
                     UserAuthored):
    class Meta:
        app_label = 'cal'
        verbose_name = _("Recurring event")
        verbose_name_plural = _("Recurring events")
        abstract = dd.is_abstract_model(__name__, 'RecurrentEvent')

    event_type = dd.ForeignKey('cal.EventType', blank=True, null=True)
    description = dd.RichTextField(
        _("Description"), blank=True, format='html')

    # def on_create(self,ar):
        # super(RecurrentEvent,self).on_create(ar)
        # self.event_type = settings.SITE.site_config.holiday_event_type

    # def __unicode__(self):
        # return self.summary

    def update_cal_rset(self):
        return self

    def update_cal_from(self, ar):
        return self.start_date

    def update_cal_event_type(self):
        return self.event_type

    def update_cal_summary(self, et, i):
        return six.text_type(self)

    def care_about_conflicts(self, we):
        return False

dd.update_field(
    RecurrentEvent, 'every_unit',
    default=Recurrencies.as_callable('yearly'), blank=False, null=False)



class ExtAllDayField(dd.VirtualField):

    """
    An editable virtual field needed for
    communication with the Ext.ensible CalendarPanel
    because we consider the "all day" checkbox
    equivalent to "empty start and end time fields".
    """

    editable = True

    def __init__(self, *args, **kw):
        dd.VirtualField.__init__(self, models.BooleanField(*args, **kw), None)

    def set_value_in_object(self, request, obj, value):
        if value:
            obj.end_time = None
            obj.start_time = None
        else:
            if not obj.start_time:
                obj.start_time = datetime.time(9, 0, 0)
            if not obj.end_time:
                pass
                # obj.end_time = datetime.time(10, 0, 0)
        # obj.save()

    def value_from_object(self, obj, ar):
        # logger.info("20120118 value_from_object() %s",dd.obj2str(obj))
        return (obj.start_time is None)


@dd.python_2_unicode_compatible
class Event(Component, Ended, Assignable, TypedPrintable, Mailable, Postable):
    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'Event')
        # abstract = True
        verbose_name = _("Calendar entry")
        verbose_name_plural = _("Calendar entries")
        # verbose_name = pgettext("cal", "Event")
        # verbose_name_plural = pgettext("cal", "Events")

    update_guests = UpdateGuests()
    update_events = UpdateEntriesByEvent()
    show_today = ShowEntriesByDay('start_date')

    event_type = dd.ForeignKey('cal.EventType', blank=True, null=True)

    transparent = models.BooleanField(_("Transparent"), default=False)
    room = dd.ForeignKey('cal.Room', null=True, blank=True)
    priority = dd.ForeignKey(Priority, null=True, blank=True)
    state = EntryStates.field(
        default=EntryStates.as_callable('suggested'))
    all_day = ExtAllDayField(_("all day"))

    move_next = MoveEntryNext()

    show_conflicting = dd.ShowSlaveTable(ConflictingEvents)

    def strftime(self):
        if not self.start_date:
            return ''
        d = self.start_date.strftime(settings.SITE.date_format_strftime)
        if self.start_time:
            t = self.start_time.strftime(
                settings.SITE.time_format_strftime)
            return "%s %s" % (d, t)
        else:
            return d

    def __str__(self):
        if self.summary:
            s = self.summary
        elif self.event_type:
            s = str(self.event_type)
        elif self.pk:
            s = self._meta.verbose_name + " #" + str(self.pk)
        else:
            s = _("Unsaved %s") % self._meta.verbose_name
        when = self.strftime()
        if when:
            s = "{} ({})".format(s, when)
        return s

    def duration_veto(obj):
        if obj.end_date is None:
            return
        et = obj.event_type
        if et is None:
            return
        duration = obj.end_date - obj.start_date
        # print (20161222, duration.days, et.max_days)
        if duration.days > et.max_days:
            return _(
                "Event lasts {0} days but only {1} are allowed.").format(
                    duration.days, et.max_days)

    def full_clean(self, *args, **kw):
        et = self.event_type
        if et and et.max_days == 1:
            # avoid "Abandoning with 297 unsaved instances"
            self.end_date = None
        msg = self.duration_veto()
        if msg is not None:
            raise ValidationError(str(msg))
        super(Event, self).full_clean(*args, **kw)

    def get_change_observers(self):
        # implements ChangeNotifier
        if not self.is_user_modified():
            return
        for x in super(Event, self).get_change_observers():
            yield x
        for u in (self.user, self.assigned_to):
            if u is not None:
                yield (u, u.mail_mode)
    
        
    def has_conflicting_events(self):
        qs = self.get_conflicting_events()
        if qs is None:
            return False
        if self.event_type is not None:
            if self.event_type.transparent:
                return False
            # holidays (all room events) conflict also with events
            # whose type otherwise would allow conflicting events
            if qs.filter(event_type__all_rooms=True).count() > 0:
                return True
            n = self.event_type.max_conflicting - 1
        else:
            n = 0
        # date = self.start_date
        # if date.day == 9 and date.month == 3:
        #     dd.logger.info("20171130 has_conflicting_events() %s", qs.query)
        return qs.count() > n

    def get_conflicting_events(self):
        if self.transparent:
            return
        # if self.event_type is not None and self.event_type.transparent:
        #     return
        # return False
        # Event = dd.resolve_model('cal.Event')
        # ot = ContentType.objects.get_for_model(RecurrentEvent)
        qs = self.__class__.objects.filter(transparent=False)
        qs = qs.exclude(event_type__transparent=True)
        
        # if self.state.transparent:
        #     # cancelled entries are basically transparent to all
        #     # others. Except if they have an owner, in which case we
        #     # wouldn't want Lino to put another automatic entry at
        #     # that date.
        #     if self.owner_id is None:
        #         return
        #     qs = qs.filter(
        #         owner_id=self.owner_id, owner_type=self.owner_type)
        
        end_date = self.end_date or self.start_date
        flt = Q(start_date=self.start_date, end_date__isnull=True)
        flt |= Q(end_date__isnull=False,
                 start_date__lte=self.start_date, end_date__gte=end_date)
        if end_date == self.start_date:
            if self.start_time and self.end_time:
                # the other starts before me and ends after i started
                c1 = Q(start_time__lte=self.start_time,
                       end_time__gt=self.start_time)
                # the other ends after me and started before i ended
                c2 = Q(end_time__gte=self.end_time,
                       start_time__lt=self.end_time)
                # the other is full day
                c3 = Q(end_time__isnull=True, start_time__isnull=True)
                flt &= (c1 | c2 | c3)
        qs = qs.filter(flt)

        # saved events don't conflict with themselves:
        if self.id is not None:
            qs = qs.exclude(id=self.id)

        # automatic events never conflict with other generated events
        # of same owner. Rule needed for update_events.
        if self.auto_type:
            qs = qs.exclude(
                # auto_type=self.auto_type,
                auto_type__isnull=False,
                owner_id=self.owner_id, owner_type=self.owner_type)

        # transparent events (cancelled or omitted) usually don't
        # cause a conflict with other events (e.g. a holiday). But a
        # cancelled course lesson should not tolerate another lesson
        # of the same course on the same date.
        ntstates = EntryStates.filter(transparent=False)
        if self.owner_id is None:
            if self.state.transparent:
                return
            qs = qs.filter(state__in=ntstates)
        else:
            if self.state.transparent:
                qs = qs.filter(
                    owner_id=self.owner_id, owner_type=self.owner_type)
            else:
                qs = qs.filter(
                    Q(state__in=ntstates) | Q(
                        owner_id=self.owner_id, owner_type=self.owner_type))

        if self.room is None:
            # an entry that needs a room but doesn't yet have one,
            # conflicts with any all-room entry (e.g. a holiday).  For
            # generated entries this list extends to roomed entries of
            # the same generator.
            
            if self.event_type is None or not self.event_type.all_rooms:
                if self.owner_id is None:
                    qs = qs.filter(event_type__all_rooms=True)
                else:
                    qs = qs.filter(
                        Q(event_type__all_rooms=True) | Q(
                            owner_id=self.owner_id, owner_type=self.owner_type))
        else:
            # other event in the same room
            c1 = Q(room=self.room)
            # other event locks all rooms (e.g. holidays)
            # c2 = Q(room__isnull=False, event_type__all_rooms=True)
            c2 = Q(event_type__all_rooms=True)
            qs = qs.filter(c1 | c2)
        if self.user is not None:
            if self.event_type is not None:
                if self.event_type.locks_user:
                    # c1 = Q(event_type__locks_user=False)
                    # c2 = Q(user=self.user)
                    # qs = qs.filter(c1|c2)
                    qs = qs.filter(user=self.user, event_type__locks_user=True)
        # qs = Event.objects.filter(flt,owner_type=ot)
        # if we.start_date.month == 7:
            # print 20131011, self, we.start_date, qs.count()
        # print 20131025, qs.query
        return qs

    def is_fixed_state(self):
        return self.state.fixed
        # return self.state in EntryStates.editable_states

    def is_user_modified(self):
        return self.state != EntryStates.suggested

    def after_ui_save(self, ar, cw):
        super(Event, self).after_ui_save(ar, cw)
        self.update_guests.run_from_code(ar)

    def before_state_change(self, ar, old, new):
        super(Event, self).before_state_change(ar, old, new)
        if new.noauto:
            self.auto_type = None
        
    def suggest_guests(self):
        if self.owner:
            for obj in self.owner.suggest_cal_guests(self):
                yield obj

    def get_event_summary(event, ar):
        # from django.utils.translation import ugettext as _
        s = event.summary
        # if event.owner_id:
        #     s += " ({0})".format(event.owner)
        if event.user is not None and event.user != ar.get_user():
            if event.access_class == AccessClasses.show_busy:
                s = _("Busy")
            s = event.user.username + ': ' + unicode(s)
        elif settings.SITE.project_model is not None \
                and event.project is not None:
            s += " " + unicode(_("with")) + " " + unicode(event.project)
        if event.state:
            s = ("(%s) " % unicode(event.state)) + s
        n = event.guest_set.all().count()
        if n:
            s = ("[%d] " % n) + s
        return s

    def before_ui_save(self, ar, **kw):
        # logger.info("20130528 before_ui_save")
        if self.state is EntryStates.suggested:
            self.state = EntryStates.draft
        return super(Event, self).before_ui_save(ar, **kw)

    def on_create(self, ar):
        if self.event_type is None:
            self.event_type = ar.user.event_type or \
                settings.SITE.site_config.default_event_type
        self.start_date = settings.SITE.today()
        self.start_time = timezone.now().time()
        # see also Assignable.on_create()
        super(Event, self).on_create(ar)

    # def on_create(self,ar):
        # self.start_date = settings.SITE.today()
        # self.start_time = datetime.datetime.now().time()
        # ~ # default user is almost the same as for UserAuthored
        # ~ # but we take the *real* user, not the "working as"
        # if self.user_id is None:
            # u = ar.user
            # if u is not None:
                # self.user = u
        # super(Event,self).on_create(ar)

    def get_postable_recipients(self):
        """return or yield a list of Partners"""
        if self.project:
            if isinstance(self.project, dd.plugins.cal.partner_model):
                yield self.project
        for g in self.guest_set.all():
            yield g.partner
        # if self.user.partner:
            # yield self.user.partner

    def get_mailable_type(self):
        return self.event_type

    def get_mailable_recipients(self):
        if self.project:
            if isinstance(self.project, dd.plugins.cal.partner_model):
                yield ('to', self.project)
        for g in self.guest_set.all():
            yield ('to', g.partner)
        if self.user.partner:
            yield ('cc', self.user.partner)

    # def get_mailable_body(self,ar):
        # return self.description

    @dd.displayfield(_("When"), sortable_by=['start_date', 'start_time'])
    def when_text(self, ar):
        txt = when_text(self.start_date, self.start_time)
        if self.end_date and self.end_date != self.start_date:
            txt += "-" + when_text(self.end_date, self.end_time)
        return txt

    @dd.displayfield(_("When"), sortable_by=['start_date', 'start_time'])
    # def linked_date(self, ar):
    def when_html(self, ar):
        if ar is None:
            return ''
        EntriesByDay = settings.SITE.models.cal.EntriesByDay
        txt = when_text(self.start_date, self.start_time)
        return EntriesByDay.as_link(ar, self.start_date, txt)
        # return self.obj2href(ar, txt)

    @dd.displayfield(_("Link URL"))
    def url(self, ar):
        return 'foo'

    @dd.virtualfield(dd.DisplayField(_("Reminder")))
    def reminder(self, request):
        return False
    # reminder.return_type = dd.DisplayField(_("Reminder"))

    def get_calendar(self):
        # for sub in Subscription.objects.filter(user=ar.get_user()):
            # if sub.contains_event(self):
                # return sub
        return None

    @dd.virtualfield(dd.ForeignKey('cal.Calendar'))
    def calendar(self, ar):
        return self.get_calendar()

    def get_print_language(self):
        # if settings.SITE.project_model is not None and self.project:
        if self.project:
            return self.project.get_print_language()
        if self.user:
            return self.user.language
        return settings.SITE.get_default_language()

    @classmethod
    def get_default_table(cls):
        return OneEvent

    @classmethod
    def on_analyze(cls, lino):
        cls.DISABLED_AUTO_FIELDS = dd.fields_list(cls, "summary")
        super(Event, cls).on_analyze(lino)

    def auto_type_changed(self, ar):
        if self.auto_type:
            self.summary = self.owner.update_cal_summary(
                self.event_type, self.auto_type)

    # def save(self, *args, **kwargs):
    #     if "Weekends" in str(self.owner):
    #         if not self.end_date:
    #             raise Exception("20180321")
    #     super(Event, self).save(*args, **kwargs)

dd.update_field(Event, 'user', verbose_name=_("Responsible user"))


class EntryChecker(Checker):
    model = Event
    def get_responsible_user(self, obj):
        return obj.user or super(
            EntryChecker, self).get_responsible_user(obj)
    
class EventGuestChecker(EntryChecker):
    verbose_name = _("Entries without participants")

    def get_checkdata_problems(self, obj, fix=False):
        if not obj.state.edit_guests:
            return
        existing = set([g.partner.pk for g in obj.guest_set.all()])
        if len(existing) == 0:
            suggested = list(obj.suggest_guests())
            if len(suggested) > 0:
                msg = _("No participants although {0} suggestions exist.")
                yield (True, msg.format(len(suggested)))
                if fix:
                    for g in suggested:
                        g.save()

EventGuestChecker.activate()


class ConflictingEventsChecker(EntryChecker):
    verbose_name = _("Check for conflicting calendar entries")

    def get_checkdata_problems(self, obj, fix=False):
        if not obj.has_conflicting_events():
            return
        qs = obj.get_conflicting_events()
        num = qs.count()
        if num == 1:
            msg = _("Event conflicts with {0}.").format(qs[0])
        else:
            msg = _("Event conflicts with {0} other events.").format(num)
        yield (False, msg)

ConflictingEventsChecker.activate()


class ObsoleteEventTypeChecker(EntryChecker):
    verbose_name = _("Obsolete generated calendar entries")

    def get_checkdata_problems(self, obj, fix=False):
        if not obj.auto_type:
            return
        if obj.owner is None:
            msg = _("Has auto_type but no owner.")
            yield (False, msg)
            return
        et = obj.owner.update_cal_event_type()
        if obj.event_type != et:
            msg = _("Event type but {0} (should be {1}).").format(
                obj.event_type, et)
            autofix = False  # TODO: make this configurable?
            yield (autofix, msg)
            if fix:
                obj.event_type = et
                obj.full_clean()
                obj.save()

ObsoleteEventTypeChecker.activate()


DONT_FIX_LONG_ENTRIES = False

class LongEntryChecker(EntryChecker):
    verbose_name = _("Too long-lasting calendar entries")
    model = Event

    def get_checkdata_problems(self, obj, fix=False):
        msg = obj.duration_veto()
        if msg is not None:
            if DONT_FIX_LONG_ENTRIES:
                yield (False, msg)
            else:
                yield (True, msg)
                if fix:
                    obj.end_date = None
                    obj.full_clean()
                    obj.save()

LongEntryChecker.activate()


@dd.python_2_unicode_compatible
class Guest(Printable):
    workflow_state_field = 'state'
    allow_cascaded_delete = ['event']

    class Meta:
        app_label = 'cal'
        abstract = dd.is_abstract_model(__name__, 'Guest')
        # verbose_name = _("Participant")
        # verbose_name_plural = _("Participants")
        verbose_name = _("Presence")
        verbose_name_plural = _("Presences")
        unique_together = ['event', 'partner']

    event = dd.ForeignKey('cal.Event')
    partner = dd.ForeignKey(dd.plugins.cal.partner_model)
    role = dd.ForeignKey(
        'cal.GuestRole', verbose_name=_("Role"), blank=True, null=True)
    state = GuestStates.field(default=GuestStates.as_callable('invited'))
    remark = models.CharField(_("Remark"), max_length=200, blank=True)

    # Define a `user` property because we want to use
    # `lino.modlib.users.mixins.My`
    def get_user(self):
        # used to apply `owner` requirement in GuestState
        return self.event.user
    user = property(get_user)
    # author_field_name = 'user'

    def __str__(self):
        return u'%s #%s (%s)' % (
            self._meta.verbose_name, self.pk, self.event.strftime())

    # def get_printable_type(self):
    #     return self.role

    def get_mailable_type(self):
        return self.role

    def get_mailable_recipients(self):
        yield ('to', self.partner)

    @dd.displayfield(_("Event"))
    def event_summary(self, ar):
        if ar is None:
            return ''
        return ar.obj2html(self.event, self.event.get_event_summary(ar))


def migrate_reminder(obj, reminder_date, reminder_text,
                     delay_value, delay_type, reminder_done):
    """
    This was used only for migrating to 1.2.0,
    see :mod:`lino.projects.pcsw.migrate`.
    """
    raise NotImplementedError(
        "No longer needed (and no longer supported after 20111026).")

    def delay2alarm(delay_type):
        if delay_type == 'D':
            return DurationUnits.days
        if delay_type == 'W':
            return DurationUnits.weeks
        if delay_type == 'M':
            return DurationUnits.months
        if delay_type == 'Y':
            return DurationUnits.years

    # ~ # These constants must be unique for the whole Lino Site.
    # ~ # Keep in sync with auto types defined in lino.projects.pcsw.models.Person
    # REMINDER = 5

    if reminder_text:
        summary = reminder_text
    else:
        summary = _('due date reached')

    update_auto_task(
        None,  # REMINDER,
        obj.user,
        reminder_date,
        summary, obj,
        done=reminder_done,
        alarm_value=delay_value,
        alarm_unit=delay2alarm(delay_type))


# Inject application-specific fields to users.User.
dd.inject_field(settings.SITE.user_model,
                'access_class',
                AccessClasses.field(
                    default=AccessClasses.as_callable('public'),
                    verbose_name=_("Default access class"),
                    help_text=_(
            """The default access class for your calendar events and tasks.""")
                ))
dd.inject_field(settings.SITE.user_model,
                'event_type',
                dd.ForeignKey('cal.EventType',
                                  blank=True, null=True,
                                  verbose_name=_("Default Event Type"),
        help_text=_("""The default event type for your calendar events.""")
                ))

dd.inject_field(
    'system.SiteConfig',
    'default_event_type',
    dd.ForeignKey(
        'cal.EventType',
        blank=True, null=True,
        verbose_name=_("Default Event Type"),
        help_text=_("""The default type of events on this site.""")
    ))

dd.inject_field(
    'system.SiteConfig',
    'site_calendar',
    dd.ForeignKey(
        'cal.Calendar',
        blank=True, null=True,
        related_name="%(app_label)s_%(class)s_set_by_site_calender",
        verbose_name=_("Site Calendar"),
        help_text=_("""The default calendar of this site.""")))

dd.inject_field(
    'system.SiteConfig',
    'max_auto_events',
    models.IntegerField(
        _("Max automatic events"), default=72,
        blank=True, null=True,
        help_text=_(
            """Maximum number of automatic events to be generated.""")
    ))

dd.inject_field(
    'system.SiteConfig',
    'hide_events_before',
    models.DateField(
        _("Hide events before"),
        blank=True, null=True,
        help_text=_("""If this is specified, certain tables show only 
events after the given date.""")
    ))


Reservation.show_today = ShowEntriesByDay('start_date')

if False:  # removed 20160610 because it is probably not used

    def update_reminders_for_user(user, ar):
        n = 0
        for model in rt.models_by_base(EventGenerator):
            for obj in model.objects.filter(user=user):
                obj.update_reminders(ar)
                # logger.info("--> %s",unicode(obj))
                n += 1
        return n

    class UpdateUserReminders(UpdateEntries):

        """
        Users can invoke this to re-generate their automatic tasks.
        """

        def run_from_ui(self, ar, **kw):
            user = ar.selected_rows[0]
            dd.logger.info("Updating reminders for %s", unicode(user))
            n = update_reminders_for_user(user, ar)
            msg = _("%(num)d reminders for %(user)s have been updated."
                    ) % dict(user=user, num=n)
            dd.logger.info(msg)
            ar.success(msg, **kw)

    @dd.receiver(dd.pre_analyze, dispatch_uid="add_update_reminders")
    def pre_analyze(sender, **kw):
        sender.user_model.define_action(update_reminders=UpdateUserReminders())


from .ui import *

