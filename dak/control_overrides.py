#!/usr/bin/env python

# Bulk manipulation of the overrides
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

# On 30 Nov 1998, James Troup wrote:
# 
# > James Troup<2> <troup2@debian.org>
# > 
# >    James is a clone of James; he's going to take over the world.
# >    After he gets some sleep.
# 
# Could you clone other things too? Sheep? Llamas? Giant mutant turnips?
# 
# Your clone will need some help to take over the world, maybe clone up an
# army of penguins and threaten to unleash them on the world, forcing
# governments to sway to the new James' will!
# 
# Yes, I can envision a day when James' duplicate decides to take a horrific
# vengance on the James that spawned him and unleashes his fury in the form
# of thousands upon thousands of chickens that look just like Captin Blue
# Eye! Oh the horror.
# 
# Now you'll have to were name tags to people can tell you apart, unless of
# course the new clone is truely evil in which case he should be easy to
# identify!
# 
# Jason
# Chicken. Black. Helicopters.
# Be afraid.

# <Pine.LNX.3.96.981130011300.30365Z-100000@wakko>

################################################################################

import pg, sys, time
import utils, database, logging
import apt_pkg

################################################################################

Cnf = None
projectB = None
Logger = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak control-overrides [OPTIONS]
  -h, --help               print this help and exit

  -c, --component=CMPT     list/set overrides by component
                                  (contrib,*main,non-free)
  -s, --suite=SUITE        list/set overrides by suite
                                  (experimental,stable,testing,*unstable)
  -t, --type=TYPE          list/set overrides by type
                                  (*deb,dsc,udeb)

  -a, --add                add overrides (changes and deletions are ignored)
  -S, --set                set overrides
  -l, --list               list overrides

  -q, --quiet              be less verbose

 starred (*) values are default"""
    sys.exit(exit_code)

################################################################################

def process_file (file, suite, component, type, action):
    suite_id = daklib.database.get_suite_id(suite)
    if suite_id == -1:
        daklib.utils.fubar("Suite '%s' not recognised." % (suite))

    component_id = daklib.database.get_component_id(component)
    if component_id == -1:
        daklib.utils.fubar("Component '%s' not recognised." % (component))

    type_id = daklib.database.get_override_type_id(type)
    if type_id == -1:
        daklib.utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc.)" % (type))

    # --set is done mostly internal for performance reasons; most
    # invocations of --set will be updates and making people wait 2-3
    # minutes while 6000 select+inserts are run needlessly isn't cool.

    original = {}
    new = {}
    c_skipped = 0
    c_added = 0
    c_updated = 0
    c_removed = 0
    c_error = 0

    q = projectB.query("SELECT o.package, o.priority, o.section, o.maintainer, p.priority, s.section FROM override o, priority p, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s and o.priority = p.id and o.section = s.id"
                       % (suite_id, component_id, type_id))
    for i in q.getresult():
        original[i[0]] = i[1:]

    start_time = time.time()
    projectB.query("BEGIN WORK")
    for line in file.readlines():
        line = daklib.utils.re_comments.sub('', line).strip()
        if line == "":
            continue

        maintainer_override = None
        if type == "dsc":
            split_line = line.split(None, 2)
            if len(split_line) == 2:
                (package, section) = split_line
            elif len(split_line) == 3:
                (package, section, maintainer_override) = split_line
            else:
                daklib.utils.warn("'%s' does not break into 'package section [maintainer-override]'." % (line))
                c_error += 1
                continue
            priority = "source"
        else: # binary or udeb
            split_line = line.split(None, 3)
            if len(split_line) == 3:
                (package, priority, section) = split_line
            elif len(split_line) == 4:
                (package, priority, section, maintainer_override) = split_line
            else:
                daklib.utils.warn("'%s' does not break into 'package priority section [maintainer-override]'." % (line))
                c_error += 1
                continue

        section_id = daklib.database.get_section_id(section)
        if section_id == -1:
            daklib.utils.warn("'%s' is not a valid section. ['%s' in suite %s, component %s]." % (section, package, suite, component))
            c_error += 1
            continue
        priority_id = daklib.database.get_priority_id(priority)
        if priority_id == -1:
            daklib.utils.warn("'%s' is not a valid priority. ['%s' in suite %s, component %s]." % (priority, package, suite, component))
            c_error += 1
            continue

        if new.has_key(package):
            daklib.utils.warn("Can't insert duplicate entry for '%s'; ignoring all but the first. [suite %s, component %s]" % (package, suite, component))
            c_error += 1
            continue
        new[package] = ""
        if original.has_key(package):
            (old_priority_id, old_section_id, old_maintainer_override, old_priority, old_section) = original[package]
            if action == "add" or old_priority_id == priority_id and \
               old_section_id == section_id and \
               ((old_maintainer_override == maintainer_override) or \
		(old_maintainer_override == "" and maintainer_override == None)):
                # If it's unchanged or we're in 'add only' mode, ignore it
                c_skipped += 1
                continue
            else:
                # If it's changed, delete the old one so we can
                # reinsert it with the new information
                c_updated += 1
                projectB.query("DELETE FROM override WHERE suite = %s AND component = %s AND package = '%s' AND type = %s"
                               % (suite_id, component_id, package, type_id))
                # Log changes
                if old_priority_id != priority_id:
                    Logger.log(["changed priority",package,old_priority,priority])
                if old_section_id != section_id:
                    Logger.log(["changed section",package,old_section,section])
                if old_maintainer_override != maintainer_override:
                    Logger.log(["changed maintainer override",package,old_maintainer_override,maintainer_override])
                update_p = 1
        else:
            c_added += 1
            update_p = 0

        if maintainer_override:
            projectB.query("INSERT INTO override (suite, component, type, package, priority, section, maintainer) VALUES (%s, %s, %s, '%s', %s, %s, '%s')"
                           % (suite_id, component_id, type_id, package, priority_id, section_id, maintainer_override))
        else:
            projectB.query("INSERT INTO override (suite, component, type, package, priority, section,maintainer) VALUES (%s, %s, %s, '%s', %s, %s, '')"
                           % (suite_id, component_id, type_id, package, priority_id, section_id))

        if not update_p:
            Logger.log(["new override",suite,component,type,package,priority,section,maintainer_override])

    if not action == "add":
        # Delete any packages which were removed
        for package in original.keys():
            if not new.has_key(package):
                projectB.query("DELETE FROM override WHERE suite = %s AND component = %s AND package = '%s' AND type = %s"
                               % (suite_id, component_id, package, type_id))
                c_removed += 1
                Logger.log(["removed override",suite,component,type,package])

    projectB.query("COMMIT WORK")
    if not Cnf["Control-Overrides::Options::Quiet"]:
        print "Done in %d seconds. [Updated = %d, Added = %d, Removed = %d, Skipped = %d, Errors = %d]" % (int(time.time()-start_time), c_updated, c_added, c_removed, c_skipped, c_error)
    Logger.log(["set complete",c_updated, c_added, c_removed, c_skipped, c_error])

################################################################################

def list(suite, component, type):
    suite_id = daklib.database.get_suite_id(suite)
    if suite_id == -1:
        daklib.utils.fubar("Suite '%s' not recognised." % (suite))

    component_id = daklib.database.get_component_id(component)
    if component_id == -1:
        daklib.utils.fubar("Component '%s' not recognised." % (component))

    type_id = daklib.database.get_override_type_id(type)
    if type_id == -1:
        daklib.utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc)" % (type))

    if type == "dsc":
        q = projectB.query("SELECT o.package, s.section, o.maintainer FROM override o, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.section = s.id ORDER BY s.section, o.package" % (suite_id, component_id, type_id))
        for i in q.getresult():
            print daklib.utils.result_join(i)
    else:
        q = projectB.query("SELECT o.package, p.priority, s.section, o.maintainer, p.level FROM override o, priority p, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.priority = p.id AND o.section = s.id ORDER BY s.section, p.level, o.package" % (suite_id, component_id, type_id))
        for i in q.getresult():
            print daklib.utils.result_join(i[:-1])

################################################################################

def main ():
    global Cnf, projectB, Logger

    Cnf = daklib.utils.get_conf()
    Arguments = [('a', "add", "Control-Overrides::Options::Add"),
                 ('c', "component", "Control-Overrides::Options::Component", "HasArg"),
                 ('h', "help", "Control-Overrides::Options::Help"),
                 ('l', "list", "Control-Overrides::Options::List"),
                 ('q', "quiet", "Control-Overrides::Options::Quiet"),
                 ('s', "suite", "Control-Overrides::Options::Suite", "HasArg"),
                 ('S', "set", "Control-Overrides::Options::Set"),
                 ('t', "type", "Control-Overrides::Options::Type", "HasArg")]

    # Default arguments
    for i in [ "add", "help", "list", "quiet", "set" ]:
	if not Cnf.has_key("Control-Overrides::Options::%s" % (i)):
	    Cnf["Control-Overrides::Options::%s" % (i)] = ""
    if not Cnf.has_key("Control-Overrides::Options::Component"):
	Cnf["Control-Overrides::Options::Component"] = "main"
    if not Cnf.has_key("Control-Overrides::Options::Suite"):
	Cnf["Control-Overrides::Options::Suite"] = "unstable"
    if not Cnf.has_key("Control-Overrides::Options::Type"):
	Cnf["Control-Overrides::Options::Type"] = "deb"

    file_list = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)

    if Cnf["Control-Overrides::Options::Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)

    action = None
    for i in [ "add", "list", "set" ]:
        if Cnf["Control-Overrides::Options::%s" % (i)]:
            if action:
                daklib.utils.fubar("Can not perform more than one action at once.")
            action = i

    (suite, component, type) = (Cnf["Control-Overrides::Options::Suite"],
                                Cnf["Control-Overrides::Options::Component"],
                                Cnf["Control-Overrides::Options::Type"])

    if action == "list":
        list(suite, component, type)
    else:
        Logger = daklib.logging.Logger(Cnf, "control-overrides")
        if file_list:
            for file in file_list:
                process_file(daklib.utils.open_file(file), suite, component, type, action)
        else:
            process_file(sys.stdin, suite, component, type, action)
        Logger.close()

#######################################################################################

if __name__ == '__main__':
    main()

