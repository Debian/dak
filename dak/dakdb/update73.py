#!/usr/bin/env python
# coding=utf8

"""
Reference archive table from suite and add path to archive root

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2012 Ansgar Burchardt <ansgar@debian.org>
@license: GNU General Public License version 2 or later
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

import psycopg2
from daklib.dak_exceptions import DBUpdateError
from daklib.config import Config

################################################################################
def do_update(self):
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        archive_root = cnf["Dir::Root"]
        c.execute("ALTER TABLE archive ADD COLUMN path TEXT NOT NULL DEFAULT %s", (archive_root,))
        c.execute("ALTER TABLE archive ALTER COLUMN path DROP DEFAULT")

        c.execute("ALTER TABLE archive ADD COLUMN mode CHAR(4) NOT NULL DEFAULT '0644' CHECK (mode SIMILAR TO '[0-7]{4}')")
        c.execute("ALTER TABLE archive ADD COLUMN tainted BOOLEAN NOT NULL DEFAULT 'f'")
        c.execute("ALTER TABLE archive ADD COLUMN use_morgue BOOLEAN NOT NULL DEFAULT 't'")

        c.execute("SELECT id FROM archive")
        (archive_id,) = c.fetchone()

        if c.fetchone() is not None:
            raise DBUpdateError("Cannot automatically upgrade form installation with multiple archives.")

        c.execute("ALTER TABLE suite ADD COLUMN archive_id INT REFERENCES archive(id) NOT NULL DEFAULT %s", (archive_id,))
        c.execute("ALTER TABLE suite ALTER COLUMN archive_id DROP DEFAULT")

        c.execute("UPDATE config SET value = '73' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 73, rollback issued. Error message : %s' % (str(msg)))
