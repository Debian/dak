#!/usr/bin/env python
# coding=utf8

"""
Add world.suite_summary view.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2013, Ansgar Burchardt <ansgar@debian.org>
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

statements = [
"""
CREATE OR REPLACE VIEW world.suite_summary AS
    SELECT
        s.source,
        s.version,
        uploader_fpr.fingerprint,
        suite.suite_name AS distribution,
        s.created AS date,
        changed_by.name AS changed,
        uploader.name AS uploaded
    FROM source s
        JOIN src_associations sa ON s.id = sa.source
        JOIN suite ON sa.suite = suite.id
        JOIN maintainer changed_by ON s.changedby = changed_by.id
        LEFT JOIN fingerprint uploader_fpr ON s.sig_fpr = uploader_fpr.id
        LEFT JOIN uid uploader ON uploader_fpr.uid = uploader.id
""",
]

################################################################################
def do_update(self):
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("UPDATE config SET value = '96' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 96, rollback issued. Error message: {0}'.format(msg))
