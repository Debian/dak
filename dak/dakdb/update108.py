# coding=utf8

"""
Add codename to package_list view

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
"""DROP VIEW IF EXISTS package_list""",
"""
CREATE OR REPLACE VIEW package_list AS
SELECT
  tmp.package,
  tmp.version,
  tmp.source,
  tmp.source_version,
  suite.suite_name AS suite,
  suite.codename AS codename,
  archive.name AS archive,
  component.name AS component,
  CASE component.name
    WHEN 'main' THEN suite.suite_name
    ELSE CONCAT(suite.suite_name, '/', component.name)
    END AS display_suite,
  tmp.architecture_is_source,
  tmp.architecture,
  tmp.type
FROM
  (SELECT
    s.source AS package,
    s.version AS version,
    s.source AS source,
    s.version AS source_version,
    sa.suite AS suite_id,
    TRUE AS architecture_is_source,
    'source' AS architecture,
    'dsc' AS type,
    sc.component_id
    FROM source s
    JOIN src_associations sa ON s.id = sa.source
    JOIN source_component sc ON s.id = sc.source_id AND sa.suite = sc.suite_id
   UNION
   SELECT
    b.package AS package,
    b.version AS version,
    s.source AS source,
    s.version AS source_version,
    ba.suite AS suite_id,
    FALSE AS architecture_is_source,
    a.arch_string AS architecture,
    b.type AS type,
    bc.component_id
    FROM binaries b
    JOIN source s ON b.source = s.id
    JOIN architecture a ON b.architecture = a.id
    JOIN bin_associations ba ON b.id = ba.bin
    JOIN binary_component bc ON b.id = bc.binary_id AND ba.suite = bc.suite_id) AS tmp
  JOIN suite ON tmp.suite_id = suite.id
  JOIN archive ON suite.archive_id = archive.id
  JOIN component ON tmp.component_id = component.id
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

        c.execute("UPDATE config SET value = '108' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 108, rollback issued. Error message: {0}'.format(msg))
