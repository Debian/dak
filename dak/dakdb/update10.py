#!/usr/bin/env python
# coding=utf8

"""
Add constraints to src_uploaders

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
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

# <mhy> oh no, Ganneff has just corrected my english

################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError
from daklib.utils import get_conf

################################################################################

def do_update(self):
    print "Add constraints to src_uploaders"
    Cnf = get_conf()

    try:
        c = self.db.cursor()
        # Deal with out-of-date src_uploaders entries
        c.execute("DELETE FROM src_uploaders WHERE source NOT IN (SELECT id FROM source)")
        c.execute("DELETE FROM src_uploaders WHERE maintainer NOT IN (SELECT id FROM maintainer)")
        # Add constraints
        c.execute("ALTER TABLE src_uploaders ADD CONSTRAINT src_uploaders_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) ON DELETE CASCADE")
        c.execute("ALTER TABLE src_uploaders ADD CONSTRAINT src_uploaders_source FOREIGN KEY (source) REFERENCES source(id) ON DELETE CASCADE")
        c.execute("UPDATE config SET value = '10' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply suite config updates, rollback issued. Error message : %s" % (str(msg)))
