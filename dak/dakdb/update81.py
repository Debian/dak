#!/usr/bin/env python
# coding=utf8

"""
Correct permissions of policy_queue_byhand_file_id_seq

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2012 Luca Falavigna <dktrkranz@debian.org>
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

################################################################################
def do_update(self):
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()
        c.execute("GRANT SELECT, UPDATE, USAGE ON policy_queue_byhand_file_id_seq TO ftpmaster")
        c.execute("GRANT SELECT ON policy_queue_byhand_file_id_seq TO public")
        c.execute("UPDATE config SET value = '81' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 81, rollback issued. Error message: {0}'.format(msg))
