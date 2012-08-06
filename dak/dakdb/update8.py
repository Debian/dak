#!/usr/bin/env python
# coding=utf8

"""
More suite config into the DB

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
    print "Moving some more of the suite config into the DB"
    Cnf = get_conf()

    try:
        c = self.db.cursor()

        c.execute("ALTER TABLE suite ADD COLUMN copychanges TEXT;")
        query = "UPDATE suite SET copychanges = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            copychanges = Cnf.find("Suite::%s::CopyChanges" % (suite))
            print "[CopyChanges] Processing suite %s" % (suite)
            if not copychanges:
                continue
            suite = suite.lower()
            c.execute(query, [copychanges, suite])

        c.execute("ALTER TABLE suite ADD COLUMN copydotdak TEXT;")
        query = "UPDATE suite SET copydotdak = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            copydotdak = Cnf.find("Suite::%s::CopyDotDak" % (suite))
            print "[CopyDotDak] Processing suite %s" % (suite)
            if not copydotdak:
                continue
            suite = suite.lower()
            c.execute(query, [copydotdak, suite])

        c.execute("ALTER TABLE suite ADD COLUMN commentsdir TEXT;")
        query = "UPDATE suite SET commentsdir = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            commentsdir = Cnf.find("Suite::%s::CommentsDir" % (suite))
            print "[CommentsDir] Processing suite %s" % (suite)
            if not commentsdir:
                continue
            suite = suite.lower()
            c.execute(query, [commentsdir, suite])

        c.execute("ALTER TABLE suite ADD COLUMN overridesuite TEXT;")
        query = "UPDATE suite SET overridesuite = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            overridesuite = Cnf.find("Suite::%s::OverrideSuite" % (suite))
            print "[OverrideSuite] Processing suite %s" % (suite)
            if not overridesuite:
                continue
            suite = suite.lower()
            c.execute(query, [overridesuite, suite])

        c.execute("ALTER TABLE suite ADD COLUMN changelogbase TEXT;")
        query = "UPDATE suite SET changelogbase = %s WHERE suite_name = %s"  #: Update query
        for suite in Cnf.subtree("Suite").list():
            changelogbase = Cnf.find("Suite::%s::ChangeLogBase" % (suite))
            print "[ChangeLogBase] Processing suite %s" % (suite)
            if not changelogbase:
                continue
            suite = suite.lower()
            c.execute(query, [changelogbase, suite])

        c.execute("UPDATE config SET value = '8' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply suite config updates, rollback issued. Error message : %s" % (str(msg)))
