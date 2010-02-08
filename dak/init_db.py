#!/usr/bin/env python

"""Sync dak.conf configuartion file and the SQL database"""
# Copyright (C) 2000, 2001, 2002, 2003, 2006  James Troup <james@nocrew.org>

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

import sys
import apt_pkg

from daklib import utils
from daklib.dbconn import *
from daklib.config import Config

################################################################################

def usage(exit_code=0):
    """Print a usage message and exit with 'exit_code'."""

    print """Usage: dak init-db
Initalizes some tables in the projectB database based on the config file.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

class InitDB(object):
    def __init__(self, Cnf, projectB):
        self.Cnf = Cnf
        self.projectB = projectB

    def do_archive(self):
        """initalize the archive table."""

        # Remove existing archives
        s = self.projectB.session()
        s.query(Archive).delete()

        for name in self.Cnf.SubTree("Archive").List():
            a = Archive()
            a.archive_name  = name
            a.origin_server = self.Cnf.get("Archive::%s::OriginServer" % name, "")
            a.description   = self.Cnf.get("Archive::%s::Description" % name,  "")
            s.add(a)

        s.commit()

    def do_architecture(self):
        """Initalize the architecture table."""

        # Remove existing architectures
        s = self.projectB.session()
        s.query(Architecture).delete()

        for arch in self.Cnf.SubTree("Architectures").List():
            a = Architecture()
            a.arch_string  = arch
            a.description  = self.Cnf.get("Architecture::%s" % arch, "")
            s.add(a)

        s.commit()

    def do_component(self):
        """Initalize the component table."""

        # Remove existing components
        s = self.projectB.session()
        s.query(Component).delete()

        for name in self.Cnf.SubTree("Component").List():
            c = Component()
            c.component_name = name
            c.description = self.Cnf.get("Component::%s::Description" % name, "")
            c.meets_dfsg  = False
            if self.Cnf.get("Component::%s::MeetsDFSG" % name, "false").lower() == 'true':
                c.meets_dfsg = True
            s.add(c)

        s.commit()

    def do_location(self):
        """Initalize the location table."""

        # Remove existing locations
        s = self.projectB.session()
        s.query(Location).delete()

        for location in self.Cnf.SubTree("Location").List():
            archive_name = self.Cnf.get("Location::%s::Archive" % location, "")
            a = s.query(Archive).filter_by(archive_name=archive_name)
            if a.count() < 1:
                utils.fubar("E: Archive '%s' for location '%s' not found" % (archive_name, location))
            archive_id = a.one().archive_id

            location_type = self.Cnf.get("Location::%s::Type" % location, "")
            if location_type != 'pool':
                utils.fubar("E: type %s not recognised for location %s" % (location_type, location))

            for component in self.Cnf.SubTree("Component").List():
                c = s.query(Component).filter_by(component_name=component)
                if c.count() < 1:
                    utils.fubar("E: Can't find component %s for location %s" % (component, location))
                component_id = c.one().component_id

                l = Location()
                l.path = location
                l.archive_id = archive_id
                l.component_id = component_id
                l.archive_type = location_type
                s.add(l)

        s.commit()

    def do_suite(self):
        """Initialize the suite table."""

        s = self.projectB.session()
        s.query(Suite).delete()

        for suite in self.Cnf.SubTree("Suite").List():
            suite = suite.lower()
            su = Suite()
            su.suite_name  = suite
            su.version     = self.Cnf.get("Suite::%s::Version" % suite, "-")
            su.origin      = self.Cnf.get("Suite::%s::Origin" % suite, "")
            su.description = self.Cnf.get("Suite::%s::Description" % suite, "")
            s.add(su)

            for architecture in self.Cnf.ValueList("Suite::%s::Architectures" % (suite)):
                sa = SuiteArchitecture()
                a = s.query(Architecture).filter_by(arch_string=architecture)
                if a.count() < 1:
                    utils.fubar("E: Architecture %s not found for suite %s" % (architecture, suite))
                sa.arch_id = a.one().arch_id
                sa.suite_id = su.suite_id
                s.add(sa)

        s.commit()

    def do_override_type(self):
        """Initalize the override_type table."""

        s = self.projectB.session()
        s.query(OverrideType).delete()

        for override_type in self.Cnf.ValueList("OverrideType"):
            ot = OverrideType()
            ot.overridetype = override_type
            s.add(ot)

        s.commit()

    def do_priority(self):
        """Initialize the priority table."""

        s = self.projectB.session()
        s.query(Priority).delete()

        for priority in self.Cnf.SubTree("Priority").List():
            p = Priority()
            p.priority = priority
            p.level    = self.Cnf.get("Priority::%s", "0")
            s.add(p)

        s.commit()

    def do_section(self):
        """Initalize the section table."""

        s = self.projectB.session()
        s.query(Section).delete()

        for component in self.Cnf.SubTree("Component").List():
            if self.Cnf["Control-Overrides::ComponentPosition"] == "prefix":
                suffix = ""
                if component != "main":
                    prefix = component + '/'
                else:
                    prefix = ""
            else:
                prefix = ""
                if component != "main":
                    suffix = '/' + component
                else:
                    suffix = ""

            for section in self.Cnf.ValueList("Section"):
                sec = Section()
                sec.section = prefix + section + suffix
                s.add(sec)

        s.commit()

    def do_all(self):
        self.do_archive()
        self.do_architecture()
        self.do_component()
        self.do_location()
        self.do_suite()
        self.do_override_type()
        self.do_priority()
        self.do_section()

################################################################################

def main ():
    """Sync dak.conf configuartion file and the SQL database"""

    Cnf = utils.get_conf()
    arguments = [('h', "help", "Init-DB::Options::Help")]
    for i in [ "help" ]:
        if not Cnf.has_key("Init-DB::Options::%s" % (i)):
            Cnf["Init-DB::Options::%s" % (i)] = ""

    arguments = apt_pkg.ParseCommandLine(Cnf, arguments, sys.argv)

    options = Cnf.SubTree("Init-DB::Options")
    if options["Help"]:
        usage()
    elif arguments:
        utils.warn("dak init-db takes no arguments.")
        usage(exit_code=1)

    # Just let connection failures be reported to the user
    projectB = DBConn()
    Cnf = Config()

    InitDB(Cnf, projectB).do_all()

################################################################################

if __name__ == '__main__':
    main()
