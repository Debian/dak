#!/usr/bin/env python
# coding=utf8

"""
Fix permissions again

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Mark Hymers <mhy@debian.org>
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
    Fix up permissions (again)
    """
    print __doc__
    try:
        c = self.db.cursor()

        for table in ['build_queue_policy_files',
                      'version_check']:
            c.execute("""GRANT SELECT, UPDATE, INSERT ON %s TO ftpmaster""" % table)
            c.execute("""GRANT SELECT ON %s TO public""" % table)

        # Make sure all sequences are fixed up
        for seq in ['architecture_id_seq',
                    'archive_id_seq',
                    'bin_associations_id_seq',
                    'binaries_id_seq',
                    'binary_acl_id_seq',
                    'binary_acl_map_id_seq',
                    'build_queue_files_id_seq',
                    'build_queue_id_seq',
                    'changelogs_text_id_seq',
                    'changes_id_seq',
                    'changes_pending_binaries_id_seq',
                    'changes_pending_files_id_seq',
                    'changes_pending_source_id_seq',
                    'component_id_seq',
                    'config_id_seq',
                    'dsc_files_id_seq',
                    'files_id_seq',
                    'fingerprint_id_seq',
                    'keyring_acl_map_id_seq',
                    'keyrings_id_seq',
                    'location_id_seq',
                    'maintainer_id_seq',
                    'metadata_keys_key_id_seq',
                    'new_comments_id_seq',
                    'override_type_id_seq',
                    'policy_queue_id_seq',
                    'priority_id_seq',
                    'section_id_seq',
                    'source_acl_id_seq',
                    'source_id_seq',
                    'src_associations_id_seq',
                    'src_format_id_seq',
                    'src_uploaders_id_seq',
                    'suite_id_seq',
                    'uid_id_seq',
                    'upload_blocks_id_seq']:
            c.execute("""GRANT SELECT, UPDATE, USAGE ON %s TO ftpmaster""" % seq)
            c.execute("""GRANT SELECT ON %s TO public""" % seq)

        c.execute("UPDATE config SET value = '58' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 58, rollback issued. Error message : %s' % (str(msg)))
