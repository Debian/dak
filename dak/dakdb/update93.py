#!/usr/bin/env python
# coding=utf8

"""
update world.files-1 view to handle backports archive on ftp-master

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2012 Ansgar Burchardt <ansgar@debian.org>
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

################################################################################
def do_update(self):
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        c.execute("""
            CREATE OR REPLACE VIEW world."files-1" AS
              SELECT
                files.id AS id,
                component.name || '/' || files.filename AS filename,
                files.size AS size,
                files.md5sum AS md5sum,
                files.sha1sum AS sha1sum,
                files.sha256sum AS sha256sum,
                files.last_used AS last_used,
                files.created AS created,
                files.modified AS modified
              FROM files
              JOIN files_archive_map fam ON files.id = fam.file_id
              JOIN component ON fam.component_id = component.id
              WHERE fam.archive_id = (SELECT id FROM archive WHERE name IN ('backports', 'ftp-master', 'security') ORDER BY id LIMIT 1)
            """)

        c.execute("UPDATE config SET value = '93' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 93, rollback issued. Error message: {0}'.format(msg))
