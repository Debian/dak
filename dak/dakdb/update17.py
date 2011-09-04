#!/usr/bin/env python
# coding=utf8

"""
adding a bin_contents table to hold lists of files contained in .debs and .udebs

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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

    print "adding a bin_contents table to hold lists of files contained in .debs and .udebs"

    try:
        c = self.db.cursor()
        c.execute("""CREATE TABLE bin_contents (
        file text,
        binary_id integer,
        UNIQUE(file,binary_id))""" )

        c.execute("""ALTER TABLE ONLY bin_contents
        ADD CONSTRAINT bin_contents_bin_fkey
        FOREIGN KEY (binary_id) REFERENCES binaries(id)
        ON DELETE CASCADE;""")

        c.execute("""CREATE INDEX ind_bin_contents_binary ON bin_contents(binary_id);""" )

        c.execute("GRANT ALL ON bin_contents TO ftpmaster;")
        c.execute("GRANT SELECT ON bin_contents TO public;")
        c.execute("UPDATE config SET value = '17' WHERE name = 'db_revision'")

        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply process-new update 17, rollback issued. Error message : %s" % (str(msg)))



