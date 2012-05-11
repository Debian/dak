#!/usr/bin/env python
"""
Get suite_architectures table use sane values

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
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
from daklib.utils import get_conf

################################################################################

suites = {}  #: Cache of existing suites
archs = {}   #: Cache of existing architectures

def do_update(self):
    """ Execute the DB update """

    print "Lets make suite_architecture table use sane values"
    Cnf = get_conf()

    query = "INSERT into suite_architectures (suite, architecture) VALUES (%s, %s)"  #: Update query
    try:
        c = self.db.cursor()
        c.execute("DELETE FROM suite_architectures;")

        c.execute("SELECT id, arch_string FROM architecture;")
        a=c.fetchall()
        for arch in a:
            archs[arch[1]]=arch[0]

        c.execute("SELECT id,suite_name FROM suite")
        s=c.fetchall()
        for suite in s:
            suites[suite[1]]=suite[0]

        for suite in Cnf.subtree("Suite").list():
            print "Processing suite %s" % (suite)
            architectures = Cnf.subtree("Suite::" + suite).value_list("Architectures")
            suite = suite.lower()
            for arch in architectures:
                c.execute(query, [suites[suite], archs[arch]])

        c.execute("UPDATE config SET value = '4' WHERE name = 'db_revision'")

        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply sanity to suite_architecture table, rollback issued. Error message : %s" % (str(msg)))
