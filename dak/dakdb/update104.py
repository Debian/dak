# coding=utf8

"""
Drop created and modified columns from bin_contents and src_contents

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2014, Ansgar Burchardt <ansgar@debian.org>
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

statements = [
"DROP TRIGGER IF EXISTS modified_bin_contents ON bin_contents",
"ALTER TABLE bin_contents DROP COLUMN created, DROP COLUMN modified",
"DROP TRIGGER IF EXISTS modified_src_contents ON src_contents",
"ALTER TABLE src_contents DROP COLUMN created, DROP COLUMN modified",
]

################################################################################


def do_update(self):
    print(__doc__)
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("UPDATE config SET value = '104' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 104, rollback issued. Error message: {0}'.format(msg))
