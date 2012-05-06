#!/usr/bin/env python

""" Bulk manipulation of the overrides """
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

import sys, time
import apt_pkg

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils
from daklib import daklog
from daklib.regexes import re_comments

################################################################################

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
  -C, --change             change overrides (additions and deletions are ignored)
  -l, --list               list overrides

  -q, --quiet              be less verbose
  -n, --no-action          only list the action that would have been done

 starred (*) values are default"""
    sys.exit(exit_code)

################################################################################

def process_file(file, suite, component, otype, mode, action, session):
    cnf = Config()

    s = get_suite(suite, session=session)
    if s is None:
        utils.fubar("Suite '%s' not recognised." % (suite))
    suite_id = s.suite_id

    c = get_component(component, session=session)
    if c is None:
        utils.fubar("Component '%s' not recognised." % (component))
    component_id = c.component_id

    o = get_override_type(otype)
    if o is None:
        utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc.)" % (otype))
    type_id = o.overridetype_id

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

    q = session.execute("""SELECT o.package, o.priority, o.section, o.maintainer, p.priority, s.section
                           FROM override o, priority p, section s
                           WHERE o.suite = :suiteid AND o.component = :componentid AND o.type = :typeid
                             and o.priority = p.id and o.section = s.id""",
                           {'suiteid': suite_id, 'componentid': component_id, 'typeid': type_id})
    for i in q.fetchall():
        original[i[0]] = i[1:]

    start_time = time.time()

    section_cache = get_sections(session)
    priority_cache = get_priorities(session)

    # Our session is already in a transaction

    for line in file.readlines():
        line = re_comments.sub('', line).strip()
        if line == "":
            continue

        maintainer_override = None
        if otype == "dsc":
            split_line = line.split(None, 2)
            if len(split_line) == 2:
                (package, section) = split_line
            elif len(split_line) == 3:
                (package, section, maintainer_override) = split_line
            else:
                utils.warn("'%s' does not break into 'package section [maintainer-override]'." % (line))
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
                utils.warn("'%s' does not break into 'package priority section [maintainer-override]'." % (line))
                c_error += 1
                continue

        if not section_cache.has_key(section):
            utils.warn("'%s' is not a valid section. ['%s' in suite %s, component %s]." % (section, package, suite, component))
            c_error += 1
            continue

        section_id = section_cache[section]

        if not priority_cache.has_key(priority):
            utils.warn("'%s' is not a valid priority. ['%s' in suite %s, component %s]." % (priority, package, suite, component))
            c_error += 1
            continue

        priority_id = priority_cache[priority]

        if new.has_key(package):
            utils.warn("Can't insert duplicate entry for '%s'; ignoring all but the first. [suite %s, component %s]" % (package, suite, component))
            c_error += 1
            continue
        new[package] = ""

        if original.has_key(package):
            (old_priority_id, old_section_id, old_maintainer_override, old_priority, old_section) = original[package]
            if mode == "add" or old_priority_id == priority_id and \
               old_section_id == section_id and \
               old_maintainer_override == maintainer_override:
                # If it's unchanged or we're in 'add only' mode, ignore it
                c_skipped += 1
                continue
            else:
                # If it's changed, delete the old one so we can
                # reinsert it with the new information
                c_updated += 1
                if action:
                    session.execute("""DELETE FROM override WHERE suite = :suite AND component = :component
                                                              AND package = :package AND type = :typeid""",
                                    {'suite': suite_id,  'component': component_id,
                                     'package': package, 'typeid': type_id})

                # Log changes
                if old_priority_id != priority_id:
                    Logger.log(["changed priority", package, old_priority, priority])
                if old_section_id != section_id:
                    Logger.log(["changed section", package, old_section, section])
                if old_maintainer_override != maintainer_override:
                    Logger.log(["changed maintainer override", package, old_maintainer_override, maintainer_override])
                update_p = 1
        elif mode == "change":
            # Ignore additions in 'change only' mode
            c_skipped += 1
            continue
        else:
            c_added += 1
            update_p = 0

        if action:
            if not maintainer_override:
                m_o = None
            else:
                m_o = maintainer_override
            session.execute("""INSERT INTO override (suite, component, type, package,
                                                     priority, section, maintainer)
                                             VALUES (:suiteid, :componentid, :typeid,
                                                     :package, :priorityid, :sectionid,
                                                     :maintainer)""",
                              {'suiteid': suite_id, 'componentid': component_id,
                               'typeid':  type_id,  'package': package,
                               'priorityid': priority_id, 'sectionid': section_id,
                               'maintainer': m_o})

        if not update_p:
            Logger.log(["new override", suite, component, otype, package,priority,section,maintainer_override])

    if mode == "set":
        # Delete any packages which were removed
        for package in original.keys():
            if not new.has_key(package):
                if action:
                    session.execute("""DELETE FROM override
                                       WHERE suite = :suiteid AND component = :componentid
                                         AND package = :package AND type = :typeid""",
                                    {'suiteid': suite_id, 'componentid': component_id,
                                     'package': package, 'typeid': type_id})
                c_removed += 1
                Logger.log(["removed override", suite, component, otype, package])

    if action:
        session.commit()

    if not cnf["Control-Overrides::Options::Quiet"]:
        print "Done in %d seconds. [Updated = %d, Added = %d, Removed = %d, Skipped = %d, Errors = %d]" % (int(time.time()-start_time), c_updated, c_added, c_removed, c_skipped, c_error)

    Logger.log(["set complete", c_updated, c_added, c_removed, c_skipped, c_error])

################################################################################

def list_overrides(suite, component, otype, session):
    dat = {}
    s = get_suite(suite, session)
    if s is None:
        utils.fubar("Suite '%s' not recognised." % (suite))

    dat['suiteid'] = s.suite_id

    c = get_component(component, session)
    if c is None:
        utils.fubar("Component '%s' not recognised." % (component))

    dat['componentid'] = c.component_id

    o = get_override_type(otype)
    if o is None:
        utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc)" % (otype))

    dat['typeid'] = o.overridetype_id

    if otype == "dsc":
        q = session.execute("""SELECT o.package, s.section, o.maintainer FROM override o, section s
                                WHERE o.suite = :suiteid AND o.component = :componentid
                                  AND o.type = :typeid AND o.section = s.id
                             ORDER BY s.section, o.package""", dat)
        for i in q.fetchall():
            print utils.result_join(i)
    else:
        q = session.execute("""SELECT o.package, p.priority, s.section, o.maintainer, p.level
                                 FROM override o, priority p, section s
                                WHERE o.suite = :suiteid AND o.component = :componentid
                                  AND o.type = :typeid AND o.priority = p.id AND o.section = s.id
                             ORDER BY s.section, p.level, o.package""", dat)
        for i in q.fetchall():
            print utils.result_join(i[:-1])

################################################################################

def main ():
    global Logger

    cnf = Config()
    Arguments = [('a', "add", "Control-Overrides::Options::Add"),
                 ('c', "component", "Control-Overrides::Options::Component", "HasArg"),
                 ('h', "help", "Control-Overrides::Options::Help"),
                 ('l', "list", "Control-Overrides::Options::List"),
                 ('q', "quiet", "Control-Overrides::Options::Quiet"),
                 ('s', "suite", "Control-Overrides::Options::Suite", "HasArg"),
                 ('S', "set", "Control-Overrides::Options::Set"),
                 ('C', "change", "Control-Overrides::Options::Change"),
                 ('n', "no-action", "Control-Overrides::Options::No-Action"),
                 ('t', "type", "Control-Overrides::Options::Type", "HasArg")]

    # Default arguments
    for i in [ "add", "help", "list", "quiet", "set", "change", "no-action" ]:
        if not cnf.has_key("Control-Overrides::Options::%s" % (i)):
            cnf["Control-Overrides::Options::%s" % (i)] = ""
    if not cnf.has_key("Control-Overrides::Options::Component"):
        cnf["Control-Overrides::Options::Component"] = "main"
    if not cnf.has_key("Control-Overrides::Options::Suite"):
        cnf["Control-Overrides::Options::Suite"] = "unstable"
    if not cnf.has_key("Control-Overrides::Options::Type"):
        cnf["Control-Overrides::Options::Type"] = "deb"

    file_list = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    if cnf["Control-Overrides::Options::Help"]:
        usage()

    session = DBConn().session()

    mode = None
    for i in [ "add", "list", "set", "change" ]:
        if cnf["Control-Overrides::Options::%s" % (i)]:
            if mode:
                utils.fubar("Can not perform more than one action at once.")
            mode = i

    # Need an action...
    if mode is None:
        utils.fubar("No action specified.")

    (suite, component, otype) = (cnf["Control-Overrides::Options::Suite"],
                                 cnf["Control-Overrides::Options::Component"],
                                 cnf["Control-Overrides::Options::Type"])

    if mode == "list":
        list_overrides(suite, component, otype, session)
    else:
        if get_suite(suite).untouchable:
            utils.fubar("%s: suite is untouchable" % suite)

        action = True
        if cnf["Control-Overrides::Options::No-Action"]:
            utils.warn("In No-Action Mode")
            action = False

        Logger = daklog.Logger("control-overrides", mode)
        if file_list:
            for f in file_list:
                process_file(utils.open_file(f), suite, component, otype, mode, action, session)
        else:
            process_file(sys.stdin, suite, component, otype, mode, action, session)
        Logger.close()

#######################################################################################

if __name__ == '__main__':
    main()
