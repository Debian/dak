# coding=utf8
"""
Add separate Contents-all support settings for suites

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2020, Niels Thykier <niels@thykier.net>
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
    Update default settings for suites
    """
    print(__doc__)
    try:
        c = self.db.cursor()

        c.execute("""
          ALTER TABLE suite
            ADD COLUMN separate_contents_architecture_all boolean NOT NULL DEFAULT FALSE,
            ADD COLUMN separate_packages_architecture_all boolean NOT NULL DEFAULT FALSE
        """)

        #  We do not support separate Packages-all at the moment, so ensure it is
        #  never set at all.  We still add it to the database because we can use
        #  it for adding basic support as well as setup some basic control
        #  checks for now. When we are ready to support
        #  separate_packages_architecture_all, then we should replace this
        #  check with:
        #
        #     CHECK (NOT separate_packages_architecture_all OR separate_contents_architecture_all)
        #
        #  This is because clients are not required to support separate Packages-all without
        #  Contents-all according to:
        #     https://wiki.debian.org/DebianRepository/Format#No-Support-for-Architecture-all
        #
        c.execute("""
        ALTER TABLE suite
            ADD CHECK (NOT separate_packages_architecture_all)
        """)

        c.execute("UPDATE config SET value = '123' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 123, rollback issued. Error message : %s' % (str(msg)))
