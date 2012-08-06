#!/usr/bin/env python

"""
Add created,modified columns for all tables.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Barry deFreese <bdefreese@debian.org>
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
    print "Add created, modified fields for all tables."

    updatetables = ['architecture', 'archive', 'bin_associations', 'bin_contents',
        'binaries', 'binary_acl', 'binary_acl_map', 'build_queue', 'build_queue_files',
        'changes', 'changes_pending_binaries', 'changes_pending_files',
        'changes_pending_files_map', 'changes_pending_source', 'changes_pending_source_files',
        'changes_pool_files', 'component', 'config', 'dsc_files', 'files', 'fingerprint',
        'keyring_acl_map', 'keyrings', 'location', 'maintainer', 'new_comments', 'override',
        'override_type', 'policy_queue', 'priority', 'section', 'source', 'source_acl',
        'src_associations', 'src_format', 'src_uploaders', 'suite', 'suite_architectures',
        'suite_build_queue_copy', 'suite_src_formats', 'uid', 'upload_blocks']

    c = self.db.cursor()

    print "Create trigger function."
    c.execute("""CREATE OR REPLACE FUNCTION tfunc_set_modified() RETURNS trigger AS $$
    BEGIN NEW.modified = now(); return NEW; END;
    $$ LANGUAGE 'plpgsql'""")

    try:
        for updatetable in updatetables:

            print "Add created field to %s." % updatetable
            c.execute("ALTER TABLE %s ADD COLUMN created TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()" % updatetable)

            print "Add modified field to %s." % updatetable
            c.execute("ALTER TABLE %s ADD COLUMN modified TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()" % updatetable)

            print "Create modified trigger."
            c.execute("""CREATE TRIGGER modified_%s BEFORE UPDATE ON %s
            FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified()""" % (updatetable, updatetable))

        print "Committing"
        c.execute("UPDATE config SET value = '26' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
            self.db.rollback()
            raise DBUpdateError("Database error, rollback issued. Error message : %s" % (str(msg)))

