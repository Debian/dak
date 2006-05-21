#!/usr/bin/env python

# Cruft checker and hole filler for overrides
# Copyright (C) 2000, 2001, 2002, 2004, 2006  James Troup <james@nocrew.org>
# Copyright (C) 2005  Jeroen van Wolffelaar <jeroen@wolffelaar.nl>

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

######################################################################
# NB: dak check-overrides is not a good idea with New Incoming as it #
# doesn't take into account accepted.  You can minimize the impact   #
# of this by running it immediately after dak process-accepted but   #
# that's still racy because 'dak process-new' doesn't lock with 'dak #
# process-accepted'.  A better long term fix is the evil plan for    #
# accepted to be in the DB.                                          #
######################################################################

# dak check-overrides should now work fine being done during
# cron.daily, for example just before 'dak make-overrides' (after 'dak
# process-accepted' and 'dak make-suite-file-list'). At that point,
# queue/accepted should be empty and installed, so... dak
# check-overrides does now take into account suites sharing overrides

# TODO:
# * Only update out-of-sync overrides when corresponding versions are equal to
#   some degree
# * consistency checks like:
#   - section=debian-installer only for udeb and # dsc
#   - priority=source iff dsc
#   - (suite, package, 'dsc') is unique,
#   - just as (suite, package, (u)deb) (yes, across components!)
#   - sections match their component (each component has an own set of sections,
#     could probably be reduced...)

################################################################################

import pg, sys, os
import apt_pkg
import daklib.database
import daklib.logging
import daklib.utils

################################################################################

Options = None
projectB = None
Logger = None
sections = {}
priorities = {}
blacklist = {}

################################################################################

def usage (exit_code=0):
    print """Usage: dak check-overrides
Check for cruft in overrides.

  -n, --no-action            don't do anything
  -h, --help                 show this help and exit"""

    sys.exit(exit_code)

################################################################################

def gen_blacklist(dir):
    for entry in os.listdir(dir):
        entry = entry.split('_')[0]
        blacklist[entry] = 1

def process(osuite, affected_suites, originosuite, component, type):
    global Logger, Options, projectB, sections, priorities

    osuite_id = daklib.database.get_suite_id(osuite)
    if osuite_id == -1:
        daklib.utils.fubar("Suite '%s' not recognised." % (osuite))
    originosuite_id = None
    if originosuite:
        originosuite_id = daklib.database.get_suite_id(originosuite)
        if originosuite_id == -1:
            daklib.utils.fubar("Suite '%s' not recognised." % (originosuite))

    component_id = daklib.database.get_component_id(component)
    if component_id == -1:
        daklib.utils.fubar("Component '%s' not recognised." % (component))

    type_id = daklib.database.get_override_type_id(type)
    if type_id == -1:
        daklib.utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc)" % (type))
    dsc_type_id = daklib.database.get_override_type_id("dsc")
    deb_type_id = daklib.database.get_override_type_id("deb")

    source_priority_id = daklib.database.get_priority_id("source")

    if type == "deb" or type == "udeb":
        packages = {}
        q = projectB.query("""
SELECT b.package FROM binaries b, bin_associations ba, files f,
                              location l, component c
 WHERE b.type = '%s' AND b.id = ba.bin AND f.id = b.file AND l.id = f.location
   AND c.id = l.component AND ba.suite IN (%s) AND c.id = %s
""" % (type, ",".join([ str(i) for i in affected_suites ]), component_id))
        for i in q.getresult():
            packages[i[0]] = 0

    src_packages = {}
    q = projectB.query("""
SELECT s.source FROM source s, src_associations sa, files f, location l,
                     component c
 WHERE s.id = sa.source AND f.id = s.file AND l.id = f.location
   AND c.id = l.component AND sa.suite IN (%s) AND c.id = %s
""" % (",".join([ str(i) for i in affected_suites]), component_id))
    for i in q.getresult():
        src_packages[i[0]] = 0

    # -----------
    # Drop unused overrides

    q = projectB.query("SELECT package, priority, section, maintainer FROM override WHERE suite = %s AND component = %s AND type = %s" % (osuite_id, component_id, type_id))
    projectB.query("BEGIN WORK")
    if type == "dsc":
        for i in q.getresult():
            package = i[0]
            if src_packages.has_key(package):
                src_packages[package] = 1
            else:
                if blacklist.has_key(package):
                    daklib.utils.warn("%s in incoming, not touching" % package)
                    continue
                Logger.log(["removing unused override", osuite, component,
                    type, package, priorities[i[1]], sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    projectB.query("""DELETE FROM override WHERE package =
                        '%s' AND suite = %s AND component = %s AND type =
                        %s""" % (package, osuite_id, component_id, type_id))
        # create source overrides based on binary overrides, as source
        # overrides not always get created
        q = projectB.query(""" SELECT package, priority, section,
            maintainer FROM override WHERE suite = %s AND component = %s
            """ % (osuite_id, component_id))
        for i in q.getresult():
            package = i[0]
            if not src_packages.has_key(package) or src_packages[package]:
                continue
            src_packages[package] = 1
            
            Logger.log(["add missing override", osuite, component,
                type, package, "source", sections[i[2]], i[3]])
            if not Options["No-Action"]:
                projectB.query("""INSERT INTO override (package, suite,
                    component, priority, section, type, maintainer) VALUES
                    ('%s', %s, %s, %s, %s, %s, '%s')""" % (package,
                    osuite_id, component_id, source_priority_id, i[2],
                    dsc_type_id, i[3]))
        # Check whether originosuite has an override for us we can
        # copy
        if originosuite:
            q = projectB.query("""SELECT origin.package, origin.priority,
                origin.section, origin.maintainer, target.priority,
                target.section, target.maintainer FROM override origin LEFT
                JOIN override target ON (origin.package = target.package AND
                target.suite=%s AND origin.component = target.component AND origin.type =
                target.type) WHERE origin.suite = %s AND origin.component = %s
                AND origin.type = %s""" %
                (osuite_id, originosuite_id, component_id, type_id))
            for i in q.getresult():
                package = i[0]
                if not src_packages.has_key(package) or src_packages[package]:
                    if i[4] and (i[1] != i[4] or i[2] != i[5] or i[3] != i[6]):
                        Logger.log(["syncing override", osuite, component,
                            type, package, "source", sections[i[5]], i[6], "source", sections[i[2]], i[3]])
                        if not Options["No-Action"]:
                            projectB.query("""UPDATE override SET section=%s,
                                maintainer='%s' WHERE package='%s' AND
                                suite=%s AND component=%s AND type=%s""" %
                                (i[2], i[3], package, osuite_id, component_id,
                                dsc_type_id))
                    continue
                # we can copy
                src_packages[package] = 1
                Logger.log(["copying missing override", osuite, component,
                    type, package, "source", sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    projectB.query("""INSERT INTO override (package, suite,
                        component, priority, section, type, maintainer) VALUES
                        ('%s', %s, %s, %s, %s, %s, '%s')""" % (package,
                        osuite_id, component_id, source_priority_id, i[2],
                        dsc_type_id, i[3]))

        for package, hasoverride in src_packages.items():
            if not hasoverride:
                daklib.utils.warn("%s has no override!" % package)

    else: # binary override
        for i in q.getresult():
            package = i[0]
            if packages.has_key(package):
                packages[package] = 1
            else:
                if blacklist.has_key(package):
                    daklib.utils.warn("%s in incoming, not touching" % package)
                    continue
                Logger.log(["removing unused override", osuite, component,
                    type, package, priorities[i[1]], sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    projectB.query("""DELETE FROM override WHERE package =
                        '%s' AND suite = %s AND component = %s AND type =
                        %s""" % (package, osuite_id, component_id, type_id))

        # Check whether originosuite has an override for us we can
        # copy
        if originosuite:
            q = projectB.query("""SELECT origin.package, origin.priority,
                origin.section, origin.maintainer, target.priority,
                target.section, target.maintainer FROM override origin LEFT
                JOIN override target ON (origin.package = target.package AND
                target.suite=%s AND origin.component = target.component AND
                origin.type = target.type) WHERE origin.suite = %s AND
                origin.component = %s AND origin.type = %s""" % (osuite_id,
                originosuite_id, component_id, type_id))
            for i in q.getresult():
                package = i[0]
                if not packages.has_key(package) or packages[package]:
                    if i[4] and (i[1] != i[4] or i[2] != i[5] or i[3] != i[6]):
                        Logger.log(["syncing override", osuite, component,
                            type, package, priorities[i[4]], sections[i[5]],
                            i[6], priorities[i[1]], sections[i[2]], i[3]])
                        if not Options["No-Action"]:
                            projectB.query("""UPDATE override SET priority=%s, section=%s,
                                maintainer='%s' WHERE package='%s' AND
                                suite=%s AND component=%s AND type=%s""" %
                                (i[1], i[2], i[3], package, osuite_id,
                                component_id, type_id))
                    continue
                # we can copy
                packages[package] = 1
                Logger.log(["copying missing override", osuite, component,
                    type, package, priorities[i[1]], sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    projectB.query("""INSERT INTO override (package, suite,
                        component, priority, section, type, maintainer) VALUES
                        ('%s', %s, %s, %s, %s, %s, '%s')""" % (package, osuite_id, component_id, i[1], i[2], type_id, i[3]))

        for package, hasoverride in packages.items():
            if not hasoverride:
                daklib.utils.warn("%s has no override!" % package)

    projectB.query("COMMIT WORK")
    sys.stdout.flush()


################################################################################

def main ():
    global Logger, Options, projectB, sections, priorities

    Cnf = daklib.utils.get_conf()

    Arguments = [('h',"help","Check-Overrides::Options::Help"),
                 ('n',"no-action", "Check-Overrides::Options::No-Action")]
    for i in [ "help", "no-action" ]:
        if not Cnf.has_key("Check-Overrides::Options::%s" % (i)):
            Cnf["Check-Overrides::Options::%s" % (i)] = ""
    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)
    Options = Cnf.SubTree("Check-Overrides::Options")

    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)

    # init sections, priorities:
    q = projectB.query("SELECT id, section FROM section")
    for i in q.getresult():
        sections[i[0]] = i[1]
    q = projectB.query("SELECT id, priority FROM priority")
    for i in q.getresult():
        priorities[i[0]] = i[1]

    if not Options["No-Action"]:
        Logger = daklib.logging.Logger(Cnf, "check-overrides")
    else:
        Logger = daklib.logging.Logger(Cnf, "check-overrides", 1)

    gen_blacklist(Cnf["Dir::Queue::Accepted"])

    for osuite in Cnf.SubTree("Check-Overrides::OverrideSuites").List():
        if "1" != Cnf["Check-Overrides::OverrideSuites::%s::Process" % osuite]:
            continue

        osuite = osuite.lower()

        originosuite = None
        originremark = ""
        try:
            originosuite = Cnf["Check-Overrides::OverrideSuites::%s::OriginSuite" % osuite]
            originosuite = originosuite.lower()
            originremark = " taking missing from %s" % originosuite
        except KeyError:
            pass

        print "Processing %s%s..." % (osuite, originremark)
        # Get a list of all suites that use the override file of 'osuite'
        ocodename = Cnf["Suite::%s::codename" % osuite]
        suites = []
        for suite in Cnf.SubTree("Suite").List():
            if ocodename == Cnf["Suite::%s::OverrideCodeName" % suite]:
                suites.append(suite)

        q = projectB.query("SELECT id FROM suite WHERE suite_name in (%s)" \
            % ", ".join([ repr(i) for i in suites ]).lower())

        suiteids = []
        for i in q.getresult():
            suiteids.append(i[0])
            
        if len(suiteids) != len(suites) or len(suiteids) < 1:
            daklib.utils.fubar("Couldn't find id's of all suites: %s" % suites)

        for component in Cnf.SubTree("Component").List():
            if component == "mixed":
                continue; # Ick
            # It is crucial for the dsc override creation based on binary
            # overrides that 'dsc' goes first
            otypes = Cnf.ValueList("OverrideType")
            otypes.remove("dsc")
            otypes = ["dsc"] + otypes
            for otype in otypes:
                print "Processing %s [%s - %s] using %s..." \
                    % (osuite, component, otype, suites)
                sys.stdout.flush()
                process(osuite, suiteids, originosuite, component, otype)

    Logger.close()

################################################################################

if __name__ == '__main__':
    main()

