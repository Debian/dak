#!/usr/bin/env python
# coding=utf8

"""
Add tables for extra_src handling

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

################################################################################
def do_update(self):
    """
    Add tables for extra_src handling
    """
    print __doc__
    try:
        c = self.db.cursor()

        c.execute("""
CREATE TABLE extra_src_references (
    bin_id      INT4 NOT NULL REFERENCES binaries(id) ON DELETE CASCADE,
    src_id      INT4 NOT NULL REFERENCES source(id) ON DELETE RESTRICT,

    PRIMARY KEY (bin_id, src_id)
)""")

        c.execute("UPDATE config SET value = '45' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply update 45, rollback issued. Error message : %s' % (str(msg)))
