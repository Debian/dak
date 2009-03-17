#!/usr/bin/env python
# coding=utf8

"""
Debian Archive Kit Database Update Script
Copyright © 2008 Michael Casadevall <mcasadevall@debian.org>
Copyright © 2009 Mike O'Connor <stew@debian.org>

Debian Archive Kit Database Update Script 8
"""

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

################################################################################


################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError
from daklib.utils import get_conf

################################################################################

def do_update(self):
    print "add package_type enum"
    Cnf = get_conf()

    try:
        c = self.db.cursor()

        c.execute("CREATE TYPE package_type AS ENUM('deb','udeb','tdeb', 'dsc')")
        c.execute("ALTER TABLE binaries RENAME COLUMN type to type_text" );
        c.execute("ALTER TABLE binaries ADD COLUMN type package_type" );
        c.execute("UPDATE binaries set type=type_text::package_type" );
        c.execute("ALTER TABLE binaries DROP COLUMN type_text" );
        c.execute("CREATE INDEX binary_type_ids on binaries(type)")

        self.db.commit()

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        raise DBUpdateError, "Unable to apply binary type enum update, rollback issued. Error message : %s" % (str(msg))
