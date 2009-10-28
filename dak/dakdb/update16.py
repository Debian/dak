#!/usr/bin/env python
# coding=utf8

"""
Adding tables for key-based ACLs and blocks

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
from daklib.dak_exceptions import DBUpdateError

################################################################################

def do_update(self):
    print "Adding tables for handling key-based ACLs and upload blocks"

    try:
        c = self.db.cursor()

        # Fix up some older table permissions
        c.execute("GRANT SELECT ON src_format TO public")
        c.execute("GRANT ALL ON src_format TO ftpmaster")
        c.execute("GRANT USAGE ON src_format_id_seq TO ftpmaster")

        c.execute("GRANT SELECT ON suite_src_formats TO public")
        c.execute("GRANT ALL ON suite_src_formats TO ftpmaster")

        # Source ACLs table
        print "Source ACLs table"
        c.execute("""
        CREATE TABLE source_acl (
              id SERIAL PRIMARY KEY,
              access_level TEXT UNIQUE NOT NULL
        )
        """)

        ## Can upload all packages
        c.execute("INSERT INTO source_acl (id, access_level) VALUES (1, 'full')")
        ## Can upload only packages marked as DM upload allowed
        c.execute("INSERT INTO source_acl (id, access_level) VALUES (2, 'dm')")

        c.execute("GRANT SELECT ON source_acl TO public")
        c.execute("GRANT ALL ON source_acl TO ftpmaster")
        c.execute("GRANT USAGE ON source_acl_id_seq TO ftpmaster")

        # Binary ACLs table
        print "Binary ACLs table"
        c.execute("""
        CREATE TABLE binary_acl (
              id SERIAL PRIMARY KEY,
              access_level TEXT UNIQUE NOT NULL
        )
        """)

        ## Can upload any architectures of binary packages
        c.execute("INSERT INTO binary_acl (id, access_level) VALUES (1, 'full')")
        ## Can upload debs where architectures are based on the map table binary_acl_map
        c.execute("INSERT INTO binary_acl (id, access_level) VALUES (2, 'map')")

        c.execute("GRANT SELECT ON binary_acl TO public")
        c.execute("GRANT ALL ON binary_acl TO ftpmaster")
        c.execute("GRANT USAGE ON binary_acl_id_seq TO ftpmaster")

        # This is only used if binary_acl is 2 for the fingerprint concerned
        c.execute("""
        CREATE TABLE binary_acl_map (
              id SERIAL PRIMARY KEY,
              fingerprint_id INT4 REFERENCES fingerprint (id) NOT NULL,
              architecture_id INT4 REFERENCES architecture (id) NOT NULL,

              UNIQUE (fingerprint_id, architecture_id)
        )""")

        c.execute("GRANT SELECT ON binary_acl_map TO public")
        c.execute("GRANT ALL ON binary_acl_map TO ftpmaster")
        c.execute("GRANT USAGE ON binary_acl_map_id_seq TO ftpmaster")

        ## NULL means no source upload access (i.e. any upload containing source
        ## will be rejected)
        c.execute("ALTER TABLE fingerprint ADD COLUMN source_acl_id INT4 REFERENCES source_acl(id) DEFAULT NULL")

        ## NULL means no binary upload access
        c.execute("ALTER TABLE fingerprint ADD COLUMN binary_acl_id INT4 REFERENCES binary_acl(id) DEFAULT NULL")

        # Blockage table (replaces the hard coded stuff we used to have in extensions)
        print "Adding blockage table"
        c.execute("""
        CREATE TABLE upload_blocks (
              id             SERIAL PRIMARY KEY,
              source         TEXT NOT NULL,
              version        TEXT DEFAULT NULL,
              fingerprint_id INT4 REFERENCES fingerprint (id),
              uid_id         INT4 REFERENCES uid (id),
              reason         TEXT NOT NULL,

              CHECK (fingerprint_id IS NOT NULL OR uid_id IS NOT NULL)
        )""")

        c.execute("GRANT SELECT ON upload_blocks TO public")
        c.execute("GRANT ALL ON upload_blocks TO ftpmaster")
        c.execute("GRANT USAGE ON upload_blocks_id_seq TO ftpmaster")

        print "Updating config version"
        c.execute("UPDATE config SET value = '16' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        raise DBUpdateError, "Unable to apply ACLs update (16), rollback issued. Error message : %s" % (str(msg))
