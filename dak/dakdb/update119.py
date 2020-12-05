# coding=utf8

"""remove unused database objects

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2018, Bastian Blank <waldi@debian.org>
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

views = [
    'obsolete_all_associations',
    'obsolete_any_associations',
    'obsolete_any_by_all_associations',
    'obsolete_src_associations',
    'almost_obsolete_all_associations',
    'almost_obsolete_src_associations',
    'newest_all_associations',
    'newest_any_associations',
    'any_associations_source',
    'binaries_suite_arch',
    'file_arch_suite',
    'src_associations_bin',
    'suite_arch_by_name',
]

sequences = [
    'location_id_seq',
]

################################################################################


def do_update(self):
    print(__doc__)
    try:
        cnf = Config()

        c = self.db.cursor()

        for i in views:
            c.execute("DROP VIEW {0}".format(i))

        for i in sequences:
            c.execute("DROP SEQUENCE IF EXISTS {0}".format(i))

        c.execute("UPDATE config SET value = '119' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 119, rollback issued. Error message: {0}'.format(msg))
