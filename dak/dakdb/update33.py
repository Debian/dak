#!/usr/bin/env python
# coding=utf8

"""
Implement changelogs related tables

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2010 Luca Falavigna <dktrkranz@debian.org>
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


################################################################################

import psycopg2
from daklib.dak_exceptions import DBUpdateError

################################################################################
def do_update(self):
    """
    Implement changelogs table
    """
    print __doc__
    try:
        c = self.db.cursor()
        c.execute('ALTER TABLE changes ADD COLUMN changelog_id integer')
        c.execute('CREATE TABLE changelogs_text (id serial PRIMARY KEY NOT NULL, changelog text)')
        c.execute("GRANT SELECT ON changelogs_text TO public")
        c.execute("GRANT ALL ON changelogs_text TO ftpmaster")
        c.execute('CREATE VIEW changelogs AS SELECT cl.id, source, CAST(version AS debversion), architecture, changelog \
                   FROM changes c JOIN changelogs_text cl ON cl.id = c.changelog_id')
        c.execute("GRANT SELECT ON changelogs TO public")
        c.execute("GRANT ALL ON changelogs TO ftpmaster")
        c.execute("UPDATE config SET value = '33' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply build_queue update 33, rollback issued. Error message : %s' % (str(msg)))
