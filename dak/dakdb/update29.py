#!/usr/bin/env python
# coding=utf8

"""
Adding content fields

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2010  Mike O'Connor <stew@debian.org>
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

################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError

################################################################################

def do_update(self):
    print "revert update6 since we have a new scheme for contents"

    try:
        c = self.db.cursor()
        c.execute("""DROP FUNCTION comma_concat(text, text) CASCADE;""" );
        c.execute("""DROP TABLE pending_content_associations;""")
        c.execute("""DROP TABLE content_associations;""")
        c.execute("""DROP TABLE content_file_names;""")
        c.execute("""DROP TABLE content_file_paths;""")

        c.execute("UPDATE config SET value = '29' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to appy debversion updates, rollback issued. Error message : %s" % (str(msg)))
