#!/usr/bin/env python
# coding=utf8

"""
Fix up constraints for pg 9.0

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
from socket import gethostname;

################################################################################
def do_update(self):
    """
    Fix up constraints for pg 9.0
    """
    print __doc__
    try:
        c = self.db.cursor()

        c.execute("ALTER TABLE policy_queue DROP constraint policy_queue_perms_check")
        c.execute("ALTER TABLE policy_queue DROP constraint policy_queue_change_perms_check")
        c.execute("ALTER TABLE policy_queue ADD CONSTRAINT policy_queue_perms_check CHECK (perms SIMILAR TO '[0-7][0-7][0-7][0-7]')")
        c.execute("ALTER TABLE policy_queue ADD CONSTRAINT policy_queue_change_perms_check CHECK (change_perms SIMILAR TO '[0-7][0-7][0-7][0-7]')")

        c.execute("UPDATE config SET value = '43' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply update 43, rollback issued. Error message : %s' % (str(msg)))
