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
Multi storage backend.

"""

from os.path import expanduser, basename, dirname, getmtime
from time import strftime, gmtime
from contextlib import contextmanager
from .. import config, ical

class Empty(object):

    def components(self, path):
        return [Collection(USER, '/%s' % config.get('storage', 'multi_user'))]

    def text(self):
        return ''

    def append(self, text):
        raise NotImplementedError

    def remove(self, name):
        raise NotImplementedError

class User(object):

    def components(self, path):
        return [Collection(REM, i) for i in REM.get_files()] + [Collection(ABOOK, config.get('storage', 'abook_file'))]

    def text(self):
        return ''

    def append(self, text):
        raise NotImplementedError

    def remove(self, name):
        raise NotImplementedError

from remind import Remind
from abook import Abook
from dateutil.tz import gettz
EMPTY = Empty()
USER = User()
tz = gettz(expanduser(config.get('storage', 'timezone')))
# Manually set timezone name to generate correct ical files
# (python-vobject tests for the zone attribute)
tz.zone = expanduser(config.get('storage', 'timezone'))
REM = Remind(tz, expanduser(config.get('storage', 'remind_file')))
ABOOK = Abook(expanduser(config.get('storage', 'abook_file')))

class Collection(ical.Collection):
    """Collection Adapter for remind and abook storage."""

    def __init__(self, storage, storPath, principal=False):
        super(Collection, self).__init__(storPath, principal)
        self._storage = storage

    def append(self, name, text):
        """Append items from ``text`` to collection.

        If ``name`` is given, give this name to new items in ``text``.

        """
        self._storage.append(text, self.path)

    def remove(self, name):
        """Remove object named ``name`` from collection."""
        self._storage.remove(name, self.path)

    def replace(self, name, text):
        """Replace content by ``text`` in collection objet called ``name``."""
        self.remove(name)
        self.append(name, text)

    @property
    def text(self):
        return self._storage.text()

    @property
    def components(self):
        """Get list of all components in collection."""
        items = self._storage.components(self.path)
        if isinstance(self._storage, Remind):
            return self._parse(items, (ical.Event, ))
        elif isinstance(self._storage, Abook):
            return [ical.Card(text=item[0].decode('utf-8'), name=item[1]) for item in items]
        return items

    @classmethod
    def from_path(cls, path, depth='1', include_container=True):
        path = dirname(path)
        if path == '/%s' % config.get('storage', 'multi_user'):
            storage = USER
        elif 'remind' in path:
            storage = REM
        elif 'abook' in path:
            storage = ABOOK
        else:
            storage = EMPTY
        if depth == '0':
            return [Collection(storage, path, True)]

        result = []
        collection = Collection(storage, path, True)
        if include_container:
            result.append(collection)
        result.extend(collection.components)
        return result

    @classmethod
    def is_node(cls, path):
        return path == '' or path == '/%s' % config.get('storage', 'multi_user')

    def is_leaf(self, path):
        return path != '' and path != '/%s' % config.get('storage', 'multi_user') and path.startswith(self.path)

    @property
    def last_modified(self):
        return strftime('%a, %d %b %Y %H:%M:%S +0000', gmtime(getmtime(self.path)))

    @property
    @contextmanager
    def props(self):
        # On enter
        if isinstance(self._storage, Abook):
            yield {'tag': 'VADDRESSBOOK', 'A:calendar-color': '#33b5e5'}
        else:
            yield {'tag': 'VCALENDAR', 'A:calendar-color': '#%06x' % (hash(basename(self.path)) % 0xffffff)}
        # On exit
