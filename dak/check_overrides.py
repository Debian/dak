#!/usr/bin/env python

""" Cruft checker and hole filler for overrides

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2004, 2006  James Troup <james@nocrew.org>
@opyright: 2005  Jeroen van Wolffelaar <jeroen@wolffelaar.nl>
@copyright: 2011  Joerg Jaspert <joerg@debian.org>
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

import sys, os
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib import daklog
from daklib import utils

################################################################################

Options = None                 #: Commandline arguments parsed into this
Logger = None                  #: Our logging object
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

def process(osuite, affected_suites, originosuite, component, otype, session):
    global Logger, Options, sections, priorities

    o = get_suite(osuite, session)
    if o is None:
        utils.fubar("Suite '%s' not recognised." % (osuite))
    osuite_id = o.suite_id

    originosuite_id = None
    if originosuite:
        oo = get_suite(originosuite, session)
        if oo is None:
            utils.fubar("Suite '%s' not recognised." % (originosuite))
        originosuite_id = oo.suite_id

    c = get_component(component, session)
    if c is None:
        utils.fubar("Component '%s' not recognised." % (component))
    component_id = c.component_id

    ot = get_override_type(otype, session)
    if ot is None:
        utils.fubar("Type '%s' not recognised. (Valid types are deb, udeb and dsc)" % (otype))
    type_id = ot.overridetype_id
    dsc_type_id = get_override_type("dsc", session).overridetype_id

    source_priority_id = get_priority("source", session).priority_id

    if otype == "deb" or otype == "udeb":
        packages = {}
        # TODO: Fix to use placeholders (check how to with arrays)
        q = session.execute("""
SELECT b.package
  FROM binaries b
  JOIN bin_associations ba ON b.id = ba.bin
  JOIN suite ON ba.suite = suite.id
  JOIN files_archive_map af ON b.file = af.file_id AND suite.archive_id = af.archive_id
 WHERE b.type = :otype AND ba.suite IN (%s) AND af.component_id = :component_id
""" % (",".join([ str(i) for i in affected_suites ])), {'otype': otype, 'component_id': component_id})
        for i in q.fetchall():
            packages[i[0]] = 0

    src_packages = {}
    q = session.execute("""
SELECT s.source FROM source s
  JOIN src_associations sa ON s.id = sa.source
  JOIN suite ON sa.suite = suite.id
  JOIN files_archive_map af ON s.file = af.file_id AND suite.archive_id = af.archive_id
 WHERE sa.suite IN (%s) AND af.component_id = :component_id
""" % (",".join([ str(i) for i in affected_suites])), {'component_id': component_id})
    for i in q.fetchall():
        src_packages[i[0]] = 0

    # -----------
    # Drop unused overrides

    q = session.execute("""SELECT package, priority, section, maintainer
                             FROM override WHERE suite = :suite_id
                              AND component = :component_id AND type = :type_id""",
                        {'suite_id': osuite_id, 'component_id': component_id,
                         'type_id': type_id})
    # We're already within a transaction
    if otype == "dsc":
        for i in q.fetchall():
            package = i[0]
            if src_packages.has_key(package):
                src_packages[package] = 1
            else:
                if blacklist.has_key(package):
                    utils.warn("%s in incoming, not touching" % package)
                    continue
                Logger.log(["removing unused override", osuite, component,
                    otype, package, priorities[i[1]], sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    session.execute("""DELETE FROM override WHERE package = :package
                                          AND suite = :suite_id AND component = :component_id
                                          AND type = :type_id
                                          AND created < now() - interval '14 days'""",
                                    {'package': package, 'suite_id': osuite_id,
                                     'component_id': component_id, 'type_id': type_id})
        # create source overrides based on binary overrides, as source
        # overrides not always get created
        q = session.execute("""SELECT package, priority, section, maintainer
                                 FROM override WHERE suite = :suite_id AND component = :component_id""",
                            {'suite_id': osuite_id, 'component_id': component_id})
        for i in q.fetchall():
            package = i[0]
            if not src_packages.has_key(package) or src_packages[package]:
                continue
            src_packages[package] = 1

            Logger.log(["add missing override", osuite, component,
                otype, package, "source", sections[i[2]], i[3]])
            if not Options["No-Action"]:
                session.execute("""INSERT INTO override (package, suite, component,
                                                        priority, section, type, maintainer)
                                         VALUES (:package, :suite_id, :component_id,
                                                 :priority_id, :section_id, :type_id, :maintainer)""",
                               {'package': package, 'suite_id': osuite_id,
                                'component_id': component_id, 'priority_id': source_priority_id,
                                'section_id': i[2], 'type_id': dsc_type_id, 'maintainer': i[3]})
        # Check whether originosuite has an override for us we can
        # copy
        if originosuite:
            q = session.execute("""SELECT origin.package, origin.priority, origin.section,
                                         origin.maintainer, target.priority, target.section,
                                         target.maintainer
                                    FROM override origin
                               LEFT JOIN override target ON (origin.package = target.package
                                                             AND target.suite = :suite_id
                                                             AND origin.component = target.component
                                                             AND origin.type = target.type)
                                   WHERE origin.suite = :originsuite_id
                                     AND origin.component = :component_id
                                     AND origin.type = :type_id""",
                                {'suite_id': osuite_id, 'originsuite_id': originosuite_id,
                                 'component_id': component_id, 'type_id': type_id})
            for i in q.fetchall():
                package = i[0]
                if not src_packages.has_key(package) or src_packages[package]:
                    if i[4] and (i[1] != i[4] or i[2] != i[5] or i[3] != i[6]):
                        Logger.log(["syncing override", osuite, component,
                            otype, package, "source", sections[i[5]], i[6], "source", sections[i[2]], i[3]])
                        if not Options["No-Action"]:
                            session.execute("""UPDATE override
                                                 SET section = :section,
                                                     maintainer = :maintainer
                                               WHERE package = :package AND suite = :suite_id
                                                 AND component = :component_id AND type = :type_id""",
                                            {'section': i[2], 'maintainer': i[3],
                                             'package': package, 'suite_id': osuite_id,
                                             'component_id': component_id, 'type_id': dsc_type_id})
                    continue

                # we can copy
                src_packages[package] = 1
                Logger.log(["copying missing override", osuite, component,
                    otype, package, "source", sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    session.execute("""INSERT INTO override (package, suite, component,
                                                             priority, section, type, maintainer)
                                            VALUES (:package, :suite_id, :component_id,
                                                    :priority_id, :section_id, :type_id,
                                                    :maintainer)""",
                                    {'package': package, 'suite_id': osuite_id,
                                     'component_id': component_id, 'priority_id': source_priority_id,
                                     'section_id': i[2], 'type_id': dsc_type_id, 'maintainer': i[3]})

        for package, hasoverride in src_packages.items():
            if not hasoverride:
                utils.warn("%s has no override!" % package)

    else: # binary override
        for i in q.fetchall():
            package = i[0]
            if packages.has_key(package):
                packages[package] = 1
            else:
                if blacklist.has_key(package):
                    utils.warn("%s in incoming, not touching" % package)
                    continue
                Logger.log(["removing unused override", osuite, component,
                    otype, package, priorities[i[1]], sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    session.execute("""DELETE FROM override
                                        WHERE package = :package AND suite = :suite_id
                                          AND component = :component_id AND type = :type_id
                                          AND created < now() - interval '14 days'""",
                                    {'package': package, 'suite_id': osuite_id,
                                     'component_id': component_id, 'type_id': type_id})

        # Check whether originosuite has an override for us we can
        # copy
        if originosuite:
            q = session.execute("""SELECT origin.package, origin.priority, origin.section,
                                          origin.maintainer, target.priority, target.section,
                                          target.maintainer
                                     FROM override origin LEFT JOIN override target
                                                          ON (origin.package = target.package
                                                              AND target.suite = :suite_id
                                                              AND origin.component = target.component
                                                              AND origin.type = target.type)
                                    WHERE origin.suite = :originsuite_id
                                      AND origin.component = :component_id
                                      AND origin.type = :type_id""",
                                 {'suite_id': osuite_id, 'originsuite_id': originosuite_id,
                                  'component_id': component_id, 'type_id': type_id})
            for i in q.fetchall():
                package = i[0]
                if not packages.has_key(package) or packages[package]:
                    if i[4] and (i[1] != i[4] or i[2] != i[5] or i[3] != i[6]):
                        Logger.log(["syncing override", osuite, component,
                            otype, package, priorities[i[4]], sections[i[5]],
                            i[6], priorities[i[1]], sections[i[2]], i[3]])
                        if not Options["No-Action"]:
                            session.execute("""UPDATE override
                                                  SET priority = :priority_id,
                                                      section = :section_id,
                                                      maintainer = :maintainer
                                                WHERE package = :package
                                                  AND suite = :suite_id
                                                  AND component = :component_id
                                                  AND type = :type_id""",
                                            {'priority_id': i[1], 'section_id': i[2],
                                             'maintainer': i[3], 'package': package,
                                             'suite_id': osuite_id, 'component_id': component_id,
                                             'type_id': type_id})
                    continue
                # we can copy
                packages[package] = 1
                Logger.log(["copying missing override", osuite, component,
                    otype, package, priorities[i[1]], sections[i[2]], i[3]])
                if not Options["No-Action"]:
                    session.execute("""INSERT INTO override (package, suite, component,
                                                             priority, section, type, maintainer)
                                            VALUES (:package, :suite_id, :component_id,
                                                    :priority_id, :section_id, :type_id, :maintainer)""",
                                    {'package': package, 'suite_id': osuite_id,
                                     'component_id': component_id, 'priority_id': i[1],
                                     'section_id': i[2], 'type_id': type_id, 'maintainer': i[3]})

        for package, hasoverride in packages.items():
            if not hasoverride:
                utils.warn("%s has no override!" % package)

    session.commit()
    sys.stdout.flush()


################################################################################

def main ():
    global Logger, Options, sections, priorities

    cnf = Config()

    Arguments = [('h',"help","Check-Overrides::Options::Help"),
                 ('n',"no-action", "Check-Overrides::Options::No-Action")]
    for i in [ "help", "no-action" ]:
        if not cnf.has_key("Check-Overrides::Options::%s" % (i)):
            cnf["Check-Overrides::Options::%s" % (i)] = ""
    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Check-Overrides::Options")

    if Options["Help"]:
        usage()

    session = DBConn().session()

    # init sections, priorities:

    # We need forward and reverse
    sections = get_sections(session)
    for name, entry in sections.items():
        sections[entry] = name

    priorities = get_priorities(session)
    for name, entry in priorities.items():
        priorities[entry] = name

    if not Options["No-Action"]:
        Logger = daklog.Logger("check-overrides")
    else:
        Logger = daklog.Logger("check-overrides", 1)

    for suite in session.query(Suite).filter(Suite.overrideprocess==True):
        originosuite = None
        originremark = ''

        if suite.overrideorigin is not None:
            originosuite = get_suite(suite.overrideorigin, session)
            if originosuite is None:
                utils.fubar("%s has an override origin suite of %s but it doesn't exist!" % (suite.suite_name, suite.overrideorigin))
            originosuite = originosuite.suite_name
            originremark = " taking missing from %s" % originosuite

        print "Processing %s%s..." % (suite.suite_name, originremark)

        # Get a list of all suites that use the override file of 'suite.suite_name' as
        # well as the suite
        ocodename = suite.codename
        suiteids = [x.suite_id for x in session.query(Suite).filter(Suite.overridecodename == ocodename).all()]
        if suite.suite_id not in suiteids:
            suiteids.append(suite.suite_id)

        if len(suiteids) < 1:
            utils.fubar("Couldn't find id's of all suites: %s" % suiteids)

        for component in session.query(Component).all():
            # It is crucial for the dsc override creation based on binary
            # overrides that 'dsc' goes first
            component_name = component.component_name
            otypes = ['dsc']
            for ot in session.query(OverrideType):
                if ot.overridetype == 'dsc':
                    continue
                otypes.append(ot.overridetype)

            for otype in otypes:
                print "Processing %s [%s - %s]" \
                    % (suite.suite_name, component_name, otype)
                sys.stdout.flush()
                process(suite.suite_name, suiteids, originosuite, component_name, otype, session)

    Logger.close()

################################################################################

if __name__ == '__main__':
    main()
