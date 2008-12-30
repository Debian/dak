#!/usr/bin/env python
# Create all the contents files

# Copyright (C) 2008, 2009 Michael Casadevall <mcasadevall@debian.org>

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
# <Ganneff> there is the idea to slowly replace contents files
# <Ganneff> with a new generation of such files.
# <Ganneff> having more info.
# <Ganneff> of course that wont help for now where we need to generate them :)
################################################################################

################################################################################

import sys, os, popen2, tempfile, stat, time, pg
import apt_pkg
from daklib import database, utils
from daklib.dak_exceptions import *

################################################################################

Cnf = None
projectB = None
out = None
AptCnf = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak generate-contents
Generate Contents files

 -h, --help                 show this help and exit
 -s, --suite=SUITE         only write file lists for this suite
"""
    sys.exit(exit_code)

################################################################################

def handle_dup_files(file_list):
    # Sort the list, and then handle finding dups in the filenames key

    # Walk the list, seeing if the current entry and the next one are the same
    # and if so, join them together


    return file_list

################################################################################

def generate_contents(suites):
    global projectB, Cnf
    # Ok, the contents information is in the database

    # We need to work and get the contents, and print it out on a per
    # architectual basis

    # Get our suites, and the architectures
    for s in suites:
        suite_id = database.get_suite_id(s)

        q = projectB.query("SELECT architecture FROM suite_architectures WHERE suite = '%d'" % suite_id)

        arch_list = [ ]
        for r in q.getresult():
            arch_list.append(r[0])

        arch_all_id = database.get_architecture_id("all")

       # Got the arch all packages, now we need to get the arch dependent packages
       # attach the arch all, stick them together, and write out the result

        for arch_id in arch_list:
            print "SELECT b.package, c.file, s.section FROM contents c JOIN binaries b ON (b.id=c.binary_pkg) JOIN bin_associations ba ON (b.id=ba.bin) JOIN override o ON (o.package=b.package) JOIN section s ON (s.id=o.section) WHERE (b.architecture = '%d' OR b.architecture = '%d') AND ba.suite = '%d'" % (arch_id, arch_all_id, suite_id)
            q = projectB.query("SELECT b.package, c.file, s.section FROM contents c JOIN binaries b ON (b.id=c.binary_pkg) JOIN bin_associations ba ON (b.id=ba.bin) JOIN override o ON (o.package=b.package) JOIN section s ON (s.id=o.section) WHERE (b.architecture = '%d' OR b.architecture = '%d') AND ba.suite = '%d'" % (arch_id, arch_all_id, suite_id))
            # We need to copy the arch_all packages table into arch packages

            # This is for the corner case of arch dependent packages colliding
            # with arch all packages only on some architectures.
            # Ugly, I know ...

            arch_packages = []
            for r in q.getresult():
                arch_packages.append((r[1], (r[2] + '/' + r[0])))

            arch_packages = handle_dup_files(arch_packages)

            #for contents in arch_packages:
                #print contents[0] + '\t\t\t\t' + contents[1]

################################################################################

def main ():
    global Cnf, projectB, out
    out = sys.stdout

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Generate-Contents::Options::Help"),
                 ('s',"suite","Generate-Contents::Options::Suite","HasArg"),
                ]
    for i in [ "help", "suite" ]:
        if not Cnf.has_key("Generate-Contents::Options::%s" % (i)):
            Cnf["Generate-Contents::Options::%s" % (i)] = ""

    suites = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Generate-Contents::Options")

    if Options["Help"]:
        usage()

    if Options["Suite"]:
        suites = utils.split_args(Options["Suite"])
    else:
        suites = Cnf.SubTree("Suite").List()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    generate_contents(suites)

#######################################################################################

if __name__ == '__main__':
    main()
