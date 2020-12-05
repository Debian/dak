# coding=utf8

"""
Change indices for {src,bin}_contents

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2015, Ansgar Burchardt <ansgar@debian.org>
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
DROP INDEX IF EXISTS ind_bin_contents_binary
""",
"""
ALTER TABLE bin_contents
  DROP CONSTRAINT IF EXISTS bin_contents_pkey
""",
"""
CREATE UNIQUE INDEX bin_contents_pkey
  ON bin_contents (binary_id, file) WITH (fillfactor = 80)
""",
"""
ALTER TABLE bin_contents
  ADD PRIMARY KEY USING INDEX bin_contents_pkey
""",
"""
CLUSTER bin_contents USING bin_contents_pkey
""",
"""
DROP INDEX IF EXISTS src_contents_source_id_idx
""",
"""
ALTER TABLE src_contents
  DROP CONSTRAINT IF EXISTS src_contents_pkey
""",
"""
CREATE UNIQUE INDEX src_contents_pkey
  ON src_contents (source_id, file) WITH (fillfactor = 80)
""",
"""
ALTER TABLE src_contents
  ADD PRIMARY KEY USING INDEX src_contents_pkey
""",
"""
CLUSTER src_contents USING src_contents_pkey
""",
]

################################################################################


def do_update(self):
    print(__doc__)
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("UPDATE config SET value = '109' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 109, rollback issued. Error message: {0}'.format(msg))
