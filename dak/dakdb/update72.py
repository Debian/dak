#!/usr/bin/env python
# coding=utf8

"""
Remove redundant indices

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2012 Ansgar Burchardt <ansgar@debian.org>
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
    """
    Remove redundant indices
    """
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        indices = [
            # table 'binaries':
            "binaries_id", # (id). already covered by binaries_pkey (id)
            "binaries_by_package", # (id, package). already covered by binaries_pkey (id)
            "binaries_files", # (file). already covered by binaries_file_key (file)
            "jjt5", # (id, source). already covered by binaries_pkey (id)
            # table 'changes':
            "changesin_queue_approved_for", # (in_queue, approved_for). already covered by changesin_queue (in_queue)
            # table 'files':
            "jjt",  # (id). already covered by files_pkey (id)
            "jjt3", # (id, location). already covered by files_pkey (id)
            # table 'override':
            "override_suite_key", # (suite, component, package, type). same as override_pkey
            # table 'suite':
            "suite_hash", # (suite_name). already covered by suite_name_unique (suite_name)
            # table 'suite_architectures':
            "suite_architectures_suite_key", # (suite, architecture). same as suite_architectures_pkey
        ]
        for index in indices:
            c.execute("DROP INDEX IF EXISTS {0}".format(index))

        c.execute("UPDATE config SET value = '72' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 72, rollback issued. Error message : %s' % (str(msg)))
