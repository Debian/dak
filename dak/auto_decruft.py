#!/usr/bin/env python

"""
Check for obsolete binary packages

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000-2006 James Troup <james@nocrew.org>
@copyright: 2009      Torsten Werner <twerner@debian.org>
@copyright: 2015      Niels Thykier <niels@thykier.net>
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

# | priviledged positions? What privilege? The honour of working harder
# | than most people for absolutely no recognition?
#
# Manoj Srivastava <srivasta@debian.org> in <87lln8aqfm.fsf@glaurung.internal.golden-gryphon.com>

################################################################################

import sys
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils
from daklib.cruft import *
from daklib.rm import remove

################################################################################

def usage(exit_code=0):
    print """Usage: dak cruft-report
Check for obsolete or duplicated packages.

  -h, --help                show this help and exit.
  -n, --dry-run             don't do anything, just show what would have been done
  -s, --suite=SUITE         check suite SUITE."""
    sys.exit(exit_code)

################################################################################

def remove_sourceless_cruft(suite_name, suite_id, session, dryrun):
    """Remove binaries without a source

    @type suite_name: string
    @param suite_name: The name of the suite to remove from

    @type suite_id: int
    @param suite_id: The id of the suite donated by suite_name

    @type session: SQLA Session
    @param session: The database session in use

    @type dryrun: bool
    @param dryrun: If True, just to print the actions rather than actually doing them
    """""
    global Options
    rows = query_without_source(suite_id, session)
    arch_all_id = get_architecture('all', session=session)


    message = '[auto-cruft] no longer built from source and no reverse dependencies'
    for row in rows:
        package = row[0]
        if utils.check_reverse_depends([package], suite_name, [], session, cruft=True, quiet=True):
            continue

        if dryrun:
            # Embed the -R just in case someone wants to run it manually later
            print 'Would do:    dak rm -m "%s" -s %s -a all -p -R -b %s' % \
                  (message, suite_name, package)
        else:
            q = session.execute("""
            SELECT b.package, b.version, a.arch_string, b.id
            FROM binaries b
                JOIN bin_associations ba ON b.id = ba.bin
                JOIN architecture a ON b.architecture = a.id
                JOIN suite su ON ba.suite = su.id
            WHERE a.id = :arch_all_id AND b.package = :package AND su.id = :suite_id
            """, {arch_all_id: arch_all_id, package: package, suite_id: suite_id})
            remove(session, message, [suite_name], list(q), partial=True, whoami="DAK's auto-decrufter")


def removeNBS(suite_name, suite_id, session, dryrun):
    """Remove binaries no longer built

    @type suite_name: string
    @param suite_name: The name of the suite to remove from

    @type suite_id: int
    @param suite_id: The id of the suite donated by suite_name

    @type session: SQLA Session
    @param session: The database session in use

    @type dryrun: bool
    @param dryrun: If True, just to print the actions rather than actually doing them
    """""
    global Options
    rows = queryNBS(suite_id, session)
    arch2ids = {}
    for row in rows:
        (pkg_list, arch_list, source, _) = row
        if utils.check_reverse_depends(pkg_list, suite_name, arch_list, session, cruft=True, quiet=True):
            continue
        arch_string = ','.join(arch_list)
        message = '[auto-cruft] NBS (no longer built by %s and had no reverse dependencies)' % source

        if dryrun:
            # Embed the -R just in case someone wants to run it manually later
            pkg_string = ' '.join(pkg_list)
            print 'Would do:    dak rm -m "%s" -s %s -a %s -p -R -b %s' % \
                  (message, suite_name, arch_string, pkg_string)
        else:
            for architecture in arch_list:
                if architecture in arch2ids:
                    arch2ids[architecture] = utils.get_architecture(architecture, session=session)
            arch_ids = ", ".join(arch2ids[architecture] for architecture in arch_list)
            pkg_db_set = ", ".join('"%s"' % package for package in pkg_list)
            # TODO: Fix this properly to remove the remaining non-bind arguments
            q = session.execute("""
            SELECT b.package, b.version, a.arch_string, b.id
            FROM binaries b
                JOIN bin_associations ba ON b.id = ba.bin
                JOIN architecture a ON b.architecture = a.id
                JOIN suite su ON ba.suite = su.id
            WHERE a.id IN (%s) AND b.package IN (%s) AND su.id = :suite_id
            """ % (arch_ids, pkg_db_set), { suite_id: suite_id})
            remove(session, message, [suite_name], list(q), partial=True, whoami="DAK's auto-decrufter")

################################################################################

def main ():
    global Options
    cnf = Config()

    Arguments = [('h',"help","Auto-Decruft::Options::Help"),
                 ('n',"dry-run","Auto-Decruft::Options::Dry-Run"),
                 ('s',"suite","Auto-Decruft::Options::Suite","HasArg")]
    for i in ["help", "Dry-Run"]:
        if not cnf.has_key("Auto-Decruft::Options::%s" % (i)):
            cnf["Auto-Decruft::Options::%s" % (i)] = ""

    cnf["Auto-Decruft::Options::Suite"] = cnf.get("Dinstall::DefaultSuite", "unstable")

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.subtree("Auto-Decruft::Options")
    if Options["Help"]:
        usage()

    dryrun = False
    if Options["Dry-Run"]:
        dryrun = True

    session = DBConn().session()

    suite = get_suite(Options["Suite"].lower(), session)
    if not suite:
        utils.fubar("Cannot find suite %s" % Options["Suite"].lower())

    suite_id = suite.suite_id
    suite_name = suite.suite_name.lower()

    remove_sourceless_cruft(suite_name, suite_id, session, dryrun)
    removeNBS(suite_name, suite_id, session, dryrun)

################################################################################

if __name__ == '__main__':
    main()
