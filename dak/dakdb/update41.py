#!/usr/bin/env python
# coding=utf8

"""
Remove useless type casts from primary keys to support sqlalchemy's reflection
mechanism for all tables. Rename 2 sequences and add 1 primary key.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Torsten Werner <twerner@debian.org>
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
from socket import gethostname;

################################################################################
def do_update(self):
    """
    Remove useless type casts from primary keys, fix 2 sequences, and add 1
    primary key.
    """
    print __doc__
    try:
        c = self.db.cursor()

        # remove useless type casts
        for table in ('architecture', 'archive', 'bin_associations', \
            'binaries', 'component', 'dsc_files', 'files', \
            'fingerprint', 'location', 'maintainer', 'override_type', \
            'pending_bin_contents', 'priority', 'section', 'source', \
            'src_associations', 'suite', 'uid'):
            c.execute("ALTER TABLE %s ALTER id SET DEFAULT nextval('%s_id_seq'::regclass)" % \
                (table, table))

        # rename sequences
        c.execute("ALTER SEQUENCE known_changes_id_seq RENAME TO changes_id_seq")
        c.execute("ALTER SEQUENCE queue_files_id_seq RENAME TO build_queue_files_id_seq")

        # replace unique contraint by primary key
        c.execute( \
            "ALTER TABLE bin_contents DROP CONSTRAINT bin_contents_file_key");
        c.execute("ALTER TABLE bin_contents ADD PRIMARY KEY (file, binary_id)");

        c.execute("UPDATE config SET value = '41' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 41, rollback issued. Error message : %s' % (str(msg)))
