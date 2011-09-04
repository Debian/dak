#!/usr/bin/env python
# coding=utf8

"""
Add missing PrimaryMirror field to archive table

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Mark Hymers <mhy@debian.org>
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
    Add missing PrimaryMirror field to archive table
    """
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        c.execute("ALTER TABLE archive ADD COLUMN primary_mirror TEXT")

        c.execute("SELECT id, name FROM archive")

        query = "UPDATE archive SET primary_mirror = %s WHERE id = %s"
        for a_id, a_name in c.fetchall():
            if cnf.has_key('Archive::%s::PrimaryMirror' % a_name):
                primloc = cnf['Archive::%s::PrimaryMirror' % a_name]
                print "Setting archive %s PrimaryMirror to %s" % (a_name, primloc)
                c.execute(query, [primloc, a_id])

        c.execute("UPDATE config SET value = '63' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 63, rollback issued. Error message : %s' % (str(msg)))
