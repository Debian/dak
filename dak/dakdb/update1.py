#!/usr/bin/env python

# Debian Archive Kit Database Update Script
# Copyright (C) 2008  Michael Casadevall <mcasadevall@debian.org>

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

################################################################################

def do_update(self):
    print "Adding DM fields to database"

    try:
       c = self.db.cursor()
       c.execute("ALTER TABLE source ADD COLUMN dm_upload_allowed BOOLEAN DEFAULT 'no' NOT NULL;")
       c.execute("ALTER TABLE fingerprint ADD COLUMN is_dm BOOLEAN DEFAULT 'false' NOT NULL;")

       print "Migrating DM data to source table. This might take some time ..."

       c.execute("UPDATE source SET dm_upload_allowed = 't' WHERE id = (SELECT source FROM src_uploaders);")
       c.execute("UPDATE config SET value = '1' WHERE name = 'db_revision'")
       self.db.commit()

       print "REMINDER: Remember to run the updated byhand-dm crontab to update Debian Maintainer information"

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        print "FATAL: Unable to apply DM table update 1!"
        print "Error Message: " + str(msg)
        print "Database changes have been rolled back."
