#!/usr/bin/env python
# coding=utf8

"""
Move to using the C version of debversion

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
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


################################################################################

import psycopg2
import time
import os
import datetime
import traceback

from daklib.dak_exceptions import DBUpdateError
from daklib.config import Config

################################################################################

def do_update(self):
    print "Converting database to use new C based debversion type"

    try:
        c = self.db.cursor()

        print "Temporarily converting columns to TEXT"
        c.execute("ALTER TABLE binaries ALTER COLUMN version TYPE TEXT")
        c.execute("ALTER TABLE source ALTER COLUMN version TYPE TEXT")
        c.execute("ALTER TABLE upload_blocks ALTER COLUMN version TYPE TEXT")
        c.execute("ALTER TABLE pending_content_associations ALTER COLUMN version TYPE TEXT")

        print "Dropping old debversion type"
        c.execute("DROP OPERATOR >(debversion, debversion)")
        c.execute("DROP OPERATOR <(debversion, debversion)")
        c.execute("DROP OPERATOR <=(debversion, debversion)")
        c.execute("DROP OPERATOR >=(debversion, debversion)")
        c.execute("DROP OPERATOR =(debversion, debversion)")
        c.execute("DROP OPERATOR <>(debversion, debversion)")
        c.execute("DROP FUNCTION debversion_eq(debversion,debversion)")
        c.execute("DROP FUNCTION debversion_ge(debversion,debversion)")
        c.execute("DROP FUNCTION debversion_gt(debversion,debversion)")
        c.execute("DROP FUNCTION debversion_le(debversion,debversion)")
        c.execute("DROP FUNCTION debversion_lt(debversion,debversion)")
        c.execute("DROP FUNCTION debversion_ne(debversion,debversion)")
        c.execute("DROP FUNCTION debversion_compare(debversion,debversion)")
        c.execute("DROP FUNCTION debversion_revision(debversion)")
        c.execute("DROP FUNCTION debversion_version(debversion)")
        c.execute("DROP FUNCTION debversion_epoch(debversion)")
        c.execute("DROP FUNCTION debversion_split(debversion)")
        c.execute("DROP TYPE debversion")

        # URGH - kill me now
        print "Importing new debversion type"
        f = open('/usr/share/postgresql/8.4/contrib/debversion.sql', 'r')
        cmds = []
        curcmd = ''
        for j in f.readlines():
            j = j.replace('\t', '').replace('\n', '').split('--')[0]
            if not j.startswith('--'):
                jj = j.split(';')
                curcmd += " " + jj[0]
                if len(jj) > 1:
                    for jjj in jj[1:]:
                        if jjj.strip() == '':
                            cmds.append(curcmd)
                            curcmd = ''
                        else:
                            curcmd += " " + jjj

        for cm in cmds:
            c.execute(cm)

        print "Converting columns to new debversion type"
        c.execute("ALTER TABLE binaries ALTER COLUMN version TYPE debversion")
        c.execute("ALTER TABLE source ALTER COLUMN version TYPE debversion")
        c.execute("ALTER TABLE upload_blocks ALTER COLUMN version TYPE debversion")
        c.execute("ALTER TABLE pending_content_associations ALTER COLUMN version TYPE debversion")

        print "Committing"
        c.execute("UPDATE config SET value = '19' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply debversion update 19, rollback issued. Error message : %s" % (str(msg)))
