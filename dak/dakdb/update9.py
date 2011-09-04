#!/usr/bin/env python
# coding=utf8

"""
Pending contents disinguished by arch

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008  Michael Casadevall <mcasadevall@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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

# * Ganneff ponders how to best write the text to -devel. (need to tell em in
#   case they find more bugs). "We fixed the fucking idiotic broken implementation
#   to be less so" is probably not the nicest, even if perfect valid, way to say so

################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError
from daklib.utils import get_conf

################################################################################

def do_update(self):
    print "pending_contents should distinguish by arch"
    Cnf = get_conf()

    try:
        c = self.db.cursor()

        c.execute("DELETE FROM pending_content_associations")
        c.execute("""ALTER TABLE pending_content_associations
                         ADD COLUMN architecture integer NOT NULL""")
        c.execute("""ALTER TABLE ONLY pending_content_associations
                         ADD CONSTRAINT pending_content_assiciations_arch
                         FOREIGN KEY (architecture)
                         REFERENCES architecture(id)
                         ON DELETE CASCADE""")
        c.execute("UPDATE config SET value = '9' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply suite config updates, rollback issued. Error message : %s" % (str(msg)))
