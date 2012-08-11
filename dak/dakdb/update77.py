#!/usr/bin/env python
# coding=utf8

"""
Move stayofexecution to the database

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

	stayofexecution = cnf.get('Clean-Suites::StayOfExecution', '129600')
	c.execute("ALTER TABLE archive ADD COLUMN stayofexecution INTERVAL NOT NULL DEFAULT %s", (stayofexecution,))
        c.execute("UPDATE archive SET stayofexecution='0' WHERE name IN ('new', 'policy', 'build-queues')")

        c.execute("UPDATE config SET value = '77' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 77, rollback issued. Error message: {0}'.format(msg))
