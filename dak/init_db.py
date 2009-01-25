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

import psycopg2, sys
import apt_pkg

from daklib import utils
from daklib.DBConn import DBConn
from daklib.Config import Config

################################################################################

def usage(exit_code=0):
    """Print a usage message and exit with 'exit_code'."""

    print """Usage: dak init-db
Initalizes some tables in the projectB database based on the config file.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def sql_get (config, key):
    """Return the value of config[key] or None if it doesn't exist."""

    try:
        return config[key]
    except KeyError:
        return None

################################################################################

class InitDB(object):
    def __init__(self, Cnf, projectB):
        self.Cnf = Cnf
        self.projectB = projectB

    def do_archive(self):
        """Initalize the archive table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM archive")
        archive_add = "INSERT INTO archive (name, origin_server, description) VALUES (%s, %s, %s)"
        for name in self.Cnf.SubTree("Archive").List():
            archive_config = self.Cnf.SubTree("Archive::%s" % (name))
            origin_server = sql_get(archive_config, "OriginServer")
            description = sql_get(archive_config, "Description")
            c.execute(archive_add, [name, origin_server, description])
        self.projectB.commit()

    def do_architecture(self):
        """Initalize the architecture table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM architecture")
        arch_add = "INSERT INTO architecture (arch_string, description) VALUES (%s, %s)"
        for arch in self.Cnf.SubTree("Architectures").List():
            description = self.Cnf["Architectures::%s" % (arch)]
            c.execute(arch_add, [arch, description])
        self.projectB.commit()

    def do_component(self):
        """Initalize the component table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM component")

        comp_add = "INSERT INTO component (name, description, meets_dfsg) " + \
                   "VALUES (%s, %s, %s)"

        for name in self.Cnf.SubTree("Component").List():
            component_config = self.Cnf.SubTree("Component::%s" % (name))
            description = sql_get(component_config, "Description")
            meets_dfsg = (component_config.get("MeetsDFSG").lower() == "true")
            c.execute(comp_add, [name, description, meets_dfsg])

        self.projectB.commit()

    def do_location(self):
        """Initalize the location table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM location")

        loc_add_mixed = "INSERT INTO location (path, archive, type) " + \
                        "VALUES (%s, %s, %s)"

        loc_add = "INSERT INTO location (path, component, archive, type) " + \
                  "VALUES (%s, %s, %s, %s)"

        for location in self.Cnf.SubTree("Location").List():
            location_config = self.Cnf.SubTree("Location::%s" % (location))
            archive_id = self.projectB.get_archive_id(location_config["Archive"])
            if archive_id == -1:
                utils.fubar("Archive '%s' for location '%s' not found."
                                   % (location_config["Archive"], location))
            location_type = location_config.get("type")
            if location_type == "legacy-mixed":
                c.execute(loc_add_mixed, [location, archive_id, location_config["type"]])
            elif location_type == "legacy" or location_type == "pool":
                for component in self.Cnf.SubTree("Component").List():
                    component_id = self.projectB.get_component_id(component)
                    c.execute(loc_add, [location, component_id, archive_id, location_type])
            else:
                utils.fubar("E: type '%s' not recognised in location %s."
                                   % (location_type, location))

        self.projectB.commit()

    def do_suite(self):
        """Initalize the suite table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM suite")

        suite_add = "INSERT INTO suite (suite_name, version, origin, description) " + \
                    "VALUES (%s, %s, %s, %s)"

        sa_add = "INSERT INTO suite_architectures (suite, architecture) " + \
                 "VALUES (currval('suite_id_seq'), %s)"

        for suite in self.Cnf.SubTree("Suite").List():
            suite_config = self.Cnf.SubTree("Suite::%s" %(suite))
            version = sql_get(suite_config, "Version")
            origin = sql_get(suite_config, "Origin")
            description = sql_get(suite_config, "Description")
            c.execute(suite_add, [suite.lower(), version, origin, description])
            for architecture in self.Cnf.ValueList("Suite::%s::Architectures" % (suite)):
                architecture_id = self.projectB.get_architecture_id (architecture)
                if architecture_id < 0:
                    utils.fubar("architecture '%s' not found in architecture"
                                       " table for suite %s."
                                   % (architecture, suite))
                c.execute(sa_add, [architecture_id])

        self.projectB.commit()

    def do_override_type(self):
        """Initalize the override_type table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM override_type")

        over_add = "INSERT INTO override_type (type) VALUES (%s)"

        for override_type in self.Cnf.ValueList("OverrideType"):
            c.execute(over_add, [override_type])

        self.projectB.commit()

    def do_priority(self):
        """Initialize the priority table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM priority")

        prio_add = "INSERT INTO priority (priority, level) VALUES (%s, %s)"

        for priority in self.Cnf.SubTree("Priority").List():
            c.execute(prio_add, [priority, self.Cnf["Priority::%s" % (priority)]])

        self.projectB.commit()

    def do_section(self):
        """Initalize the section table."""

        c = self.projectB.cursor()
        c.execute("DELETE FROM section")

        sect_add = "INSERT INTO section (section) VALUES (%s)"

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
                c.execute(sect_add, [prefix + section + suffix])

        self.projectB.commit()

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
