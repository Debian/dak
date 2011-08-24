#!/usr/bin/env python
# coding=utf8

"""
Add order column to metadata_keys

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

################################################################################
def do_update(self):
    """
    Add order column to metadata_keys
    """
    print __doc__
    try:
        c = self.db.cursor()

        c.execute("ALTER TABLE metadata_keys ADD COLUMN ordering INTEGER NOT NULL DEFAULT 0")

        initial_order = {
                'Package': -2600,
                'Source': -2500,
                'Binary': -2400,
                'Version': -2300,
                'Essential': -2250,
                'Installed-Size': -2200,
                'Maintainer': -2100,
                'Uploaders': -2090,
                'Original-Maintainer': -2080,
                'Build-Depends': -2000,
                'Build-Depends-Indep': -1990,
                'Build-Conflicts': -1980,
                'Build-Conflicts-Indep': -1970,
                'Architecture': -1800,
                'Standards-Version': -1700,
                'Format': -1600,
                'Files': -1500,
                'DM-Upload-Allowed': -1400,
                'Vcs-%': -1300,
                'Checksums-%': -1200,
                'Replaces': -1100,
                'Provides': -1000,
                'Depends': -900,
                'Pre-Depends': -850,
                'Recommends': -800,
                'Suggests': -700,
                'Enhances': -650,
                'Conflicts': -600,
                'Breaks': -500,
                'Description': -400,
                'Origin': -300,
                'Bugs': -200,
                'Multi-Arch': -150,
                'Homepage': -100,
                'Tag': 300,
                'Package-Type': 400,
                'Installer-Menu-Item': 500,
                }

        for key, order in initial_order.items():
            c.execute("""UPDATE metadata_keys SET ordering = '%s' WHERE key ILIKE '%s'""" % (order, key))

        c.execute("UPDATE config SET value = '56' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 56, rollback issued. Error message : %s' % (str(msg)))
