#!/usr/bin/env python
# coding=utf8

"""
Add suite options for overrides and control-suite to DB

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
from daklib.config import Config

################################################################################
def do_update(self):
    """
    Add suite options for overrides and control-suite to DB
    """
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        c.execute("ALTER TABLE suite ADD COLUMN overrideprocess BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("COMMENT ON COLUMN suite.overrideprocess IS %s", ['If true, check-overrides will process the suite by default'])
        c.execute("ALTER TABLE suite ADD COLUMN overrideorigin TEXT DEFAULT NULL")
        c.execute("COMMENT ON COLUMN suite.overrideprocess IS %s", ['If NOT NULL, check-overrides will take missing overrides from the named suite'])

        # Migrate config file values into database
        if cnf.has_key("Check-Overrides::OverrideSuites"):
            for suitename in cnf.subtree("Check-Overrides::OverrideSuites").list():
                if cnf.get("Check-Overrides::OverrideSuites::%s::Process" % suitename, "0") == "1":
                    print "Marking %s to have overrides processed automatically" % suitename.lower()
                    c.execute("UPDATE suite SET overrideprocess = TRUE WHERE suite_name = %s", [suitename.lower()])

                originsuite = cnf.get("Check-Overrides::OverrideSuites::%s::OriginSuite" % suitename, '')
                if originsuite != '':
                    print "Setting %s to use %s as origin for overrides" % (suitename.lower(), originsuite.lower())
                    c.execute("UPDATE suite SET overrideorigin = %s WHERE suite_name = %s", [originsuite.lower(), suitename.lower()])

        c.execute("ALTER TABLE suite ADD COLUMN allowcsset BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("COMMENT ON COLUMN suite.allowcsset IS %s", ['Allow control-suite to be used with the --set option without forcing'])

        # Import historical hard-coded values
        c.execute("UPDATE suite SET allowcsset = TRUE WHERE suite_name IN ('testing', 'squeeze-updates')")

        c.execute("UPDATE config SET value = '70' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 70, rollback issued. Error message : %s' % (str(msg)))
