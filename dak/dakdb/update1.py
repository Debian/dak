#!/usr/bin/env python

"""
Saner DM db schema

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008  Michael Casadevall <mcasadevall@debian.org>
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

# <tomv_w> really, if we want to screw ourselves, let's find a better way.
# <Ganneff> rm -rf /srv/ftp.debian.org

################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError

################################################################################

def do_update(self):
    print "Adding DM fields to database"

    try:
        c = self.db.cursor()
        c.execute("ALTER TABLE source ADD COLUMN dm_upload_allowed BOOLEAN DEFAULT 'no' NOT NULL;")
        c.execute("ALTER TABLE keyrings ADD COLUMN debian_maintainer BOOLEAN DEFAULT 'false' NOT NULL;")

        print "Migrating DM data to source table. This might take some time ..."

        c.execute("UPDATE source SET dm_upload_allowed = 't' WHERE id IN (SELECT source FROM src_uploaders);")
        c.execute("UPDATE config SET value = '1' WHERE name = 'db_revision'")

        print "Migrating DM uids to normal uids"
        c.execute("SELECT uid FROM uid WHERE uid  LIKE 'dm:%'")
        rows = c.fetchall()
        for r in rows:
            uid = r[0]
            c.execute("UPDATE uid SET uid = '%s' WHERE uid = '%s'" % (uid[3:], uid))

        self.db.commit()

        print "IMPORTANT: Set the debian_maintainer flag in the config file for keyrings that are DMs!"
        print "           Failure to do so will result in DM's having full upload abilities!"
        print "REMINDER: Remember to run the updated byhand-dm crontab to update Debian Maintainer information"
        print ""
        print "Pausing for five seconds ..."
        time.sleep (5)

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to appy DM table updates, rollback issued. Error message : %s" % (str(msg)))
