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

import pg, sys
import apt_pkg
from daklib import database
from daklib import utils

################################################################################

Cnf = None
projectB = None

################################################################################

def usage(exit_code=0):
    """Print a usage message and exit with 'exit_code'."""

    print """Usage: dak init-db
Initalizes some tables in the projectB database based on the config file.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def sql_get (config, key):
    """Return the value of config[key] in quotes or NULL if it doesn't exist."""

    if config.has_key(key):
        return "'%s'" % (config[key])
    else:
        return "NULL"

################################################################################

def do_archive():
    """Initalize the archive table."""

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM archive")
    for name in Cnf.SubTree("Archive").List():
        archive_config = Cnf.SubTree("Archive::%s" % (name))
        origin_server = sql_get(archive_config, "OriginServer")
        description = sql_get(archive_config, "Description")
        projectB.query("INSERT INTO archive (name, origin_server, description) "
                       "VALUES ('%s', %s, %s)"
                       % (name, origin_server, description))
    projectB.query("COMMIT WORK")

def do_architecture():
    """Initalize the architecture table."""

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM architecture")
    for arch in Cnf.SubTree("Architectures").List():
        description = Cnf["Architectures::%s" % (arch)]
        projectB.query("INSERT INTO architecture (arch_string, description) "
                       "VALUES ('%s', '%s')" % (arch, description))
    projectB.query("COMMIT WORK")

def do_component():
    """Initalize the component table."""

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM component")
    for name in Cnf.SubTree("Component").List():
        component_config = Cnf.SubTree("Component::%s" % (name))
        description = sql_get(component_config, "Description")
        if component_config.get("MeetsDFSG").lower() == "true":
            meets_dfsg = "true"
        else:
            meets_dfsg = "false"
        projectB.query("INSERT INTO component (name, description, meets_dfsg) "
                       "VALUES ('%s', %s, %s)"
                       % (name, description, meets_dfsg))
    projectB.query("COMMIT WORK")

def do_location():
    """Initalize the location table."""

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM location")
    for location in Cnf.SubTree("Location").List():
        location_config = Cnf.SubTree("Location::%s" % (location))
        archive_id = database.get_archive_id(location_config["Archive"])
        if archive_id == -1:
            utils.fubar("Archive '%s' for location '%s' not found."
                               % (location_config["Archive"], location))
        location_type = location_config.get("type")
        if location_type == "legacy-mixed":
            projectB.query("INSERT INTO location (path, archive, type) VALUES "
                           "('%s', %d, '%s')"
                           % (location, archive_id, location_config["type"]))
        elif location_type == "legacy" or location_type == "pool":
            for component in Cnf.SubTree("Component").List():
                component_id = database.get_component_id(component)
                projectB.query("INSERT INTO location (path, component, "
                               "archive, type) VALUES ('%s', %d, %d, '%s')"
                               % (location, component_id, archive_id,
                                  location_type))
        else:
            utils.fubar("E: type '%s' not recognised in location %s."
                               % (location_type, location))
    projectB.query("COMMIT WORK")

def do_suite():
    """Initalize the suite table."""

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM suite")
    for suite in Cnf.SubTree("Suite").List():
        suite_config = Cnf.SubTree("Suite::%s" %(suite))
        version = sql_get(suite_config, "Version")
        origin = sql_get(suite_config, "Origin")
        description = sql_get(suite_config, "Description")
        projectB.query("INSERT INTO suite (suite_name, version, origin, "
                       "description) VALUES ('%s', %s, %s, %s)"
                       % (suite.lower(), version, origin, description))
        for architecture in get_suite_architectures(suite):
            architecture_id = database.get_architecture_id (architecture)
            if architecture_id < 0:
                utils.fubar("architecture '%s' not found in architecture"
                                   " table for suite %s."
                                   % (architecture, suite))
            projectB.query("INSERT INTO suite_architectures (suite, "
                           "architecture) VALUES (currval('suite_id_seq'), %d)"
                           % (architecture_id))
    projectB.query("COMMIT WORK")

def do_override_type():
    """Initalize the override_type table."""

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM override_type")
    for override_type in Cnf.ValueList("OverrideType"):
        projectB.query("INSERT INTO override_type (type) VALUES ('%s')"
                       % (override_type))
    projectB.query("COMMIT WORK")

def do_priority():
    """Initialize the priority table."""

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM priority")
    for priority in Cnf.SubTree("Priority").List():
        projectB.query("INSERT INTO priority (priority, level) VALUES "
                       "('%s', %s)"
                       % (priority, Cnf["Priority::%s" % (priority)]))
    projectB.query("COMMIT WORK")

def do_section():
    """Initalize the section table."""
    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM section")
    for component in Cnf.SubTree("Component").List():
        if Cnf["Control-Overrides::ComponentPosition"] == "prefix":
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
        for section in Cnf.ValueList("Section"):
            projectB.query("INSERT INTO section (section) VALUES "
                           "('%s%s%s')" % (prefix, section, suffix))
    projectB.query("COMMIT WORK")

################################################################################

def main ():
    """Sync dak.conf configuartion file and the SQL database"""

    global Cnf, projectB

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

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"],
                          int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    do_archive()
    do_architecture()
    do_component()
    do_location()
    do_suite()
    do_override_type()
    do_priority()
    do_section()

################################################################################

if __name__ == '__main__':
    main()
