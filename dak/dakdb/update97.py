# coding=utf8

"""
Create path entries for changelog exporting

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2013 Luca Falavigna <dktrkranz@debian.org>
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
    Move changelogs related config values into projectb
    """
    print(__doc__)
    try:
        c = self.db.cursor()
        c.execute("ALTER TABLE archive ADD COLUMN changelog text NULL")
        c.execute("UPDATE archive SET changelog = '/srv/ftp-master.debian.org/export/changelogs' WHERE name = 'ftp-master'")
        c.execute("UPDATE archive SET changelog = '/srv/backports-master.debian.org/export/changelogs' WHERE name = 'backports'")
        c.execute("DELETE FROM config WHERE name = 'exportpath'")
        c.execute("UPDATE config SET value = '97' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply table-column update 97, rollback issued. Error message : %s' % (str(msg)))
