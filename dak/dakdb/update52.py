#!/usr/bin/env python
# coding=utf8

"""
Add table for version checks.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Ansgar Burchardt <ansgar@debian.org>
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
    Add table for version checks.
    """
    print __doc__
    try:
        cnf = Config()
        c = self.db.cursor()

        c.execute("""
            CREATE TABLE version_check (
                suite INTEGER NOT NULL REFERENCES suite(id),
                "check" TEXT NOT NULL CHECK ("check" IN ('Enhances', 'MustBeNewerThan', 'MustBeOlderThan')),
                reference INTEGER NOT NULL REFERENCES suite(id),
                PRIMARY KEY(suite, "check", reference)
            )""")

        c.execute("SELECT suite_name, id FROM suite")
        suites = c.fetchall()
        suite_id_map = {}
        for suite_name, suite_id in suites:
            suite_id_map[suite_name] = suite_id

        for check in ["Enhances", "MustBeNewerThan", "MustBeOlderThan"]:
           for suite_name in suite_id_map.keys():
	       for reference_name in [ s.lower() for s in cnf.value_list("Suite::%s::VersionChecks::%s" % (suite_name, check)) ]:
                   c.execute("""INSERT INTO version_check (suite, "check", reference) VALUES (%s, %s, %s)""", (suite_id_map[suite_name], check, suite_id_map[reference_name]))

        c.execute("UPDATE config SET value = '52' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 52, rollback issued. Error message : %s' % (str(msg)))
