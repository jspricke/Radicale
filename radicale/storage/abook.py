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
Abook storage backend.

"""

from os.path import getmtime, dirname, join
from threading import Lock
from configobj import ConfigObj
from vobject import readComponents, vCard
from vobject.vcard import Name, Address

class Abook(object):

    def __init__(self, filename=None):
        self._filename = filename
        self._last_modified = 0
        self._events = []
        self._lock = Lock()

    def components(self, path=None):
        self._lock.acquire()
        if getmtime(self._filename) > self._last_modified:
            self._events = Abook.vcard(self._filename)
            self._last_modified = getmtime(self._filename)
        self._lock.release()
        return [(v.serialize(), v.uid.value) for v in self._events]

    def text(self):
        cal = [e[0] for e in self.components()]
        return '\r\n\r\n'.join(cal).decode('utf-8')

    def append(self, text, filename):
        self._lock.acquire()
        book = ConfigObj(filename, encoding='utf-8', list_values=False)

        for card in readComponents(text):
            if ':' in card.uid.value:
                (section, oldhash) = card.uid.value.split(':')
            else:
                section = str(max([int(k) for k in book.keys()]) + 1)
            Abook.abook(card, section, book)
        Abook.write(book)
        self._lock.release()

    def remove(self, name, filename):
        self._lock.acquire()
        (section, delhash) = name.split(':')
        delhash = int(delhash)
        book = ConfigObj(filename, encoding='utf-8', list_values=False)
        linehash = hash(book[section]['name'])
        if linehash == delhash:
            del book[section]
            Abook.write(book)
        self._lock.release()

    @staticmethod
    def vcard(filename):
        book = ConfigObj(filename, encoding='utf-8', list_values=False)
        cards = []
        for (i, entry) in book.items()[1:]:
            card = vCard()
            card.add('uid').value = '%s:%d' % (i, hash(entry['name']))
            card.add('fn').value = entry['name']
            if 'nick' in entry:
                card.add('nickname').value = entry['nick']
            card.add('n').value = Name(family=entry['name'].split(' ')[-1], given=entry['name'].split(' ')[:-1])
            if 'email' in entry:
                for email in entry['email'].split(','):
                    card.add('email').value = email
            if 'phone' in entry:
                tel = card.add('tel')
                tel.type_param = 'home'
                tel.value = entry['phone']
            if 'workphone' in entry:
                tel = card.add('tel')
                tel.type_param = 'work'
                tel.value = entry['workphone']
            if 'mobile' in entry:
                tel = card.add('tel')
                tel.type_param = 'cell'
                tel.value = entry['mobile']
            if 'phone2' in entry:
                tel = card.add('tel')
                tel.type_param = 'x-assistant'
                tel.value = entry['phone2']
            if 'url' in entry:
                card.add('url').value = entry['url']
            for i in range(5):
                custom = 'custom%d' % i
                if custom in entry:
                    card.add('note').value = entry[custom]
            if 'address' in entry or 'address2' in entry or 'city' in entry or 'country' in entry or 'zip' in entry or 'country' in entry:
                address = entry.get('address', '')
                address2 = entry.get('address2', '')
                city = entry.get('city', '')
                zipn = entry.get('zip', '')
                state = entry.get('state', '')
                country = entry.get('country', '')
                card.add('adr').value = Address(extended=address2, street=address, city=city, region=state, code=zipn, country=country)
            try:
                jpeg = open(join(dirname(filename), 'photo/%s.jpeg' % entry['name']), 'rb').read()
                photo = card.add('photo')
                photo.type_param = 'jpeg'
                photo.encoding_param = 'b'
                photo.value = jpeg
            except IOError:
                pass
            cards.append(card)
        return cards

    @staticmethod
    def abook(card, section, book):
        book[section] = {}
        book[section]['name'] = card.fn.value

        if hasattr(card, 'email'):
            book[section]['email'] = ','.join([e.value for e in card.email_list])
        if hasattr(card, 'note_list'):
            for (i, note) in enumerate(card.note_list):
                book[section]['custom%d' % (i+1)] = note.value
        if hasattr(card, 'adr'):
            if card.adr.value.street:
                book[section]['address'] = card.adr.value.street
            if card.adr.value.extended:
                book[section]['address2'] = card.adr.value.extended
            if card.adr.value.city:
                book[section]['city'] = card.adr.value.city
            if card.adr.value.region:
                book[section]['state'] = card.adr.value.region
            if card.adr.value.code and card.adr.value.code != '0':
                book[section]['zip'] = card.adr.value.code
            if card.adr.value.country:
                book[section]['country'] = card.adr.value.country
        if hasattr(card, 'tel_list'):
            for tel in card.tel_list:
                if tel.TYPE_param.lower() == 'home':
                    book[section]['phone'] = tel.value
                elif tel.TYPE_param.lower() == 'x-assistant':
                    book[section]['phone2'] = tel.value
                elif tel.TYPE_param.lower() == 'work':
                    book[section]['workphone'] = tel.value
                elif tel.TYPE_param.lower() == 'cell':
                    book[section]['mobile'] = tel.value
        if hasattr(card, 'nickname'):
            book[section]['nick'] = card.nickname.value
        if hasattr(card, 'url'):
            book[section]['url'] = card.url.value
        if hasattr(card, 'photo') and book.filename:
            open(join(dirname(book.filename), 'photo/%s.%s' % (card.fn.value, card.photo.TYPE_param)), 'w').write(card.photo.value)

    @staticmethod
    def write(book):
        filename = book.filename
        book.filename = None
        entries = book.write()
        entries = [e.replace(' = ', '=', 1) for e in entries]
        if filename:
            open(filename, 'w').write('\n'.join(entries))
        else:
            return '\n'.join(entries)

def main():
    from sys import argv, stdout, stdin
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-v', '--vcard', action='store_true', help='Generate vCard output')
    (options, args) = parser.parse_args()
    if options.vcard:
        stdout.write('{0}\r\n'.format('\r\n'.join([v.serialize() for v in Abook.vcard(argv[2])])))
    else:
        book = ConfigObj(encoding='utf-8', list_values=False)
        book.initial_comment = ['abook addressbook file']
        book['format'] = {}
        book['format']['program'] = 'abook'
        book['format']['version'] = '0.6.0pre2'
        for (i, card) in enumerate(readComponents(stdin.read())):
            Abook.abook(card, str(i), book)
        stdout.write(Abook.write(book))

if __name__ == '__main__':
    main()
