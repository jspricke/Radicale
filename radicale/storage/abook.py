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
Abook storage backend.

"""

import os
import time
from threading import Lock
import ConfigParser

class Abook(object):

    def __init__(self, filename):
        self.filename = filename
        self.last_modified = 0
        self._events = []
        self._lock = Lock()

    def vcard(self):
        abook = ConfigParser.ConfigParser()
        abook.read(self.filename)
        vcards = []
        for i in abook.sections()[1:]:
            vcard = []
            vcard.append("BEGIN:VCARD")
            vcard.append("VERSION:3.0")
            vcard.append("FN:%s" % abook.get(i, 'name'))
            vcard.append("N:%s;%s" % (abook.get(i, 'name').split(' ')[-1], ' '.join(abook.get(i, 'name').split(' ')[:-1])))
            address = abook.get(i, 'address') if abook.has_option(i, 'address') else ''
            address2 = abook.get(i, 'address2') if abook.has_option(i, 'address2') else ''
            city = abook.get(i, 'city') if abook.has_option(i, 'city') else ''
            zipn = abook.get(i, 'zip') if abook.has_option(i, 'zip') else ''
            state = abook.get(i, 'state') if abook.has_option(i, 'state') else ''
            country = abook.get(i, 'country') if abook.has_option(i, 'country') else ''
            if abook.has_option(i, 'address') or abook.has_option(i, 'address') or abook.has_option(i, 'city') or abook.has_option(i, 'country') or abook.has_option(i, 'zip') or abook.has_option(i, 'country'):
                vcard.append("ADR:;;%s;%s;%s;%s;%s;%s" % (address, address2, city, state, zipn, country))
            if abook.has_option(i, 'phone'): vcard.append("TEL;HOME:%s" % abook.get(i, 'phone'))
            if abook.has_option(i, 'workphone'): vcard.append("TEL;WORK:%s" % abook.get(i, 'workphone'))
            if abook.has_option(i, 'mobile'): vcard.append("TEL;CELL:%s" % abook.get(i, 'mobile'))
            if abook.has_option(i, 'email'):
                for mail in abook.get(i, 'email').split(','):
                    vcard.append("EMAIL;INTERNET:%s" % mail)
            if abook.has_option(i, 'url'): vcard.append("URL:%s" % abook.get(i, 'url'))
            if abook.has_option(i, 'nick'): vcard.append("X-ANDROID-CUSTOM:vnd.android.cursor.item/nickname;%s;1;;;;;;;;;;;;;" % abook.get(i, 'nick'))
            uid = "%d" % hash(abook.get(i, 'name'))
            vcard.append("UID:%s" % uid)
            vcard.append("END:VCARD")
            text = '\n'.join(vcard)
            vcards.append((text.decode('utf-8'), uid))
        return vcards

    def update2(self):
        self._lock.acquire()
        if os.path.getmtime(self.filename) > self.last_modified:
            self._events = self.vcard()
            self.last_modified = os.path.getmtime(self.filename)
        self._lock.release()

    def vcal(self):
        self.update2()
        return self._events

    def text(self):
        cal = [e[0].replace('\n', '\r\n') for e in self.vcal()]
        return '\r\n\r\n'.join(cal)

    def last_modified(self):
        self.update2()
        return time.gmtime(self.filename)

    def append(self, text):
        raise NotImplementedError

    def remove(self, name):
        raise NotImplementedError

if __name__ == '__main__':
    from sys import argv, stdout
    stdout.write('{0}\r\n'.format(Abook(argv[1]).text().encode('utf-8')))
