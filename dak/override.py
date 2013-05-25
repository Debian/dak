#!/usr/bin/env python

""" Microscopic modification and query tool for overrides in projectb """
# Copyright (C) 2004, 2006  Daniel Silverstone <dsilvers@digital-scurf.org>

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
## So line up your soldiers and she'll shoot them all down
## Coz Alisha Rules The World
## You think you found a dream, then it shatters and it seems,
## That Alisha Rules The World
################################################################################

import os
import sys
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib import daklog
from daklib import utils

################################################################################

# Shamelessly stolen from 'dak rm'. Should probably end up in utils.py
def game_over():
    answer = utils.our_raw_input("Continue (y/N)? ").lower()
    if answer != "y":
        print "Aborted."
        sys.exit(1)


def usage (exit_code=0):
    print """Usage: dak override [OPTIONS] package [section] [priority]
Make microchanges or microqueries of the binary overrides

  -h, --help                 show this help and exit
  -c, --check                check override compliance
  -d, --done=BUG#            send priority/section change as closure to bug#
  -n, --no-action            don't do anything
  -s, --suite                specify the suite to use
"""
    sys.exit(exit_code)

def check_override_compliance(package, priority, archive_path, suite_name, cnf, session):
    print "Checking compliance with related overrides..."

    depends = set()
    rdepends = set()
    components = get_component_names(session)
    arches = set([x.arch_string for x in get_suite_architectures(suite_name)])
    arches -= set(["source", "all"])
    for arch in arches:
        for component in components:
            Packages = utils.get_packages_from_ftp(archive_path, suite_name, component, arch)
            while Packages.step():
                package_name = Packages.section.find("Package")
                dep_list = Packages.section.find("Depends")
                if dep_list:
                    if package_name == package:
                        for d in apt_pkg.parse_depends(dep_list):
                            for i in d:
                                depends.add(i[0])
                    else:
                        for d in apt_pkg.parse_depends(dep_list):
                            for i in d:
                                if i[0] == package:
                                    rdepends.add(package_name)

    query = """SELECT o.package, p.level, p.priority
               FROM override o
               JOIN suite s ON s.id = o.suite
               JOIN priority p ON p.id = o.priority
               WHERE s.suite_name = '%s'
               AND o.package in ('%s')""" \
               % (suite_name, "', '".join(depends.union(rdepends)))
    packages = session.execute(query)

    excuses = []
    for p in packages:
        if p[0] == package or not p[1]:
            continue
        if p[0] in depends:
            if priority.level < p[1]:
                excuses.append("%s would have priority %s, its dependency %s has priority %s" \
                      % (package, priority.priority, p[0], p[2]))
        if p[0] in rdepends:
            if priority.level > p[1]:
                excuses.append("%s would have priority %s, its reverse dependency %s has priority %s" \
                      % (package, priority.priority, p[0], p[2]))

    if excuses:
        for ex in excuses:
            print ex
    else:
        print "Proposed override change complies with Debian Policy"

def main ():
    cnf = Config()

    Arguments = [('h',"help","Override::Options::Help"),
                 ('c',"check","Override::Options::Check"),
                 ('d',"done","Override::Options::Done", "HasArg"),
                 ('n',"no-action","Override::Options::No-Action"),
                 ('s',"suite","Override::Options::Suite", "HasArg"),
                 ]
    for i in ["help", "check", "no-action"]:
        if not cnf.has_key("Override::Options::%s" % (i)):
            cnf["Override::Options::%s" % (i)] = ""
    if not cnf.has_key("Override::Options::Suite"):
        cnf["Override::Options::Suite"] = "unstable"

    arguments = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Override::Options")

    if Options["Help"]:
        usage()

    session = DBConn().session()

    if not arguments:
        utils.fubar("package name is a required argument.")

    package = arguments.pop(0)
    suite_name = Options["Suite"]
    if arguments and len(arguments) > 2:
        utils.fubar("Too many arguments")

    suite = get_suite(suite_name, session)
    if suite is None:
        utils.fubar("Unknown suite '{0}'".format(suite_name))

    if arguments and len(arguments) == 1:
        # Determine if the argument is a priority or a section...
        arg = arguments.pop()
        q = session.execute("""
        SELECT ( SELECT COUNT(*) FROM section WHERE section = :arg ) AS secs,
               ( SELECT COUNT(*) FROM priority WHERE priority = :arg ) AS prios
               """, {'arg': arg})
        r = q.fetchall()
        if r[0][0] == 1:
            arguments = (arg, ".")
        elif r[0][1] == 1:
            arguments = (".", arg)
        else:
            utils.fubar("%s is not a valid section or priority" % (arg))

    # Retrieve current section/priority...
    oldsection, oldsourcesection, oldpriority = None, None, None
    for packagetype in ['source', 'binary']:
        eqdsc = '!='
        if packagetype == 'source':
            eqdsc = '='
        q = session.execute("""
    SELECT priority.priority AS prio, section.section AS sect, override_type.type AS type
      FROM override, priority, section, suite, override_type
     WHERE override.priority = priority.id
       AND override.type = override_type.id
       AND override_type.type %s 'dsc'
       AND override.section = section.id
       AND override.package = :package
       AND override.suite = suite.id
       AND suite.suite_name = :suite_name
        """ % (eqdsc), {'package': package, 'suite_name': suite_name})

        if q.rowcount == 0:
            continue
        if q.rowcount > 1:
            utils.fubar("%s is ambiguous. Matches %d packages" % (package,q.rowcount))

        r = q.fetchone()
        if packagetype == 'binary':
            oldsection = r[1]
            oldpriority = r[0]
        else:
            oldsourcesection = r[1]
            oldpriority = 'source'

    if not oldpriority and not oldsourcesection:
        utils.fubar("Unable to find package %s" % (package))

    if oldsection and oldsourcesection and oldsection != oldsourcesection:
        # When setting overrides, both source & binary will become the same section
        utils.warn("Source is in section '%s' instead of '%s'" % (oldsourcesection, oldsection))

    if not oldsection:
        oldsection = oldsourcesection

    if not arguments:
        print "%s is in section '%s' at priority '%s'" % (
            package, oldsection, oldpriority)
        sys.exit(0)

    # At this point, we have a new section and priority... check they're valid...
    newsection, newpriority = arguments

    if newsection == ".":
        newsection = oldsection
    if newpriority == ".":
        newpriority = oldpriority

    s = get_section(newsection, session)
    if s is None:
        utils.fubar("Supplied section %s is invalid" % (newsection))
    newsecid = s.section_id

    p = get_priority(newpriority, session)
    if p is None:
        utils.fubar("Supplied priority %s is invalid" % (newpriority))
    newprioid = p.priority_id

    if newpriority == oldpriority and newsection == oldsection:
        print "I: Doing nothing"
        sys.exit(0)

    if oldpriority == 'source' and newpriority != 'source':
        utils.fubar("Trying to change priority of a source-only package")

    if Options["Check"] and newpriority != oldpriority:
        check_override_compliance(package, p, suite.archive.path, suite_name, cnf, session)

    # If we're in no-action mode
    if Options["No-Action"]:
        if newpriority != oldpriority:
            print "I: Would change priority from %s to %s" % (oldpriority,newpriority)
        if newsection != oldsection:
            print "I: Would change section from %s to %s" % (oldsection,newsection)
        if Options.has_key("Done"):
            print "I: Would also close bug(s): %s" % (Options["Done"])

        sys.exit(0)

    if newpriority != oldpriority:
        print "I: Will change priority from %s to %s" % (oldpriority,newpriority)

    if newsection != oldsection:
        print "I: Will change section from %s to %s" % (oldsection,newsection)

    if not Options.has_key("Done"):
        pass
        #utils.warn("No bugs to close have been specified. Noone will know you have done this.")
    else:
        print "I: Will close bug(s): %s" % (Options["Done"])

    game_over()

    Logger = daklog.Logger("override")

    dsc_otype_id = get_override_type('dsc').overridetype_id

    # We're already in a transaction
    # We're in "do it" mode, we have something to do... do it
    if newpriority != oldpriority:
        session.execute("""
        UPDATE override
           SET priority = :newprioid
         WHERE package = :package
           AND override.type != :otypedsc
           AND suite = (SELECT id FROM suite WHERE suite_name = :suite_name)""",
           {'newprioid': newprioid, 'package': package,
            'otypedsc':  dsc_otype_id, 'suite_name': suite_name})

        Logger.log(["changed priority", package, oldpriority, newpriority])

    if newsection != oldsection:
        q = session.execute("""
        UPDATE override
           SET section = :newsecid
         WHERE package = :package
           AND suite = (SELECT id FROM suite WHERE suite_name = :suite_name)""",
           {'newsecid': newsecid, 'package': package,
            'suite_name': suite_name})

        Logger.log(["changed section", package, oldsection, newsection])

    session.commit()

    if Options.has_key("Done"):
        if not cnf.has_key("Dinstall::BugServer"):
            utils.warn("Asked to send Done message but Dinstall::BugServer is not configured")
            Logger.close()
            return

        Subst = {}
        Subst["__OVERRIDE_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]
        Subst["__BUG_SERVER__"] = cnf["Dinstall::BugServer"]
        bcc = []
        if cnf.find("Dinstall::Bcc") != "":
            bcc.append(cnf["Dinstall::Bcc"])
        if bcc:
            Subst["__BCC__"] = "Bcc: " + ", ".join(bcc)
        else:
            Subst["__BCC__"] = "X-Filler: 42"
        if cnf.has_key("Dinstall::PackagesServer"):
            Subst["__CC__"] = "Cc: " + package + "@" + cnf["Dinstall::PackagesServer"] + "\nX-DAK: dak override"
        else:
            Subst["__CC__"] = "X-DAK: dak override"
        Subst["__ADMIN_ADDRESS__"] = cnf["Dinstall::MyAdminAddress"]
        Subst["__DISTRO__"] = cnf["Dinstall::MyDistribution"]
        Subst["__WHOAMI__"] = utils.whoami()
        Subst["__SOURCE__"] = package

        summary = "Concerning package %s...\n" % (package)
        summary += "Operating on the %s suite\n" % (suite_name)
        if newpriority != oldpriority:
            summary += "Changed priority from %s to %s\n" % (oldpriority,newpriority)
        if newsection != oldsection:
            summary += "Changed section from %s to %s\n" % (oldsection,newsection)
        Subst["__SUMMARY__"] = summary

        template = os.path.join(cnf["Dir::Templates"], "override.bug-close")
        for bug in utils.split_args(Options["Done"]):
            Subst["__BUG_NUMBER__"] = bug
            mail_message = utils.TemplateSubst(Subst, template)
            utils.send_mail(mail_message)
            Logger.log(["closed bug", bug])

    Logger.close()

#################################################################################

if __name__ == '__main__':
    main()
