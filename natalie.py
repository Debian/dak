#!/usr/bin/env python

# Manipulate override files
# Copyright (C) 2000, 2001  James Troup <james@nocrew.org>
# $Id: natalie.py,v 1.13 2001-11-18 19:57:58 rmurray Exp $

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

import errno, os, pg, pwd, string, sys, time;
import utils, db_access, logging;
import apt_pkg;

################################################################################

Cnf = None;
projectB = None;
Logger = None;

################################################################################

def usage (exit_code=0):
    print """Usage: natalie.py [OPTIONS]
  -h, --help               this help
  -c, --component=CMPT     list/set overrides by component
                                  (contrib,*main,non-free)
  -s, --suite=SUITE        list/set overrides by suite
                                  (experimental,stable,testing,*unstable)
  -t, --type=TYPE          list/set overrides by type
                                  (*deb,dsc,udeb)
  -S, --set                set overrides from stdin
  -l, --list               list overrides on stdout

 starred (*) values are default"""
    sys.exit(exit_code)

################################################################################

def init ():
    global projectB;

    projectB = pg.connect('projectb', None);
    db_access.init(Cnf, projectB);

def process_file (file, suite, component, type):
    suite_id = db_access.get_suite_id(suite);
    if suite_id == -1:
        utils.fubar("Suite '%s' not recognised." % (suite));

    component_id = db_access.get_component_id(component);
    if component_id == -1:
        utils.fubar("Component '%s' not recognised." % (component));

    type_id = db_access.get_override_type_id(type);
    if type_id == -1:
        utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc.)" % (type));

    # --set is done mostly internal for performance reasons; most
    # invocations of --set will be updates and making people wait 2-3
    # minutes while 6000 select+inserts are run needlessly isn't cool.

    original = {};
    new = {};
    c_skipped = 0;
    c_added = 0;
    c_updated = 0;
    c_removed = 0;
    c_error = 0;

    q = projectB.query("SELECT o.package, o.priority, o.section, o.maintainer, p.priority, s.section FROM override o, priority p, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s and o.priority = p.id and o.section = s.id"
                       % (suite_id, component_id, type_id));
    for i in q.getresult():
        original[i[0]] = i[1:];

    start_time = time.time();
    projectB.query("BEGIN WORK");
    for line in file.readlines():
        line = string.strip(utils.re_comments.sub('', line[:-1]))
        if line == "":
            continue;

        maintainer_override = None;
        if type == "dsc":
            split_line = string.split(line, None, 2);
            if len(split_line) == 2:
                (package, section) = split_line;
            elif len(split_line) == 3:
                (package, section, maintainer_override) = split_line;
            else:
                utils.warn("'%s' does not break into 'package section [maintainer-override]'." % (line));
                c_error = c_error + 1;
                continue;
            priority = "source";
        else: # binary or udeb
            split_line = string.split(line, None, 3);
            if len(split_line) == 3:
                (package, priority, section) = split_line;
            elif len(split_line) == 4:
                (package, priority, section, maintainer_override) = split_line;
            else:
                utils.warn("'%s' does not break into 'package priority section [maintainer-override]'." % (line));
                c_error = c_error + 1;
                continue;

        section_id = db_access.get_section_id(section);
        if section_id == -1:
            utils.warn("'%s' is not a valid section. ['%s' in suite %s, component %s]." % (section, package, suite, component));
            c_error = c_error + 1;
            continue;
        priority_id = db_access.get_priority_id(priority);
        if priority_id == -1:
            utils.warn("'%s' is not a valid priority. ['%s' in suite %s, component %s]." % (priority, package, suite, component));
            c_error = c_error + 1;
            continue;

        if new.has_key(package):
            utils.warn("Can't insert duplicate entry for '%s'; ignoring all but the first. [suite %s, component %s]" % (package, suite, component));
            c_error = c_error + 1;
            continue;
        new[package] = "";
        if original.has_key(package):
            (old_priority_id, old_section_id, old_maintainer_override, old_priority, old_section) = original[package];
            if old_priority_id == priority_id and old_section_id == section_id and old_maintainer_override == maintainer_override:
                # Same?  Ignore it
                c_skipped = c_skipped + 1;
                continue;
            else:
                # Changed?  Delete the old one so we can reinsert it with the new information
                c_updated = c_updated + 1;
                projectB.query("DELETE FROM override WHERE suite = %s AND component = %s AND package = '%s' AND type = %s"
                               % (suite_id, component_id, package, type_id));
                # Log changes
                if old_priority_id != priority_id:
                    Logger.log(["changed priority",package,old_priority,priority]);
                if old_section_id != section_id:
                    Logger.log(["changed section",package,old_section,section]);
                if old_maintainer_override != maintainer_override:
                    Logger.log(["changed maintainer override",package,old_maintainer_override,maintainer_override]);
                update_p = 1;
        else:
            c_added = c_added + 1;
            update_p = 0;

        if maintainer_override:
            projectB.query("INSERT INTO override (suite, component, type, package, priority, section, maintainer) VALUES (%s, %s, %s, '%s', %s, %s, '%s')"
                           % (suite_id, component_id, type_id, package, priority_id, section_id, maintainer_override));
        else:
            projectB.query("INSERT INTO override (suite, component, type, package, priority, section) VALUES (%s, %s, %s, '%s', %s, %s)"
                           % (suite_id, component_id, type_id, package, priority_id, section_id));

        if not update_p:
            Logger.log(["new override",suite,component,type,package,priority,section,maintainer_override]);

    # Delete any packages which were removed
    for package in original.keys():
        if not new.has_key(package):
            projectB.query("DELETE FROM override WHERE suite = %s AND component = %s AND package = '%s' AND type = %s"
                           % (suite_id, component_id, package, type_id));
            c_removed = c_removed + 1;
            Logger.log(["removed override",suite,component,type,package]);

    projectB.query("COMMIT WORK");
    print "Done in %d seconds. [Updated = %d, Added = %d, Removed = %d, Skipped = %d, Errors = %d]" % (int(time.time()-start_time), c_updated, c_added, c_removed, c_skipped, c_error);
    Logger.log(["set complete",c_updated, c_added, c_removed, c_skipped, c_error]);

################################################################################

def list(suite, component, type):
    suite_id = db_access.get_suite_id(suite);
    if suite_id == -1:
        utils.fubar("Suite '%s' not recognised." % (suite));

    component_id = db_access.get_component_id(component);
    if component_id == -1:
        utils.fubar("Component '%s' not recognised." % (component));

    type_id = db_access.get_override_type_id(type);
    if type_id == -1:
        utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc)" % (type));

    if type == "dsc":
        q = projectB.query("SELECT o.package, s.section, o.maintainer FROM override o, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.section = s.id ORDER BY s.section, o.package" % (suite_id, component_id, type_id));
        for i in q.getresult():
            print utils.result_join(i);
    else:
        q = projectB.query("SELECT o.package, p.priority, s.section, o.maintainer, p.level FROM override o, priority p, section s WHERE o.suite = %s AND o.component = %s AND o.type = %s AND o.priority = p.id AND o.section = s.id ORDER BY s.section, p.level, o.package" % (suite_id, component_id, type_id));
        for i in q.getresult():
            print utils.result_join(i[:-1]);

################################################################################

def main ():
    global Cnf, projectB, Logger;

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Natalie::Options::Help"),
                 ('c',"component", "Natalie::Options::Component", "HasArg"),
                 ('l',"list", "Natalie::Options::List"),
                 ('s',"suite","Natalie::Options::Suite", "HasArg"),
                 ('S',"set","Natalie::Options::Set"),
                 ('t',"type","Natalie::Options::Type", "HasArg")];

    # Default arguments
    for i in ["help", "list", "set" ]:
	if not Cnf.has_key("Natalie::Options::%s" (i)):
	    Cnf["Natalie::Options::%s" % (i)] = "";
    if not Cnf.has_key("Natalie::Options::Component"):
	Cnf["Natalie::Options::Component"] = "main";
    if not Cnf.has_key("Natalie::Options::Suite"):
	Cnf["Natalie::Options::Suite"] = "unstable";
    if not Cnf.has_key("Natalie::Options::Type"):
	Cnf["Natalie::Options::Type"] = "deb";

    file_list = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv);

    if Cnf["Natalie::Options::Help"]:
        usage();

    init();

    action = None;
    for i in [ "list", "set" ]:
        if Cnf["Natalie::Options::%s" % (i)]:
            if action != None:
                utils.fubar("Can not perform more than one action at once.");
            action = i;

    (suite, component, type) = (Cnf["Natalie::Options::Suite"], Cnf["Natalie::Options::Component"], Cnf["Natalie::Options::Type"])

    if action == "list":
        list(suite, component, type);
    else:
        Logger = logging.Logger(Cnf, "natalie");
        if file_list != []:
            for file in file_list:
                process_file(utils.open_file(file), suite, component, type);
        else:
            process_file(sys.stdin, suite, component, type);
        Logger.close();

#######################################################################################

if __name__ == '__main__':
    main()

