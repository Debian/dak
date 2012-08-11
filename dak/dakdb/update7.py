#!/usr/bin/env python
# coding=utf8

"""
Moving suite config into DB

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008  Michael Casadevall <mcasadevall@debian.org>
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
    print "Moving some of the suite config into the DB"
    Cnf = get_conf()

    try:
        c = self.db.cursor()

        c.execute("ALTER TABLE suite ADD COLUMN untouchable BOOLEAN NOT NULL DEFAULT FALSE;")
        query = "UPDATE suite SET untouchable = TRUE WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            untouchable = Cnf.find("Suite::%s::Untouchable" % (suite))
            if not untouchable:
                continue
            print "[Untouchable] Processing suite %s" % (suite)
            suite = suite.lower()
            c.execute(query, [suite])


        c.execute("ALTER TABLE suite ADD COLUMN announce text NOT NULL DEFAULT 'debian-devel-changes@lists.debian.org';")
        query = "UPDATE suite SET announce = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            announce_list = Cnf.find("Suite::%s::Announce" % (suite))
            print "[Announce] Processing suite %s" % (suite)
            suite = suite.lower()
            c.execute(query, [announce_list, suite])

        c.execute("ALTER TABLE suite ADD COLUMN codename text;")
        query = "UPDATE suite SET codename = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            codename = Cnf.find("Suite::%s::CodeName" % (suite))
            print "[Codename] Processing suite %s" % (suite)
            suite = suite.lower()
            c.execute(query, [codename, suite])

        c.execute("ALTER TABLE suite ADD COLUMN overridecodename text;")
        query = "UPDATE suite SET overridecodename = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            codename = Cnf.find("Suite::%s::OverrideCodeName" % (suite))
            print "[OverrideCodeName] Processing suite %s" % (suite)
            suite = suite.lower()
            c.execute(query, [codename, suite])

        c.execute("ALTER TABLE suite ADD COLUMN validtime integer NOT NULL DEFAULT 604800;")
        query = "UPDATE suite SET validtime = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            validtime = Cnf.find("Suite::%s::ValidTime" % (suite))
            print "[ValidTime] Processing suite %s" % (suite)
            if not validtime:
                validtime = 0
            suite = suite.lower()
            c.execute(query, [validtime, suite])

        c.execute("ALTER TABLE suite ADD COLUMN priority integer NOT NULL DEFAULT 0;")
        query = "UPDATE suite SET priority = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            priority = Cnf.find("Suite::%s::Priority" % (suite))
            print "[Priority] Processing suite %s" % (suite)
            if not priority:
                priority = 0
            suite = suite.lower()
            c.execute(query, [priority, suite])


        c.execute("ALTER TABLE suite ADD COLUMN notautomatic BOOLEAN NOT NULL DEFAULT FALSE;")
        query = "UPDATE suite SET notautomatic = TRUE WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            notautomatic = Cnf.find("Suite::%s::NotAutomatic" % (suite))
            print "[NotAutomatic] Processing suite %s" % (suite)
            if not notautomatic:
                continue
            suite = suite.lower()
            c.execute(query, [suite])

        c.execute("UPDATE config SET value = '7' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to appy suite config updates, rollback issued. Error message : %s" % (str(msg)))
