#!/usr/bin/env python
# coding=utf8

"""
Rename squeeze-volatile to squeeze-updates to get more confused users

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2010 Joerg Jaspert <joerg@debian.org>
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
    Rename squeeze-volatile to squeeze-updates to get more confused users
    """
    print __doc__
    try:
        c = self.db.cursor()
        if gethostname() == 'franck':
            c.execute("UPDATE suite SET suite_name='squeeze-updates', description='Updated packages for Debian x.y', codename='squeeze-updates' WHERE suite_name='squeeze-volatile'")
            c.execute("UPDATE build_queue SET queue_name='buildd-squeeze-updates', path='/srv/incoming.debian.org/dists/squeeze-updates/buildd', releasedescription='buildd squeeze updates incoming' WHERE queue_name='buildd-squeeze-volatile'")
            c.execute("UPDATE policy_queue SET queue_name='squeeze-updates-proposed-updates', path='/srv/ftp-master.debian.org/queue/updates/squeeze-updates-p-u-new' WHERE queue_name='squeeze-volatile-proposed-updates'")
        c.execute("UPDATE config SET value = '40' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 40, rollback issued. Error message : %s' % (str(msg)))
