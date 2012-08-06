#!/usr/bin/env python
# coding=utf8

"""
Just a view for version checks

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Joerg Jaspert <joerg@debian.org>
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

################################################################################
def do_update(self):
    """
    Just a view for version checks
    """
    print __doc__
    try:
        c = self.db.cursor()

        c.execute("""
        CREATE OR REPLACE VIEW version_checks AS
        SELECT s.suite_name AS source_suite, v.check as condition, t.suite_name AS target_suite
        FROM suite s
         JOIN version_check v ON (s.id = v.suite)
         JOIN suite t ON (v.reference = t.id)
        ORDER BY source_suite, condition, target_suite;
        """)

        c.execute("GRANT SELECT on version_checks TO PUBLIC;")
        c.execute("UPDATE config SET value = '61' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 61, rollback issued. Error message : %s' % (str(msg)))
