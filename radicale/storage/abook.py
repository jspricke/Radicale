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

from os.path import getmtime
from time import gmtime
from threading import Lock
from ConfigParser import ConfigParser
from vobject import readComponents

class Abook(object):

    def __init__(self, filename=None):
        self._filename = filename
        self._last_modified = 0
        self._events = []
        self._lock = Lock()

    def vcard(self):
        abook = ConfigParser()
        abook.read(self._filename)
        vcards = []
        for i in abook.sections()[1:]:
            vcard = []
            vcard.append('BEGIN:VCARD')
            vcard.append('VERSION:4.0')
            uid = '%s;%d' % (i, hash(abook.get(i, 'name')))
            vcard.append('UID:%s' % uid)
            vcard.append('FN:%s' % abook.get(i, 'name'))
            if abook.has_option(i, 'nick'): vcard.append('NICKNAME:%s' % abook.get(i, 'nick'))
            vcard.append('N:%s;%s' % (abook.get(i, 'name').split(' ')[-1], ' '.join(abook.get(i, 'name').split(' ')[:-1])))
            if abook.has_option(i, 'email'):
                for mail in abook.get(i, 'email').split(','):
                    vcard.append('EMAIL:%s' % mail)
            if abook.has_option(i, 'phone'): vcard.append('TEL;TYPE=HOME:%s' % abook.get(i, 'phone'))
            if abook.has_option(i, 'workphone'): vcard.append('TEL;TYPE=WORK:%s' % abook.get(i, 'workphone'))
            if abook.has_option(i, 'mobile'): vcard.append('TEL;TYPE=CELL:%s' % abook.get(i, 'mobile'))
            if abook.has_option(i, 'url'): vcard.append('URL:%s' % abook.get(i, 'url'))
            if abook.has_option(i, 'custom1'): vcard.append('NOTE:%s' % abook.get(i, 'custom1').replace(',', '\,'))
            if abook.has_option(i, 'custom2'): vcard.append('NOTE:%s' % abook.get(i, 'custom2').replace(',', '\,'))
            if abook.has_option(i, 'custom3'): vcard.append('NOTE:%s' % abook.get(i, 'custom3').replace(',', '\,'))
            address = abook.get(i, 'address') if abook.has_option(i, 'address') else ''
            address2 = abook.get(i, 'address2') if abook.has_option(i, 'address2') else ''
            city = abook.get(i, 'city') if abook.has_option(i, 'city') else ''
            zipn = abook.get(i, 'zip') if abook.has_option(i, 'zip') else '0'
            state = abook.get(i, 'state') if abook.has_option(i, 'state') else ''
            country = abook.get(i, 'country') if abook.has_option(i, 'country') else ''
            if abook.has_option(i, 'address') or abook.has_option(i, 'address2') or abook.has_option(i, 'city') or abook.has_option(i, 'country') or abook.has_option(i, 'zip') or abook.has_option(i, 'country'):
              vcard.append('ADR;TYPE=home:;%s;%s;%s;%s;%s;%s' % (address2, address, city, state, zipn, country))
            vcard.append('END:VCARD')
            text = '\n'.join(vcard)
            vcards.append((text.decode('utf-8'), uid))
        return vcards

    def update2(self):
        self._lock.acquire()
        if getmtime(self._filename) > self._last_modified:
            self._events = self.vcard()
            self._last_modified = getmtime(self._filename)
        self._lock.release()

    def vcal(self):
        self.update2()
        return self._events

    def text(self):
        cal = [e[0].replace('\n', '\r\n') for e in self.vcal()]
        return '\r\n\r\n'.join(cal)

    def last_modified(self):
        self.update2()
        return gmtime(self._last_modified)

    def abook(self, vcard, section, cParser):
        cParser.add_section(section)
        cParser.set(section, 'name', vcard.fn.value.encode('utf-8'))

        if hasattr(vcard, 'email'):
            email = [e.value for e in vcard.email_list]
            cParser.set(section, 'email', ','.join(email).encode('utf-8'))
        if hasattr(vcard, 'note_list'):
            for (i, note) in enumerate(vcard.note_list):
                cParser.set(section, 'custom%d' % (i+1), note.value.encode('utf-8'))
        if hasattr(vcard, 'tel_list'):
            for tel in vcard.tel_list:
                if tel.TYPE_param == 'HOME':
                    cParser.set(section, 'phone', tel.value.encode('utf-8'))
                elif tel.TYPE_param == 'WORK':
                    cParser.set(section, 'workphone', tel.value.encode('utf-8'))
                elif tel.TYPE_param == 'CELL':
                    cParser.set(section, 'mobile', tel.value.encode('utf-8'))
        if hasattr(vcard, 'nickname'): cParser.set(section, 'nick', vcard.nickname.value.encode('utf-8'))
        if hasattr(vcard, 'url'): cParser.set(section, 'url', vcard.url.value.encode('utf-8'))
        if hasattr(vcard, 'adr'):
            if vcard.adr.value.street:
                cParser.set(section, 'address', vcard.adr.value.street.encode('utf-8'))
            if vcard.adr.value.extended:
                cParser.set(section, 'address2', vcard.adr.value.extended.encode('utf-8'))
            if vcard.adr.value.city:
                cParser.set(section, 'city', vcard.adr.value.city.encode('utf-8'))
            if vcard.adr.value.region:
                cParser.set(section, 'state', vcard.adr.value.region.encode('utf-8'))
            if vcard.adr.value.code and vcard.adr.value.code != '0':
                cParser.set(section, 'zip', vcard.adr.value.code.encode('utf-8'))
            if vcard.adr.value.country:
                cParser.set(section, 'country', vcard.adr.value.country.encode('utf-8'))

    def append(self, text):
        cParser = ConfigParser()
        cParser.read(self._filename)

        for vcard in readComponents(text):
            if ';' in vcard.uid.value:
                (section, oldhash) = vcard.uid.value.split(';')
            else:
                section = int(cParser.sections[-1]) + 1

            if cParser.has_section(section):
                raise NotImplementedError

            self.abook(vcard, section, cParser)

        cParser.write(open(self._filename, 'w'))

    def remove(self, name):
        (section, delhash) = name.split(';')
        delhash = int(delhash)
        abook = ConfigParser()
        abook.read(self._filename)
        linehash = hash(hash(abook.get(section, 'name')))
        if linehash == delhash:
            abook.remove_section(section)
            abook.write(open(self._filename, 'w'))

if __name__ == '__main__':
    from sys import argv, stdout, stdin
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-v', '--vcard', action='store_true',  help='Generate vCard output')
    (options, args) = parser.parse_args()
    if options.vcard:
        stdout.write('{0}\r\n'.format(Abook(argv[2]).text().encode('utf-8')))
    else:
        stdout.write('# abook addressbook file\n\n')
        cParser = ConfigParser()
        cParser.add_section('format')
        cParser.set('format', 'program', 'abook')
        cParser.set('format', 'version', '0.6.0pre2')
        for (i, vcard) in enumerate(readComponents(stdin.read())):
            Abook().abook(vcard, str(i), cParser)
        cParser.write(stdout)
