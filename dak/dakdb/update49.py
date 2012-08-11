#!/usr/bin/env python
# coding=utf8

"""
Permission fixups

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
from socket import gethostname;

################################################################################
def do_update(self):
    """
    Fix up permissions
    """
    print __doc__
    try:
        c = self.db.cursor()

        c.execute("GRANT SELECT, UPDATE, INSERT ON binaries_metadata TO ftpmaster")
        c.execute("GRANT SELECT ON binaries_metadata TO public")
        c.execute("GRANT USAGE ON metadata_keys_key_id_seq TO ftpmaster")
        c.execute("GRANT SELECT, UPDATE, INSERT ON source_metadata TO ftpmaster")
        c.execute("GRANT SELECT ON source_metadata TO public")
        c.execute("GRANT SELECT, UPDATE, INSERT ON metadata_keys TO ftpmaster")
        c.execute("GRANT SELECT ON metadata_keys TO public")
        c.execute("GRANT SELECT, UPDATE, INSERT ON extra_src_references TO ftpmaster")
        c.execute("GRANT SELECT ON extra_src_references TO public")
        c.execute("GRANT SELECT, UPDATE, INSERT ON src_contents TO ftpmaster")
        c.execute("GRANT SELECT ON src_contents TO public")
        c.execute("GRANT USAGE ON changelogs_text_id_seq TO ftpmaster")
        c.execute("GRANT SELECT ON changes_pending_files_map TO public")
        c.execute("GRANT SELECT ON config TO public")

        c.execute("UPDATE config SET value = '49' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 49, rollback issued. Error message : %s' % (str(msg)))
