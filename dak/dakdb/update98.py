#!/usr/bin/env python
# coding=utf8

"""
Remove obsolete functions

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2013, Ansgar Burchardt <ansgar@debian.org>
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
    'DROP FUNCTION IF EXISTS bin_associations_id_max()',
    'DROP FUNCTION IF EXISTS binaries_id_max()',
    'DROP FUNCTION IF EXISTS dsc_files_id_max()',
    'DROP FUNCTION IF EXISTS files_id_max()',
    'DROP FUNCTION IF EXISTS override_type_id_max()',
    'DROP FUNCTION IF EXISTS priority_id_max()',
    'DROP FUNCTION IF EXISTS section_id_max()',
    'DROP FUNCTION IF EXISTS source_id_max()',
    'DROP AGGREGATE IF EXISTS space_separated_list(TEXT)',
    'DROP FUNCTION IF EXISTS space_concat(TEXT, TEXT)',
    'DROP FUNCTION IF EXISTS src_associations_id_max()',
]

################################################################################
def do_update(self):
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("UPDATE config SET value = '98' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 98, rollback issued. Error message: {0}'.format(msg))
