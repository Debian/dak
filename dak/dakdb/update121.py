# coding=utf8

"""
Update changes table to not require a value for the Binary column

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2018, Guillem Jover <guillem@debian.org>
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
    Update changes table to not require a value for the Binary column, as it
    can be missing on source-only uploads since dpkg 1.19.3.
    """
    print(__doc__)
    try:
        c = self.db.cursor()

        c.execute("""
          ALTER TABLE changes
            ALTER COLUMN binaries DROP NOT NULL
        """)

        c.execute("UPDATE config SET value = '121' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 121, rollback issued. Error message : %s' % (str(msg)))
