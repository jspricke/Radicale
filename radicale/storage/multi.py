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
Multi storage backend.

"""

from os.path import expanduser
from time import strftime
from contextlib import contextmanager
from .. import config, ical

class Empty(object):

    def vcal(self):
        return [Collection(REM, '/remind'), Collection(ABOOK, '/abook')]

    def text(self):
        return ""

    def last_modified(self):
        return ""

    def append(self, text):
        raise NotImplementedError

    def remove(self, name):
        raise NotImplementedError

from remind import Remind
from abook import Abook
EMPTY = Empty()
REM = Remind(expanduser(config.get("storage", "remind_file")))
ABOOK = Abook(expanduser(config.get("storage", "abook_file")))

class Collection(ical.Collection):
    """Collection Adapter for remind and abook storage."""

    def __init__(self, storage, storPath, principal=False):
        super(Collection, self).__init__(storPath, principal)
        self._rem = storage

    def append(self, name, text):
        """Append items from ``text`` to collection.

        If ``name`` is given, give this name to new items in ``text``.

        """
        self._rem.append(text)

    def remove(self, name):
        """Remove object named ``name`` from collection."""
        self._rem.remove(name)

    def replace(self, name, text):
        """Replace content by ``text`` in collection objet called ``name``."""
        self.remove(name)
        self.append(name, text)

    @property
    def text(self):
        return self._rem.text()

    @property
    def components(self):
        """Get list of all components in collection."""
        items = self._rem.vcal()
        if isinstance(self._rem, Remind):
            return [ical.Event(text = item[0], name = item[1]) for item in items]
        elif isinstance(self._rem, Abook):
            return [ical.Card(text = item[0], name = item[1]) for item in items]
        return items

    @classmethod
    def from_path(cls, path, depth="1", include_container=True):
        if path == '/':
            storage = EMPTY
            storPath = ''
        elif path.startswith('/remind'):
            storage = REM
            storPath = '/remind'
        elif path.startswith('/abook'):
            storage = ABOOK
            storPath = '/abook'
        else:
            raise NotImplementedError
        if depth == "0":
            return [cls(storage, storPath, True)]

        result = []
        collection = cls(storage, storPath, True)
        if include_container:
            result.append(collection)
        result.extend(collection.components)
        return result

    @classmethod
    def is_node(cls, path):
        return path == ""

    def is_leaf(self, path):
        return path != "" and path.startswith(self.path)

    @property
    def last_modified(self):
        return strftime("%a, %d %b %Y %H:%M:%S +0000", self._rem.last_modified())

    @property
    @contextmanager
    def props(self):
        # On enter
        if isinstance(self._rem, Abook):
            yield {'tag': 'VADDRESSBOOK', 'A:calendar-color': '#33b5e5'}
        else:
            yield {'tag': 'VCALENDAR', 'A:calendar-color': '#33b5e5'}
        # On exit
