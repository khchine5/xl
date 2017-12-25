# -*- coding: UTF-8 -*-
# Copyright 2011-2017 Luc Saffre
# License: BSD (see file COPYING for details)


from __future__ import unicode_literals
from builtins import str

from django.conf import settings
from django.db import models
from django.utils import translation
from django.utils.translation import ugettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.utils.encoding import force_text

from lino import mixins
from lino.api import dd, rt
from lino.utils import ONE_DAY
from lino.utils.xmlgen.html import E
from lino.mixins.periods import Started, Ended

from lino.modlib.office.roles import OfficeStaff, OfficeOperator

from lino.modlib.users.mixins import UserAuthored
from lino.modlib.gfks.mixins import Controllable
from lino.modlib.notify.mixins import ChangeObservable

from .choicelists import Recurrencies, Weekdays, AccessClasses

from .workflows import EntryStates
from .utils import day_and_month
from .actions import UpdateAllGuests

def format_time(t):
    if t is None:
        return ''
    return t.strftime(settings.SITE.time_format_strftime)


def daterange_text(a, b):
    if a == b:
        return a.strftime(settings.SITE.date_format_strftime)
    d = dict(min="...", max="...")
    if a:
        d.update(min=a.strftime(settings.SITE.date_format_strftime))
    if b:
        d.update(max=b.strftime(settings.SITE.date_format_strftime))
    return _("Dates %(min)s to %(max)s") % d


class MoveEntryNext(dd.MultipleRowAction):
    label = _('Move down')
    button_text = _('▽')  # 25BD White down-pointing triangle
    custom_handler = True
    # icon_name = 'date_next'
    show_in_workflow = True
    show_in_bbar = False
    help_text = _("Move this event to next available date")
    readonly = False

    def get_action_permission(self, ar, obj, state):
        if obj.auto_type is None:
            return False
        if state.fixed:
            return False
        return super(MoveEntryNext, self).get_action_permission(
            ar, obj, state)

    def run_on_row(self, obj, ar):
        obj.owner.move_event_next(obj, ar)
        return 1


class UpdateEntries(dd.MultipleRowAction):
    label = _('Update Events')
    button_text = ' ⚡ '  # 26A1
    help_text = _('Create or update the automatic calendar entries '
                  'controlled by this generator.')

    # icon_name = 'lightning'
    readonly = False

    def run_on_row(self, obj, ar):
        return obj.update_reminders(ar)


class UpdateEntriesByEvent(UpdateEntries):
    def get_action_permission(self, ar, obj, state):
        if obj.auto_type is None:
            return False
        return super(UpdateEntriesByEvent, self).get_action_permission(
            ar, obj, state)

    def run_on_row(self, obj, ar):
        return obj.owner.update_reminders(ar)


class EventGenerator(dd.Model):
    class Meta:
        abstract = True

    do_update_events = UpdateEntries()
    update_all_guests = UpdateAllGuests()

    @classmethod
    def get_registrable_fields(cls, site):
        for f in super(EventGenerator, cls).get_registrable_fields(site):
            yield f
        yield "user"

    def delete(self):
        """Delete all events generated by me before deleting myself."""

        self.get_existing_auto_events().delete()
        super(EventGenerator, self).delete()

    def update_cal_rset(self):
        raise NotImplementedError()

    def update_cal_from(self, ar):
        """Return the date of the first Event to be generated.
        Return None if no Events should be generated.

        """
        return dd.today()
        # raise NotImplementedError()
        #~ return self.applies_from

    def update_cal_until(self):
        """Return the limit date until which to generate events.  None means
        "no limit" (which de facto becomes
        :attr:`lino_xl.lib.cal.Plugin.ignore_dates_after`)

        """

        return None

    def update_cal_event_type(self):
        """Return the event_type for the events to generate.  Returning None
    means: don't generate any events.

        """
        return None

    def get_events_language(self):
        """Return the language to activate while events are being
        generated.

        """
        user = self.get_events_user()
        if user is None:
            return settings.SITE.get_default_language()
        return user.language

    def update_cal_room(self, i):
        return None

    def get_events_user(self):
        """Returns the user who is responsible for generated events.

        In :mod.`lino_avanti` this is not the author of the course but
        the teacher.

        """
        return self.get_author()

    # def update_cal_summary(self, i):
    #     ep = self.exam_policy
    #     if ep is not None and ep.event_type is not None:
    #         if ep.event_type.event_label:
    #             return ep.event_type.event_label + " " + str(i)
    #     return _("Evaluation %d") % i

    def update_cal_summary(self, event_type, i):
        label = dd.babelattr(event_type, 'event_label')
        return _("{} {}").format(label, i)

    def update_reminders(self, ar):
        return self.update_auto_events(ar)

    def update_auto_events(self, ar):
        """Generate automatic calendar events owned by this contract.

        """
        if settings.SITE.loading_from_dump:
            #~ print "20111014 loading_from_dump"
            return 0
        wanted, unwanted = self.get_wanted_auto_events(ar)
        # dd.logger.info(
        #     "20171130 get_wanted_auto_events() returned %s", unwanted)
        count = len(wanted)
        # current = 0

        # msg = dd.obj2str(self)
        # msg += ", qs=" + str([e.auto_type for e in qs])
        # msg += ", wanted=" + ', '.join([
        #     "{}:{}".format(e.auto_type, dd.fds(e.start_date))
        #     for e in wanted.values()])
        # dd.logger.info('20161015 ' + msg)

        for ee in unwanted.values():
            if not ee.is_user_modified():
                ee.delete()
                count += 1

        # create new Events for remaining wanted
        for we in wanted.values():
            self.before_auto_event_save(we)
            we.save()
            we.after_ui_save(ar, None)
        #~ logger.info("20130528 update_auto_events done")
        return count

    def compare_auto_event(self, obj, ae):
        original_state = dict(obj.__dict__)
        summary = force_text(ae.summary)
        if obj.summary != summary:
            obj.summary = summary
        if obj.user != ae.user:
            obj.user = ae.user
        if obj.start_date != ae.start_date:
            obj.start_date = ae.start_date
        if obj.end_date != ae.end_date:
            obj.end_date = ae.end_date
        if obj.start_time != ae.start_time:
            obj.start_time = ae.start_time
        if obj.end_time != ae.end_time:
            obj.end_time = ae.end_time
        if obj.event_type != ae.event_type:
            obj.event_type = ae.event_type
        if obj.room != ae.room:
            obj.room = ae.room
        self.before_auto_event_save(obj)
        if obj.__dict__ != original_state:
            obj.save()

    def setup_auto_event(self, obj):
        pass

    def before_auto_event_save(self, obj):
        """Called for automatically generated events after their automatic
        fields have been set and before the event is saved.  This
        allows for additional application-specific automatic fields.

        E.g. the :attr:`room` field in :mod:`lino_xl.lib.courses`.

        :class:`EventGenerator`
        by default manages the following **automatic event fields**:

        - :attr:`auto_type``
        - :attr:`user`
        - :attr:`summary`
        - :attr:`start_date`, :attr:`start_time`
        - :attr:`end_date`, :attr:`end_time`

        """
        pass

    def get_wanted_auto_events(self, ar):

        wanted = dict()
        unwanted = dict()
        rset = self.update_cal_rset()
        if rset is None:
            ar.info("No recurrency set")
            return wanted, unwanted
        
        #~ ar.info("20131020 rset %s",rset)
        #~ if rset and rset.every > 0 and rset.every_unit:
        if not rset.every_unit:
            ar.info("No every_unit")
            return wanted, unwanted
        
        qs = self.get_existing_auto_events()
        
        qs = qs.order_by('start_date', 'start_time', 'auto_type')
        
        # Find the existing event before the first unmodified
        # event. This is where the algorithm will start.
        event_no = 0
        date = None
        for ee in qs:
            if ee.is_user_modified():
                event_no = ee.auto_type
                # date = ee.start_date
                date = rset.get_next_suggested_date(ar, ee.start_date)
            else:
                break
        if event_no is not None:
            qs = qs.filter(auto_type__gt=event_no)

        if date is None:
            date = self.update_cal_from(ar)
            if not date:
                ar.info("No start date")
                return wanted, unwanted

        # Loop over existing events to fill the unwanted dict. In the
        # beginning all existing events are unwanted. Afterwards we
        # will pop wanted events from this dict.
        
        for ee in qs:
            unwanted[ee.auto_type] = ee
            
            # we = wanted.pop(ee.auto_type, None)
            # if we is None:
            #     # there is an unwanted event in the database
            #     if not ee.is_user_modified():
            #         unwanted.add(ee)
            #     #~ else:
            #         #~ e.auto_type = None
            #         #~ e.save()
            # elif ee.is_user_modified():
            #     if ee.start_date != we.start_date:
            #         subsequent = ', '.join([str(x.auto_type)
            #                                for x in wanted.values()])
            #         delta = ee.start_date - we.start_date
            #         ar.debug(
            #             "%d has been moved from %s to %s: "
            #             "move subsequent dates (%s) by %s"
            #             % (
            #                 ee.auto_type, we.start_date,
            #                 ee.start_date, subsequent, delta))
            #         for se in wanted.values():
            #             # ov = se.start_date
            #             se.start_date += delta
            #             # ar.debug("%d : %s -> %s" % (
            #             #     se.auto_type, ov, se.start_date))
            # else:
            #     self.compare_auto_event(ee, we)

        event_type = self.update_cal_event_type()
        if event_type is None:
            # raise Exception("20170731")
            ar.warning("No automatic events because event_type is empty")
            return wanted, unwanted
        
        # ar.debug("20140310a %s", date)
        date = rset.find_start_date(date)
        # ar.debug("20140310b %s", date)
        if date is None:
            ar.info("No available start date.")
            return wanted, unwanted
        until = self.update_cal_until() \
            or dd.plugins.cal.ignore_dates_after
        if until is None:
            raise Exception("ignore_dates_after may not be None")
        # don't take rset.max_events == 0 as False
        if rset.max_events is None:
            max_events = settings.SITE.site_config.max_auto_events
        else:
            max_events = rset.max_events
        Event = settings.SITE.modules.cal.Event
        ar.info("Generating events between %s and %s (max. %s).",
                date, until, max_events)
        ignore_before = dd.plugins.cal.ignore_dates_before
        user = self.get_events_user()
        with translation.override(self.get_events_language()):
            while max_events is None or event_no < max_events:
                if date > until:
                    ar.info("Reached upper date limit %s", until)
                    break
                event_no += 1
                if ignore_before is None or date >= ignore_before:
                    we = Event(
                        auto_type=event_no,
                        user=user,
                        start_date=date,
                        summary=self.update_cal_summary(
                            event_type, event_no),
                        room=self.update_cal_room(event_no),
                        owner=self,
                        event_type=event_type,
                        start_time=rset.start_time,
                        end_time=rset.end_time)
                    self.setup_auto_event(we)
                    date = self.resolve_conflicts(we, ar, rset, until)
                    if date is None:
                        return wanted, unwanted
                    ee = unwanted.pop(event_no, None)
                    if ee is None:
                        wanted[event_no] = we
                    elif ee.is_user_modified():
                        ar.debug(
                            "%s has been moved from %s to %s."
                            % (ee.summary, date, ee.start_date))
                        date = ee.start_date

                    else:
                        self.compare_auto_event(ee, we)
                        # we don't need to add it to wanted because
                        # compare_auto_event() saves any changes
                        # immediately.
                        # wanted[event_no] = we
                date = rset.get_next_suggested_date(ar, date)
                date = rset.find_start_date(date)
                if date is None:
                    ar.info("Could not find next date.")
                    break
        return wanted, unwanted

    def move_event_next(self, we, ar):
        """Move the specified event to the next date in this series."""

        if we.auto_type is None:
            raise Exception("Cannot move uncontrolled event")
        if we.owner is not self:
            raise Exception(
                "%s cannot move event controlled by %s" % (
                    self, we.owner))
        def doit(ar):
            if we.state == EntryStates.suggested:
                we.state = EntryStates.draft
            rset = self.update_cal_rset()
            date = rset.get_next_alt_date(ar, we.start_date)
            if date is None:
                return
            until = self.update_cal_until() \
                or dd.plugins.cal.ignore_dates_after
            we.start_date = date
            if self.resolve_conflicts(we, ar, rset, until) is None:
                return
            we.save()

            # update all following events:
            self.update_auto_events(ar)

            # report success and tell the client to refresh
            ar.success(refresh=True)
            
        ar.confirm(doit, _("Move {} to next available date?").format(we))

    def care_about_conflicts(self, we):
        return True

    def resolve_conflicts(self, we, ar, rset, until):
    
        date = we.start_date
        if rset == Recurrencies.once:
            return date
        if not self.care_about_conflicts(we):
            return date
        # if date.day == 9 and date.month == 3:
        #     ar.info("20171130 resolve_conflicts() %s",
        #             we.has_conflicting_events())
        # ar.debug("20140310 resolve_conflicts %s", we.start_date)
        while we.has_conflicting_events():
            qs = we.get_conflicting_events()
            date = rset.get_next_alt_date(ar, date)
            ar.debug("%s wants %s but conflicts with %s, moving to %s. ",
                     we.summary, we.start_date, qs, date)
            if date is None or date > until:
                ar.debug(
                    "Failed to get next date for %s (%s > %s).",
                    we, date, until)
                conflicts = [E.tostring(ar.obj2html(o)) for o in qs]
                msg = ', '.join(conflicts)
                ar.warning("%s conflicts with %s. ", we, msg)
                return None
        
            rset.move_event_to(we, date)
        return date

    def get_existing_auto_events(self):
        ot = ContentType.objects.get_for_model(self.__class__)
        qs = rt.models.cal.Event.objects.filter(
            owner_type=ot, owner_id=self.pk,
            auto_type__isnull=False)
        # noauto_states = set([x for x in EntryStates.objects() if x.noauto])
        # if noauto_states:
        #     qs = qs.exclude(state__in=noauto_states)
        return qs

    def suggest_cal_guests(self, event):
        """Yield or return a list of (unsaved) :class:`Guest
        <lino_xl.lib.cal.models.Guest>` objects representing the
        participants to invite to every the given event. Called on
        every event generated by this generator.

        """

        return []

    def get_date_formatter(self):
        rset = self.update_cal_rset()
        if rset and rset.every_unit:
            return rset.every_unit.get_date_formatter()
        return day_and_month

class RecurrenceSet(Started, Ended):


    class Meta:
        abstract = True
        verbose_name = _("Recurrence Set")
        verbose_name_plural = _("Recurrence Sets")

    #~ every_unit = DurationUnits.field(_("Repeat every (unit)"),
    every_unit = Recurrencies.field(
        _("Recurrency"),
        default=Recurrencies.monthly.as_callable,
        blank=True)  # iCal:DURATION
    every = models.IntegerField(_("Repeat every"), default=1)

    monday = models.BooleanField(Weekdays.monday.text, default=False)
    tuesday = models.BooleanField(Weekdays.tuesday.text, default=False)
    wednesday = models.BooleanField(Weekdays.wednesday.text, default=False)
    thursday = models.BooleanField(Weekdays.thursday.text, default=False)
    friday = models.BooleanField(Weekdays.friday.text, default=False)
    saturday = models.BooleanField(Weekdays.saturday.text, default=False)
    sunday = models.BooleanField(Weekdays.sunday.text, default=False)

    max_events = models.PositiveIntegerField(
        _("Number of events"),
        blank=True, null=True)

    @classmethod
    def on_analyze(cls, site):
        cls.WEEKDAY_FIELDS = dd.fields_list(
            cls, 'monday tuesday wednesday thursday friday saturday  sunday')
        super(RecurrenceSet, cls).on_analyze(site)

    @classmethod
    def get_registrable_fields(cls, site):
        for f in super(RecurrenceSet, cls).get_registrable_fields(site):
            yield f
        for f in cls.WEEKDAY_FIELDS:
            yield f
        yield 'every'
        yield 'every_unit'
        yield 'max_events'
        #~ yield 'event_type'
        yield 'start_date'
        yield 'end_date'
        yield 'start_time'
        yield 'end_time'

    def full_clean(self, *args, **kw):
        if self.every_unit == Recurrencies.per_weekday:
            self.every_unit = Recurrencies.weekly
        elif self.every_unit == Recurrencies.once:
            self.max_events = 1
            self.every = 0
        super(RecurrenceSet, self).full_clean(*args, **kw)

    def disabled_fields(self, ar):
        rv = super(RecurrenceSet, self).disabled_fields(ar)
        if self.every_unit == Recurrencies.once:
            rv.add('max_events')
            rv.add('every')
        # if self.every_unit != Recurrencies.per_weekday:
            # rv |= self.WEEKDAY_FIELDS
        return rv

    @dd.displayfield(_("Description"))
    def what_text(self, ar):
        return str(self)

    @dd.displayfield(_("Times"))
    def times_text(self, ar):
        if self.start_time or self.end_time:
            return "%s-%s" % (format_time(self.start_time),
                              format_time(self.end_time))
        return ''

    @dd.displayfield(_("When"))
    def weekdays_text(self, ar):
        if self.every_unit == Recurrencies.once:
            if self.end_date:
                return _("{0}-{1}").format(
                    dd.fds(self.start_date), dd.fds(self.end_date))
                # return _("From {0} until {1}").format(
                #     dd.fdf(self.start_date), dd.fdf(self.end_date))
            return _("On {0}").format(dd.fdf(self.start_date))
        elif self.every_unit == Recurrencies.weekly:
            weekdays = []
            for wd in Weekdays.objects():
                if getattr(self, wd.name):
                    weekdays.append(str(wd.text))
            if len(weekdays) == 0:
                return ''
            every_text = ', '.join(weekdays)
        elif self.every_unit == Recurrencies.daily:
            every_text = _("day")
        elif self.every_unit == Recurrencies.monthly:
            every_text = _("month")
        elif self.every_unit in (Recurrencies.yearly, Recurrencies.easter):
            every_text = _("year")
        else:
            return ''
        if self.every == 1:
            return _("Every %s") % every_text
        return _("Every %snd %s") % (self.every, every_text)

    def move_event_to(self, ev, newdate):
        """Move given event to a new date.  Also change `end_date` if
        necessary.

        """
        ev.start_date = newdate
        if self.end_date is None:
            ev.end_date = None
        else:
            duration = self.end_date - newdate
            ev.end_date = newdate + duration
            
    def get_next_alt_date(self, ar, date):
        """Currently always returns date + 1.

        """
        return self.find_start_date(date + ONE_DAY)

    def get_next_suggested_date(self, ar, date):
        """Find the next date after the given date, without worrying about
        conflicts.

        """
        if self.every_unit == Recurrencies.once:
            ar.debug("get_next_suggested_date() once --> None.")
            return None
        if self.every_unit == Recurrencies.per_weekday:
            date = date + ONE_DAY
        else:
            date = self.every_unit.add_duration(date, self.every)
        return self.find_start_date(date)

    def find_start_date(self, date):
        """Find the first available date for the given date (possibly
        including that date)

        """

        if date is not None:
            for i in range(7):
                if self.is_available_on(date):
                    return date
                date += ONE_DAY
        return None

    def is_available_on(self, date):
        """Whether the given date `date` is allowed according to the weekdays
        of this recurrence set.

        """
        if self.monday or self.tuesday or self.wednesday or self.thursday \
           or self.friday or self.saturday or self.sunday:
            wd = date.isoweekday()  # Monday:1, Tuesday:2 ... Sunday:7
            wd = Weekdays.get_by_value(str(wd))
            rv = getattr(self, wd.name)
            #~ logger.info('20130529 is_available_on(%s) -> %s -> %s',date,wd,rv)
            return rv
        return True

dd.update_field(RecurrenceSet, 'start_date', default=dd.today)


class Reservation(RecurrenceSet, EventGenerator, mixins.Registrable,
                  UserAuthored):

    class Meta:
        abstract = True

    room = dd.ForeignKey('cal.Room', blank=True, null=True)
    max_date = models.DateField(
        blank=True, null=True,
        verbose_name=_("Generate events until"))

    # no longer needed after 20170826
    # @classmethod
    # def setup_parameters(cls, **fields):
    #     """Adds the :attr:`room` filter parameter field."""
    #     fld = cls._meta.get_field('room')
    #     fields.setdefault(
    #         'room', dd.ForeignKey(
    #             'cal.Room', verbose_name=fld.verbose_name,
    #             blank=True, null=True))
    #     return super(Reservation, cls).setup_parameters(**fields)

    @classmethod
    def get_simple_parameters(cls):
        s = list(super(Reservation, cls).get_simple_parameters())
        s.append('room')
        return s

    def update_cal_until(self):
        return self.max_date

    def update_cal_rset(self):
        """Return the *reccurrency set* to be used when generating events for
        this reservation.

        """
        return self

    def update_cal_room(self, i):
        return self.room

    @classmethod
    def get_registrable_fields(cls, site):
        for f in super(Reservation, cls).get_registrable_fields(site):
            yield f
        yield 'room'
        yield 'max_date'

    def after_state_change(self, ar, old, target_state):
        super(Reservation, self).after_state_change(ar, old, target_state)
        self.update_reminders(ar)

    #~ def after_ui_save(self,ar):
        #~ super(Reservation,self).after_ui_save(ar)
        #~ if self.state.editable:
            #~ self.update_reminders(ar)


class Component(Started,
                mixins.ProjectRelated,
                UserAuthored,
                Controllable,
                ChangeObservable,
                mixins.CreatedModified):

    workflow_state_field = 'state'
    manager_roles_required = dd.login_required(
        (OfficeStaff, OfficeOperator))

    class Meta:
        abstract = True

    summary = models.CharField(
        _("Short description"), max_length=200, blank=True)
    description = dd.RichTextField(
        _("Description"),
        blank=True,
        format='plain')
        # format='html')

    access_class = AccessClasses.field(blank=True, help_text=_("""\
Whether this is private, public or between."""))  # iCal:CLASS
    sequence = models.IntegerField(_("Revision"), default=0)
    auto_type = models.IntegerField(_("No."), null=True, blank=True)

    def save(self, *args, **kw):
        if self.user is not None and self.access_class is None:
            self.access_class = self.user.access_class
        super(Component, self).save(*args, **kw)

    def on_duplicate(self, ar, master):
        self.auto_type = None
        super(Component, self).on_duplicate(ar, master)

    def disabled_fields(self, ar):
        rv = super(Component, self).disabled_fields(ar)
        if self.auto_type:
            rv |= self.DISABLED_AUTO_FIELDS
        return rv

    def get_uid(self):
        """
        This is going to be used when sending
        locally created components to a remote calendar.
        """
        if not settings.SITE.uid:
            raise Exception(
                'Cannot create local calendar components because settings.SITE.uid is empty.')
        return "%s@%s" % (self.pk, settings.SITE.uid)

    #~ def on_user_change(self,request):
        #~ raise NotImplementedError
        #~ self.user_modified = True
    def summary_row(self, ar, **kw):
        #~ logger.info("20120217 Component.summary_row() %s", self)
        #~ if self.owner and not self.auto_type:
        html = [ar.obj2html(self)]
        if self.start_time:
            html += [_(" at "),
                     dd.strftime(self.start_time)]
        if self.state:
            html += [' [%s]' % force_text(self.state)]
        if self.summary:
            html += [': %s' % force_text(self.summary)]
            #~ html += ui.href_to(self,force_text(self.summary))
        #~ html += _(" on ") + dbutils.dtos(self.start_date)
        #~ if self.owner and not self.owner.__class__.__name__ in ('Person','Company'):
            #~ html += " (%s)" % reports.summary_row(self.owner,ui,rr)
        if self.project is not None:
            html.append(" (%s)" % self.project.summary_row(ar, **kw))
            #~ print 20120217, self.project.__class__, self
            #~ html += " (%s)" % self.project.summary_row(ui)
        return html
        #~ return super(Event,self).summary_row(ui,rr,**kw)

    # def get_change_owner(self):
    #     return self.project


#~ Component.owner.verbose_name = _("Automatically created by")

