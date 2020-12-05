# coding=utf8

"""
Add a new release_suite name which we use in generate_releases

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2014, Mark Hymers <mhy@debian.org>
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

# This includes some updates to the tables which are Debian specific but
# shouldn't affect anyone else
statements = [
"ALTER TABLE suite ADD COLUMN release_suite TEXT DEFAULT NULL",
"UPDATE suite SET release_suite = 'oldstable-updates' WHERE suite_name = 'squeeze-updates'",
"UPDATE suite SET release_suite = 'stable-updates' WHERE suite_name = 'wheezy-updates'",
"UPDATE suite SET release_suite = 'testing-updates' WHERE suite_name = 'jessie-updates'",
]

################################################################################


def do_update(self):
    print(__doc__)
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("UPDATE config SET value = '105' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 105, rollback issued. Error message: {0}'.format(msg))
