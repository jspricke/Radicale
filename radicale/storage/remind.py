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

import os
import time
from datetime import date, datetime, timedelta
from subprocess import Popen, PIPE
from pytz import timezone, UTC
from threading import Lock
import vobject

class Remind(object):

    def __init__(self, filename):
        self.filename = filename
        self._files = {}
        self._events = []
        self._lock = Lock()

    def _rem_parse(self, rem):
        events = {}
        for line in rem.split('\n#'):
            line = line.replace('\n', ' ').split(' ')

            event = {}
            if line[3] not in self._files:
                self._files[line[3]] = (os.path.getmtime(line[3]), [l for l in open(line[3])])
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
                    if eventb - eventa != timedelta(days=1):
                        vevent.append("RRULE:FREQ=YEARLY;INTERVAL=1;COUNT=1")
                        vevent.append("RDATE;VALUE=DATE:%s" % ','.join(dtstart[1:]))
                        continue
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
        rem = Popen(['remind', '-l', '-s15', '-b1', '-r', self.filename, str(date.today() - timedelta(weeks=12))], stdout = PIPE).communicate()[0]
        rem = rem.decode('utf-8')
        events = self._rem_parse(rem[1:])
        vevents = []
        for evntlist in events.values():
            vevents.append(self._mk_vevent(evntlist))
        return vevents

    def update2(self):
        self._lock.acquire()
        if len(self._files) == 0:
            self._events = self._update()
        for fname in self._files:
            if os.path.getmtime(fname) > self._files[fname][0]:
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
        return time.gmtime(max([os.path.getmtime(fname[0]) for fname in self._files]))

    def append(self, text):
        cal = vobject.readOne(text)
        reminders = []
        for event in cal.vevent_list:
            remind = []
            remind.append("REM")
            if isinstance(event.dtstart.value, datetime):
                remind.append(event.dtstart.value.strftime("%b %d %Y AT %H:%M"))
            else:
                remind.append(event.dtstart.value.strftime("%b %d %Y"))
            if hasattr(event, 'dtend'):
                duration = event.dtend.value - event.dtstart.value
            elif hasattr(event, 'duration'):
                duration = event.duration.value
            if duration:
                remind.append("DURATION %d:%02d" % divmod(duration.seconds / 60, 60))
            #TODO parse RRULE
            remind.append("MSG %s" % event.summary.value.encode('utf-8'))
            if hasattr(event, 'location'):
                remind.append("at %s" % event.location.value.encode('utf-8'))
            if hasattr(event, 'description'):
                remind.append(" %s" % event.description.value.replace('\n', ' ').encode('utf-8'))
            reminders.append(" ".join(remind))
            reminders.append("\n")
        open(self.filename, 'a').write(''.join(reminders))

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
    from sys import argv, stdout
    stdout.write('{0}\r\n'.format(Remind(argv[1]).text().encode('utf-8')))
