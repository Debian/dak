#!/usr/bin/env python

# Sync the ISC configuartion file and the SQL database
# Copyright (C) 2000, 2001, 2002, 2003  James Troup <james@nocrew.org>
# $Id: alyson,v 1.12 2003-09-07 13:52:07 troup Exp $

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
import utils, db_access
import apt_pkg

################################################################################

Cnf = None
projectB = None

################################################################################

def usage(exit_code=0):
    print """Usage: alyson
Initalizes some tables in the projectB database based on the config file.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def get (c, i):
    if c.has_key(i):
        return "'%s'" % (c[i])
    else:
        return "NULL"

def main ():
    global Cnf, projectB

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Alyson::Options::Help")]
    for i in [ "help" ]:
	if not Cnf.has_key("Alyson::Options::%s" % (i)):
	    Cnf["Alyson::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Alyson::Options")
    if Options["Help"]:
	usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    db_access.init(Cnf, projectB)

    # archive

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM archive")
    for name in Cnf.SubTree("Archive").List():
        Archive = Cnf.SubTree("Archive::%s" % (name))
        origin_server = get(Archive, "OriginServer")
        description = get(Archive, "Description")
        projectB.query("INSERT INTO archive (name, origin_server, description) VALUES ('%s', %s, %s)" % (name, origin_server, description))
    projectB.query("COMMIT WORK")

    # architecture

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM architecture")
    for arch in Cnf.SubTree("Architectures").List():
        description = Cnf["Architectures::%s" % (arch)]
        projectB.query("INSERT INTO architecture (arch_string, description) VALUES ('%s', '%s')" % (arch, description))
    projectB.query("COMMIT WORK")

    # component

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM component")
    for name in Cnf.SubTree("Component").List():
        Component = Cnf.SubTree("Component::%s" % (name))
        description = get(Component, "Description")
        if Component.get("MeetsDFSG").lower() == "true":
            meets_dfsg = "true"
        else:
            meets_dfsg = "false"
        projectB.query("INSERT INTO component (name, description, meets_dfsg) VALUES ('%s', %s, %s)" % (name, description, meets_dfsg))
    projectB.query("COMMIT WORK")

    # location

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM location")
    for location in Cnf.SubTree("Location").List():
        Location = Cnf.SubTree("Location::%s" % (location))
        archive_id = db_access.get_archive_id(Location["Archive"])
        type = Location.get("type")
        if type == "legacy-mixed":
            projectB.query("INSERT INTO location (path, archive, type) VALUES ('%s', %d, '%s')" % (location, archive_id, Location["type"]))
        elif type == "legacy" or type == "pool":
            for component in Cnf.SubTree("Component").List():
                component_id = db_access.get_component_id(component)
                projectB.query("INSERT INTO location (path, component, archive, type) VALUES ('%s', %d, %d, '%s')" %
                               (location, component_id, archive_id, type))
        else:
            utils.fubar("E: type '%s' not recognised in location %s." % (type, location))
    projectB.query("COMMIT WORK")

    # suite

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM suite")
    for suite in Cnf.SubTree("Suite").List():
        Suite = Cnf.SubTree("Suite::%s" %(suite))
        version = get(Suite, "Version")
        origin = get(Suite, "Origin")
        description = get(Suite, "Description")
        projectB.query("INSERT INTO suite (suite_name, version, origin, description) VALUES ('%s', %s, %s, %s)"
                       % (suite.lower(), version, origin, description))
        for architecture in Cnf.ValueList("Suite::%s::Architectures" % (suite)):
            architecture_id = db_access.get_architecture_id (architecture)
            if architecture_id < 0:
                utils.fubar("architecture '%s' not found in architecture table for suite %s." % (architecture, suite))
            projectB.query("INSERT INTO suite_architectures (suite, architecture) VALUES (currval('suite_id_seq'), %d)" % (architecture_id))
    projectB.query("COMMIT WORK")

    # override_type

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM override_type")
    for type in Cnf.ValueList("OverrideType"):
        projectB.query("INSERT INTO override_type (type) VALUES ('%s')" % (type))
    projectB.query("COMMIT WORK")

    # priority

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM priority")
    for priority in Cnf.SubTree("Priority").List():
        projectB.query("INSERT INTO priority (priority, level) VALUES ('%s', %s)" % (priority, Cnf["Priority::%s" % (priority)]))
    projectB.query("COMMIT WORK")

    # section

    projectB.query("BEGIN WORK")
    projectB.query("DELETE FROM section")
    for component in Cnf.SubTree("Component").List():
        if Cnf["Natalie::ComponentPosition"] == "prefix":
            suffix = ""
            if component != "main":
                prefix = component + '/'
            else:
                prefix = ""
        else:
            prefix = ""
            component = component.replace("non-US/", "")
            if component != "main":
                suffix = '/' + component
            else:
                suffix = ""
        for section in Cnf.ValueList("Section"):
            projectB.query("INSERT INTO section (section) VALUES ('%s%s%s')" % (prefix, section, suffix))
    projectB.query("COMMIT WORK")

################################################################################

if __name__ == '__main__':
    main()

