# coding=utf8

"""set owner tables for sequences

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2018, Bastian Blank <waldi@debian.org>
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
from daklib.config import Config

sequences = {
    'acl_id_seq': 'acl.id',
    'architecture_id_seq': 'architecture.id',
    'archive_id_seq': 'archive.id',
    'bin_associations_id_seq': 'bin_associations.id',
    'binaries_id_seq': 'binaries.id',
    'build_queue_id_seq': 'build_queue.id',
    'changelogs_text_id_seq': 'changelogs_text.id',
    'changes_id_seq': 'changes.id',
    'component_id_seq': 'component.id',
    'component_ordering_seq': 'component.ordering',
    'config_id_seq': 'config.id',
    'dsc_files_id_seq': 'dsc_files.id',
    'files_id_seq': 'files.id',
    'fingerprint_id_seq': 'fingerprint.id',
    'keyrings_id_seq': 'keyrings.id',
    'maintainer_id_seq': 'maintainer.id',
    'metadata_keys_key_id_seq': 'metadata_keys.key_id',
    'new_comments_id_seq': 'new_comments.id',
    'override_type_id_seq': 'override_type.id',
    'policy_queue_byhand_file_id_seq': 'policy_queue_byhand_file.id',
    'policy_queue_id_seq': 'policy_queue.id',
    'policy_queue_upload_id_seq': 'policy_queue_upload.id',
    'priority_id_seq': 'priority.id',
    'section_id_seq': 'section.id',
    'source_id_seq': 'source.id',
    'src_associations_id_seq': 'src_associations.id',
    'src_format_id_seq': 'src_format.id',
    'src_uploaders_id_seq': 'src_uploaders.id',
    'suite_id_seq': 'suite.id',
    'uid_id_seq': 'uid.id',
}

################################################################################


def do_update(self):
    print(__doc__)
    try:
        cnf = Config()

        c = self.db.cursor()

        for i in sequences.items():
            c.execute("ALTER SEQUENCE {0} OWNED BY {1}".format(*i))

        c.execute("UPDATE config SET value = '118' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 118, rollback issued. Error message: {0}'.format(msg))
