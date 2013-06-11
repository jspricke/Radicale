#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of Radicale Server - Calendar Server
# Copyright © 2013-2014 Jochen Sprickerhof
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Radicale.  If not, see <http://www.gnu.org/licenses/>.

"""
Remind storage backend.

"""

from os.path import getmtime
from datetime import date, datetime, timedelta
from dateutil import rrule
from dateutil.tz import gettz
from subprocess import Popen, PIPE
from threading import Lock
from vobject import readOne, iCalendar

class Remind(object):

    def __init__(self, localtz, filename=None, label=None, priority=None):
        self._localtz = localtz
        self._filename = filename
        self._label = label
        self._priority = priority
        self._files = {}
        self._events = {}
        self._lock = Lock()

    def _remind(self):
        rem = Popen(['remind', '-l', '-s15', '-b1', '-r', self._filename, str(date.today() - timedelta(weeks=12))], stdout=PIPE).communicate()[0].decode('utf-8')[1:]
        self._files = {}
        events = {}
        for line in rem.split('\n#'):
            line = line.replace('\n', ' ').split(' ')

            event = {}
            if line[3] not in self._files:
                self._files[line[3]] = (getmtime(line[3]), [l for l in open(line[3])])
                events[line[3]] = {}
            hsh = hash(self._files[line[3]][1][int(line[2])-1])
            uid = '%s:%s' % (line[2], hsh)
            event['uid'] = uid
            dat = datend = [int(f) for f in line[4].split('/')]
            times = None if line[8] == '*' else line[9]
            if times:
                if '-' in times:
                    start, end = times.split('-')
                    start = [int(s) for s in start.split(':')]
                    if '+' in end:
                        end, days = end.split('+')
                        end = [int(s) for s in end.split(':')]
                        datend = dat[:]
                        datend[2] += int(days)
                    else:
                        end = [int(s) for s in end.split(':')]
                else:
                    start = end = [int(s) for s in times.split(':')]
                event['dtstart'] = [datetime(dat[0], dat[1], dat[2], start[0], start[1], tzinfo=self._localtz)]
                event['dtend'] = datetime(datend[0], datend[1], datend[2], end[0], end[1], tzinfo=self._localtz)
            else:
                event['dtstart'] = [date(dat[0], dat[1], dat[2])]
            event['msg'] = ' '.join(line[9:] if line[8] == '*' else line[10:])

            if uid in events[line[3]]:
                events[line[3]][uid]['dtstart'] += event['dtstart']
            else:
                events[line[3]][uid] = event

        for calendar in events:
            self._events[calendar] = iCalendar()
            for event in events[calendar].values():
                self._vevent(self._events[calendar], event)

    def _vevent(self, calendar, event):
        vevent = calendar.add('vevent')
        vevent.add('dtstart').value = event['dtstart'][0]
        vevent.add('summary').value = event['msg']
        vevent.add('uid').value = event['uid']
        if 'dtend' in event:
            valarm = vevent.add('valarm')
            valarm.add('trigger').value = timedelta(minutes=-10)
            valarm.add('action').value = 'DISPLAY'
            valarm.add('description').value = event['msg']
            vevent.add('dtend').value = event['dtend']
            if len(event['dtstart']) > 1:
                rset = rrule.rruleset()
                for dat in event['dtstart'][1:]:
                    rset.rdate(dat)
                vevent.rruleset = rset
        else:
            if len(event['dtstart']) > 1:
                if (max(event['dtstart']) - min(event['dtstart'])).days == len(event['dtstart']) - 1:
                    vevent.add('dtend').value = event['dtstart'][-1] + timedelta(days=1)
                else:
                    rset = rrule.rruleset()
                    for dat in event['dtstart'][1:]:
                        # dateutil needs datetime in rruleset, but vobject uses dtstart to detect that it's actually a date
                        # cf. icalendar.py:495 (setrruleset -> isDate)
                        rset.rdate(datetime(dat.year, dat.month, dat.day))
                    vevent.rruleset = rset
                    vevent.add('dtend').value = event['dtstart'][0] + timedelta(days=1)
            else:
                vevent.add('dtend').value = event['dtstart'][0] + timedelta(days=1)

    def _update(self):
        self._lock.acquire()
        if len(self._files) == 0:
            self._remind()
        for fname in self._files:
            if getmtime(fname) > self._files[fname][0]:
                self._remind()
                break
        self._lock.release()

    def components(self, path=None):
        self._update()
        if path:
            return self._events[path].serialize().decode('utf-8')
        else:
            cals = []
            for cal in self._events.values():
                cals.extend(cal.serialize().decode('utf-8').splitlines(True)[3:-1])
            return cals

    def text(self):
        cal = []
        cal.append('BEGIN:VCALENDAR\r\n')
        cal.append('VERSION:2.0\r\n')
        cal.append('PRODID:-//Radicale//NONSGML Radicale Server//EN\r\n')
        cal.extend(self.components())
        cal.append('END:VCALENDAR\r\n')
        return ''.join(cal)

    def get_files(self):
        self._update()
        return self._files

    def ical(self, text):
        cal = readOne(text)
        reminders = []
        for event in cal.vevent_list:
            remind = []
            remind.append('REM')
            remind.append(event.dtstart.value.strftime('%b %d %Y').replace(' 0', ' '))
            if self._priority:
                remind.append('PRIORITY %s' % self._priority)
            if hasattr(event, 'rrule') and event.rruleset._rrule[0]._freq != 0:
                if event.rruleset._rrule[0]._freq == rrule.DAILY or (event.rruleset._rrule[0]._byweekday and len(event.rruleset._rrule[0]._byweekday) > 1):
                    remind.append('*1')
                elif event.rruleset._rrule[0]._freq == rrule.WEEKLY:
                    remind.append('*7')
                else:
                    raise NotImplementedError
                #TODO BYMONTH
                if event.rruleset._rrule[0]._byweekday and len(event.rruleset._rrule[0]._byweekday) > 1:
                    dayNums = set(range(7)) - set(event.rruleset._rrule[0]._byweekday)
                    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                    days = [weekdays[day] for day in dayNums]
                    remind.append('SKIP OMIT %s' % ' '.join(days))
                if event.rruleset._rrule[0]._until:
                    remind.append(event.rruleset._rrule[0]._until.strftime('UNTIL %b %d %Y'))
                elif event.rruleset._rrule[0]._count:
                    remind.append(event.rruleset[-1].strftime('UNTIL %b %d %Y'))
            if hasattr(event, 'dtend'):
                duration = event.dtend.value - event.dtstart.value
            elif hasattr(event, 'duration') and event.duration.value:
                duration = event.duration.value
            if duration.days > 1 and not hasattr(event, 'rrule'):
                remind.append('*1')
            if isinstance(event.dtstart.value, datetime) and not duration.days > 1:
                remind.append(event.dtstart.value.astimezone(self._localtz).strftime('AT %H:%M'))
            if duration.days > 1 and not hasattr(event, 'rrule'):
                if hasattr(event, 'dtend') and not isinstance(event.dtend.value, datetime):
                    event.dtend.value -= timedelta(days=1)
                remind.append(event.dtend.value.strftime('UNTIL %b %d %Y'))
            elif duration.days == 0 and duration.seconds > 0:
                remind.append('DURATION %d:%02d' % divmod(duration.seconds / 60, 60))
            remind.append('MSG')
            if self._label:
                remind.append(self._label)
            remind.append('%s' % event.summary.value.encode('utf-8'))
            if hasattr(event, 'location') and event.location.value:
                remind.append('at %s' % event.location.value.encode('utf-8'))
            if hasattr(event, 'description') and event.description.value:
                remind.append('%s' % event.description.value.replace('\n', ' ').encode('utf-8'))
            if duration.days > 1 and not hasattr(event, 'rrule') and duration.seconds:
                remind.append(event.dtstart.value.astimezone(self._localtz).strftime('START %b %d %Y %H:%M'))
                remind.append(event.dtend.value.astimezone(self._localtz).strftime('END %b %d %Y %H:%M'))
            reminders.append(' '.join(remind).strip() + '\n')
        return ''.join(reminders)

    def append(self, text, filename):
        if filename not in self._files:
            return
        open(self._filename, 'a').write(self.ical(text))

    def remove(self, name, filename):
        if filename not in self._files:
            return
        (line, delhash) = name.split(':')
        line = int(line) - 1
        delhash = int(delhash)
        rem = open(filename).readlines()
        linehash = hash(rem[line])
        if linehash == delhash:
            del rem[line]
            open(filename, 'w').writelines(rem)

def main():
    from sys import argv, stdout, stdin
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-i', '--ical', action='store_true', help='Generate ical output')
    parser.add_option('-l', '--label', help='Label for every entry')
    parser.add_option('-p', '--priority', help='Priority for every entry')
    parser.add_option('-z', '--zone', default='Europe/Berlin', help='Timezone of remind')
    (options, args) = parser.parse_args()
    zone = gettz(options.zone)
    # Manually set timezone name to generate correct ical files
    # (python-vobject tests for the zone attribute)
    zone.zone = options.zone
    if options.ical:
        stdout.write('{0}\r\n'.format(Remind(zone, argv[2]).text().encode('utf-8')))
    else:
        stdout.write(Remind(zone, label=options.label, priority=options.priority).ical(stdin.read()))

if __name__ == '__main__':
    main()
