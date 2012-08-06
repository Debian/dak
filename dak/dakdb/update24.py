#!/usr/bin/env python

"""
Add some meta info to queues

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

import psycopg2

def do_update(self):
    print "Add meta info columns to queues."

    try:
        c = self.db.cursor()

        c.execute("ALTER TABLE policy_queue ADD COLUMN generate_metadata BOOL DEFAULT FALSE NOT NULL")
        c.execute("ALTER TABLE policy_queue ADD COLUMN origin TEXT DEFAULT NULL")
        c.execute("ALTER TABLE policy_queue ADD COLUMN label TEXT DEFAULT NULL")
        c.execute("ALTER TABLE policy_queue ADD COLUMN releasedescription TEXT DEFAULT NULL")
        c.execute("ALTER TABLE policy_queue ADD COLUMN signingkey TEXT DEFAULT NULL")
        c.execute("ALTER TABLE policy_queue ADD COLUMN stay_of_execution INT4 NOT NULL DEFAULT 86400 CHECK (stay_of_execution >= 0)")
        c.execute("""ALTER TABLE policy_queue
                       ADD CONSTRAINT policy_queue_meta_sanity_check
                           CHECK ( (generate_metadata IS FALSE)
                                OR (origin IS NOT NULL AND label IS NOT NULL AND releasedescription IS NOT NULL) )""")

        c.execute("ALTER TABLE build_queue ADD COLUMN generate_metadata BOOL DEFAULT FALSE NOT NULL")
        c.execute("ALTER TABLE build_queue ADD COLUMN origin TEXT DEFAULT NULL")
        c.execute("ALTER TABLE build_queue ADD COLUMN label TEXT DEFAULT NULL")
        c.execute("ALTER TABLE build_queue ADD COLUMN releasedescription TEXT DEFAULT NULL")
        c.execute("ALTER TABLE build_queue ADD COLUMN signingkey TEXT DEFAULT NULL")
        c.execute("ALTER TABLE build_queue ADD COLUMN stay_of_execution INT4 NOT NULL DEFAULT 86400 CHECK (stay_of_execution >= 0)")
        c.execute("""ALTER TABLE build_queue
                       ADD CONSTRAINT build_queue_meta_sanity_check
                           CHECK ( (generate_metadata IS FALSE)
                                OR (origin IS NOT NULL AND label IS NOT NULL AND releasedescription IS NOT NULL) )""")

        print "Committing"
        c.execute("UPDATE config SET value = '24' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
        self.db.rollback()
        raise DBUpdateError("Database error, rollback issued. Error message : %s" % (str(msg)))

