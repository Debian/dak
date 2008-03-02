#!/usr/bin/env python

# Check the release managers transition file for correctness and outdated transitions
# Copyright (C) 2008 Joerg Jaspert <joerg@debian.org>

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

# <elmo> if klecker.d.o died, I swear to god, I'm going to migrate to gentoo.

################################################################################

import os, sys
import apt_pkg
import daklib.database
import daklib.utils

from syck import *

# Globals
Cnf = None
Options = None
projectB = None

################################################################################

def init():
    global Cnf, Options, projectB

    apt_pkg.init()

    Cnf = daklib.utils.get_conf()

    Arguments = [('h',"help","Dinstall::Options::Help"),
                 ('n',"no-action","Dinstall::Options::No-Action")]

    for i in ["help", "no-action"]:
        Cnf["Dinstall::Options::%s" % (i)] = ""

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)
    
    Options = Cnf.SubTree("Dinstall::Options")

    if Options["Help"]:
        usage()

################################################################################

def usage (exit_code=0):
    print """Usage: check_transitions [OPTION]...
  -h, --help                show this help and exit.
  -n, --no-action           don't do anything"""
    sys.exit(exit_code)

################################################################################

def main():
    global Cnf
    # Only check if there is a file defined (and existant) with checks. It's a little bit
    # specific to Debian, not much use for others, so return early there.
    if not Cnf.has_key("Dinstall::Reject::ReleaseTransitions") or not os.path.exists("%s" % (Cnf["Dinstall::Reject::ReleaseTransitions"])):
        daklib.utils.warn("Dinstall::Reject::ReleaseTransitions not defined or file %s not existant." %
                          (Cnf["Dinstall::Reject::ReleaseTransitions"]))
        sys.exit(1)
    
    # Parse the yaml file
    sourcefile = file(Cnf["Dinstall::Reject::ReleaseTransitions"], 'r')
    try:
        transitions = load(sourcefile)
    except error, msg:
        # This shouldn't happen, the release team has a wrapper to check the file, but better
        # safe then sorry
        daklib.utils.warn("Not checking transitions, the transitions file is broken: %s." % (msg))
        sys.exit(2)

    to_dump = 0

    # Now look through all defined transitions
    for trans in transition:
        t = transition[trans]
        source = t["source"]
        new_vers = t["new"]

        # Will be None if nothing is in testing.
        curvers = daklib.database.get_testing_version(source)

        print """
        Looking at transition: %s
         Source:      %s
         New Version: %s
         Responsible: %s
         Reason:      %s
         Blocked Packages (total: %d):
        """ % (trans, source, new_vers, t["rm"], t["reason"])
        for i in t["packages"]:
            print " %s" % (i)

        if curvers and apt_pkg.VersionCompare(new_vers, curvers) == 1:
            # This is still valid, the current version in database is older than
            # the new version we wait for
            print "This transition is still ongoing"
        else:
            print "This transition is over, the target package reached testing, removing"
            print "%s wanted version: %s, has %s" % (source, new_vers, curvers)
            del transition[trans]
            to_dump = 1
        print "-------------------------------------------------------------------------"

    if to_dump:
        destfile = file(Cnf["Dinstall::Reject::ReleaseTransitions"], 'w')
        dump(transition, destfile)

################################################################################

if __name__ == '__main__':
    main()
