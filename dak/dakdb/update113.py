# coding=utf8

"""
Add accept_{source,binary}_uploads to suite

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2016, Ansgar Burchardt <ansgar@debian.org>
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
ALTER TABLE suite
  ADD COLUMN accept_source_uploads BOOLEAN DEFAULT TRUE,
  ADD COLUMN accept_binary_uploads BOOLEAN DEFAULT TRUE
""",
"""
UPDATE suite
   SET accept_source_uploads = FALSE, accept_binary_uploads = FALSE
 WHERE id IN (SELECT suite_id FROM policy_queue)
    OR id IN (SELECT suite_id FROM build_queue)
    OR id IN (SELECT debugsuite_id FROM suite)
"""
]

################################################################################


def do_update(self):
    print(__doc__)
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("UPDATE config SET value = '113' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 113, rollback issued. Error message: {0}'.format(msg))
