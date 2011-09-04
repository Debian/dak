#!/usr/bin/env python
# coding=utf8

"""
Add 2 partial indexes to speed up dak rm.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Torsten Werner <twerner@debian.org>
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
    """
    Add 2 partial indexes to speed up dak rm.
    """
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        # partial index for Depends
        c.execute("SELECT key_id FROM metadata_keys WHERE key = 'Depends'")
        key = c.fetchone()[0]
        c.execute("""CREATE INDEX binaries_metadata_depends
            ON binaries_metadata (bin_id) WHERE key_id = %d""" % key)

        # partial index for Provides
        c.execute("SELECT key_id FROM metadata_keys WHERE key = 'Provides'")
        key = c.fetchone()[0]
        c.execute("""CREATE INDEX binaries_metadata_provides
            ON binaries_metadata (bin_id) WHERE key_id = %d""" % key)

        c.execute("UPDATE config SET value = '66' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 66, rollback issued. Error message : %s' % (str(msg)))
