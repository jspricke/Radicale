#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of Radicale Server - Calendar Server
# Copyright © 2013 Jochen Sprickerhof
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
from time import gmtime
from datetime import date, datetime, timedelta
from dateutil import rrule
from subprocess import Popen, PIPE
from pytz import timezone, UTC
from threading import Lock
from vobject import readOne

class Remind(object):

    def __init__(self, filename=None, label=None):
        self._filename = filename
        self._label = label
        self._files = {}
        self._events = []
        self._lock = Lock()

    def _rem_parse(self, rem):
        events = {}
        for line in rem.split('\n#'):
            line = line.replace('\n', ' ').split(' ')

            event = {}
            if line[3] not in self._files:
                self._files[line[3]] = (getmtime(line[3]), [l for l in open(line[3])])
            hsh = hash(self._files[line[3]][1][int(line[2])-1])
            uid = "%s:%s:%s" % (line[3].replace('/', '-'), line[2], hsh)
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
                event['dtstart'] = [datetime(dat[0], dat[1], dat[2], start[0], start[1])]
                event['dtend'] = datetime(datend[0], datend[1], datend[2], end[0], end[1])
            else:
                event['dtstart'] = [date(dat[0], dat[1], dat[2])]
            event['msg'] = ' '.join(line[9:] if line[8] == '*' else line[10:])

            msgdict = {
                    '\\': '\\\\',
                    '\w': ' ',
                    '"': '\"',
                    }
            for key in msgdict:
                event['msg'] = event['msg'].replace(key, msgdict[key])

            if uid in events:
                events[uid]['dtstart'] += event['dtstart']
            else:
                events[uid] = event
        return events

    def _mk_vevent(self, event):
        vevent = []
        vevent.append("BEGIN:VEVENT")
        if 'dtend' in event:
            local_tz = timezone('Europe/Berlin')
            vevent.append("DTSTART;TZID=Europe/Berlin:%04d%02d%02dT%02d%02d00" % (event['dtstart'][0].year, event['dtstart'][0].month, event['dtstart'][0].day, event['dtstart'][0].hour, event['dtstart'][0].minute))
            vevent.append("DTEND;TZID=Europe/Berlin:%04d%02d%02dT%02d%02d00" % (event['dtend'].year, event['dtend'].month, event['dtend'].day, event['dtend'].hour, event['dtend'].minute))
            if len(event['dtstart']) > 1:
                rdates = [local_tz.localize(d).astimezone(UTC) for d in event['dtstart'][1:]]
                rdates2 = ["%04d%02d%02dT%02d%02d00Z" % (utcstart.year, utcstart.month, utcstart.day, utcstart.hour, utcstart.minute) for utcstart in rdates]
                vevent.append("RRULE:FREQ=YEARLY;INTERVAL=1;COUNT=1")
                vevent.append("RDATE:%s" % ','.join(rdates2))
        else:
            dtstart = ["%04d%02d%02d" % (d.year, d.month, d.day) for d in event['dtstart']]
            vevent.append("DTSTART;VALUE=DATE:%s" % dtstart[0])
            if len(dtstart) > 1:
                for eventa, eventb in zip(event['dtstart'][:-1], event['dtstart'][1:]):
                    if (eventb - eventa).days != 1:
                        vevent.append("RRULE:FREQ=YEARLY;INTERVAL=1;COUNT=1")
                        vevent.append("RDATE;VALUE=DATE:%s" % ','.join(dtstart[1:]))
                        break
                    event['dtstart'] = [event['dtstart'][-1]]
            dtend = event['dtstart'][0]
            dtend += timedelta(days=1)
            vevent.append("DTEND;VALUE=DATE:%04d%02d%02d" % (dtend.year, dtend.month, dtend.day))

        vevent.append("SUMMARY:%s" % event['msg'])
        vevent.append("UID:%s" % event['uid'])
        vevent.append("X-RADICALE-NAME:%s" % event['uid'])
        vevent.append("END:VEVENT")
        return ('\n'.join(vevent),  event['uid'])

    def _update(self):
        self._files = {}
        self._events = []
        rem = Popen(['remind', '-l', '-s15', '-b1', '-r', self._filename, str(date.today() - timedelta(weeks=12))], stdout = PIPE).communicate()[0]
        rem = rem.decode('utf-8')
        events = self._rem_parse(rem[1:])
        return [self._mk_vevent(event) for event in events.values()]

    def update2(self):
        self._lock.acquire()
        if len(self._files) == 0:
            self._events = self._update()
        for fname in self._files:
            if getmtime(fname) > self._files[fname][0]:
                self._events = self._update()
                break
        self._lock.release()

    def vcal(self):
        self.update2()
        return self._events

    def text(self):
        cal = []
        cal.append("BEGIN:VCALENDAR")
        cal.append("VERSION:2.0")
        cal.append("PRODID:-//Radicale//NONSGML Radicale Server//EN")
        cal += [e[0].replace('\n', '\r\n') for e in self.vcal()]
        cal.append("END:VCALENDAR")
        return '\r\n'.join(cal)

    def last_modified(self):
        self.update2()
        return gmtime(max([getmtime(fname[0]) for fname in self._files]))

    def ical(self, text):
        cal = readOne(text)
        reminders = []
        for event in cal.vevent_list:
            remind = []
            remind.append("REM")
            remind.append(event.dtstart.value.strftime("%b %d %Y"))
            if hasattr(event, 'rrule'):
                if event.rruleset._rrule[0]._freq == rrule.DAILY or (event.rruleset._rrule[0]._byweekday and len(event.rruleset._rrule[0]._byweekday) > 1):
                    remind.append('*1')
                elif event.rruleset._rrule[0]._freq == rrule.WEEKLY:
                    remind.append('*7')
                else:
                    print(event.rruleset._rrule[0]._freq)
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
                remind.append(event.dtend.value.strftime('*1'))
            if isinstance(event.dtstart.value, datetime) and not duration.days > 1:
                remind.append(event.dtstart.value.astimezone(timezone('Europe/Berlin')).strftime("AT %H:%M"))
            if duration.days > 1 and not hasattr(event, 'rrule'):
                if hasattr(event, 'dtend') and not isinstance(event.dtend.value, datetime):
                    event.dtend.value -= timedelta(days=1)
                remind.append(event.dtend.value.strftime('UNTIL %b %d %Y'))
            elif duration.seconds:
                remind.append("DURATION %d:%02d" % divmod(duration.seconds / 60, 60))
            remind.append("MSG")
            if self._label:
                remind.append(self._label)
            remind.append("%s" % event.summary.value.encode('utf-8'))
            if hasattr(event, 'location') and event.location.value:
                remind.append("at %s" % event.location.value.encode('utf-8'))
            if hasattr(event, 'description') and event.description.value:
                remind.append("%s" % event.description.value.replace('\n', ' ').encode('utf-8'))
            if duration.days > 1 and not hasattr(event, 'rrule') and duration.seconds:
                remind.append(event.dtstart.value.astimezone(timezone('Europe/Berlin')).strftime("START %b %d %Y %H:%M"))
                remind.append(event.dtend.value.astimezone(timezone('Europe/Berlin')).strftime('END %b %d %Y %H:%M'))
            reminders.append(" ".join(remind))
            reminders.append("\n")
        return reminders

    def append(self, text):
        reminders = self.ical(text)
        open(self._filename, 'a').write(''.join(reminders))

    def remove(self, name):
        (filename, line, delhash) = name.split(':')
        filename = filename.replace('-', '/')
        line = int(line) - 1
        delhash = int(delhash)
        rem = open(filename).readlines()
        linehash = hash(rem[line])
        if linehash == delhash:
            del rem[line]
            open(filename, 'w').writelines(rem)

if __name__ == '__main__':
    from sys import argv, stdout, stdin
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-i', '--ical', action='store_true',  help='Generate ical output')
    parser.add_option('-l', '--label', help='Label for every entry')
    (options, args) = parser.parse_args()
    rem = Remind(label=options.label)
    if options.ical:
        stdout.write('{0}\r\n'.format(Remind(argv[2]).text().encode('utf-8')))
    else:
        stdout.write(''.join(rem.ical(stdin.read())))
