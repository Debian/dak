#!/usr/bin/env python

"""
Add view for new generate_filelist command.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Torsten Werner <twerner@debian.org>
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
    print "Add views for generate_filelist to database."

    try:
        c = self.db.cursor()

        print "Drop old views."
        c.execute("DROP VIEW IF EXISTS binfiles_suite_component_arch CASCADE")
        c.execute("DROP VIEW IF EXISTS srcfiles_suite_component CASCADE")

        print "Create new views."
        c.execute("""
CREATE VIEW binfiles_suite_component_arch AS
  SELECT files.filename, binaries.type, location.path, location.component,
         bin_associations.suite, binaries.architecture
    FROM binaries
    JOIN bin_associations ON binaries.id = bin_associations.bin
    JOIN files ON binaries.file = files.id
    JOIN location ON files.location = location.id;
	    """)
        c.execute("""
CREATE VIEW srcfiles_suite_component AS
  SELECT files.filename, location.path, location.component,
         src_associations.suite
    FROM source
    JOIN src_associations ON source.id = src_associations.source
    JOIN files ON source.file = files.id
    JOIN location ON files.location = location.id;
	    """)

        print "Committing"
        c.execute("UPDATE config SET value = '23' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
        self.db.rollback()
        raise DBUpdateError("Database error, rollback issued. Error message : %s" % (str(msg)))

