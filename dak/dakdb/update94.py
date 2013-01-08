#!/usr/bin/env python
# coding=utf8

"""
src_associations_full view

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
CREATE OR REPLACE VIEW src_associations_full AS
SELECT
  suite,
  source,
  BOOL_AND(extra_source) AS extra_source
FROM
  (SELECT sa.suite AS suite, sa.source AS source, FALSE AS extra_source
     FROM src_associations sa
   UNION
   SELECT ba.suite AS suite, esr.src_id AS source_id, TRUE AS extra_source
     FROM extra_src_references esr
     JOIN bin_associations ba ON esr.bin_id = ba.bin)
  AS tmp
GROUP BY suite, source
""",
"""
COMMENT ON VIEW src_associations_full IS
  'view including all source packages for a suite, including those referenced by Built-Using'
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

        c.execute("UPDATE config SET value = '94' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 94, rollback issued. Error message: {0}'.format(msg))
