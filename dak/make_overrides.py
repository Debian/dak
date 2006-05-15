#!/usr/bin/env python

# Output override files for apt-ftparchive and indices/
# Copyright (C) 2000, 2001, 2002, 2004  James Troup <james@nocrew.org>
# $Id: denise,v 1.18 2005-11-15 09:50:32 ajt Exp $

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

# This is seperate because it's horribly Debian specific and I don't
# want that kind of horribleness in the otherwise generic natalie.  It
# does duplicate code tho.

################################################################################

import pg, sys
import utils, db_access
import apt_pkg

################################################################################

Cnf = None
projectB = None
override = {}

################################################################################

def usage(exit_code=0):
    print """Usage: denise
Outputs the override tables to text files.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def do_list(output_file, suite, component, otype):
    global override

    suite_id = db_access.get_suite_id(suite)
    if suite_id == -1:
        utils.fubar("Suite '%s' not recognised." % (suite))

    component_id = db_access.get_component_id(component)
    if component_id == -1:
        utils.fubar("Component '%s' not recognised." % (component))

    otype_id = db_access.get_override_type_id(otype)
    if otype_id == -1:
        utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc)" % (otype))

    override.setdefault(suite, {})
    override[suite].setdefault(component, {})
    override[suite][component].setdefault(otype, {})

    if otype == "dsc":
        q = projectB.query("SELECT o.package, s.section, o.maintainer FROM override o, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.section = s.id ORDER BY s.section, o.package" % (suite_id, component_id, otype_id))
        for i in q.getresult():
            override[suite][component][otype][i[0]] = i
            output_file.write(utils.result_join(i)+'\n')
    else:
        q = projectB.query("SELECT o.package, p.priority, s.section, o.maintainer, p.level FROM override o, priority p, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.priority = p.id AND o.section = s.id ORDER BY s.section, p.level, o.package" % (suite_id, component_id, otype_id))
        for i in q.getresult():
            i = i[:-1]; # Strip the priority level
            override[suite][component][otype][i[0]] = i
            output_file.write(utils.result_join(i)+'\n')

################################################################################

def main ():
    global Cnf, projectB, override

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Denise::Options::Help")]
    for i in [ "help" ]:
	if not Cnf.has_key("Denise::Options::%s" % (i)):
	    Cnf["Denise::Options::%s" % (i)] = ""
    apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Denise::Options")
    if Options["Help"]:
	usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    db_access.init(Cnf, projectB)

    for suite in Cnf.SubTree("Cindy::OverrideSuites").List():
        if Cnf.has_key("Suite::%s::Untouchable" % suite) and Cnf["Suite::%s::Untouchable" % suite] != 0:
            continue
        suite = suite.lower()

        sys.stderr.write("Processing %s...\n" % (suite))
        override_suite = Cnf["Suite::%s::OverrideCodeName" % (suite)]
        for component in Cnf.SubTree("Component").List():
            if component == "mixed":
                continue; # Ick
            for otype in Cnf.ValueList("OverrideType"):
                if otype == "deb":
                    suffix = ""
                elif otype == "udeb":
                    if component != "main":
                        continue; # Ick2
                    suffix = ".debian-installer"
                elif otype == "dsc":
                    suffix = ".src"
                filename = "%s/override.%s.%s%s" % (Cnf["Dir::Override"], override_suite, component.replace("non-US/", ""), suffix)
                output_file = utils.open_file(filename, 'w')
                do_list(output_file, suite, component, otype)
                output_file.close()

################################################################################

if __name__ == '__main__':
    main()
