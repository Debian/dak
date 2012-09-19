#!/usr/bin/env python
# coding=utf8

"""
add created_by_id and created columns to acl_per_source table

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

        c.execute("""ALTER TABLE acl_per_source
                     ADD COLUMN created_by_id INTEGER REFERENCES fingerprint(id),
                     ADD COLUMN created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP""")

        c.execute("UPDATE config SET value = '90' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 90, rollback issued. Error message: {0}'.format(msg))
