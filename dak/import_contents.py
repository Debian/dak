#!/usr/bin/env python
# Import contents files

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
################################################################################

################################################################################

import sys, os, popen2, tempfile, stat, time, pg
import re, gzip, apt_pkg
from daklib import database, utils
from daklib.dak_exceptions import *

################################################################################

Cnf = None
projectB = None
out = None
AptCnf = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak import-contents
Import Contents files

 -h, --help                 show this help and exit
 -s, --suite=SUITE         only write file lists for this suite
"""
    sys.exit(exit_code)

################################################################################

def import_contents(suites):
    global projectB, Cnf

    # Start transaction
    projectB.query("BEGIN WORK")

    # Needed to make sure postgreSQL doesn't freak out on some of the data
    projectB.query("SET CLIENT_ENCODING TO 'LATIN1'")

    # Get our suites, and the architectures
    for s in suites:
        suite_id = database.get_suite_id(s)

        q = projectB.query("SELECT s.architecture, a.arch_string FROM suite_architectures s JOIN architecture a ON (s.architecture=a.id) WHERE suite = '%d'" % suite_id)

        arch_list = [ ]
        for r in q.getresult():
            if r[1] != "source" and r[1] != "all":
                arch_list.append((r[0], r[1]))

        arch_all_id = database.get_architecture_id("all")

        for arch in arch_list:
            print "Processing %s/%s" % (s, arch[1])
            arch_id = database.get_architecture_id(arch[1])
            f = gzip.open(Cnf["Dir::Root"] + "dists/%s/Contents-%s.gz" % (s, arch[1]), "r")

            # Get line count
            lines = f.readlines()
            num_of_lines = len(lines)

            # Ok, the file cursor is at the first entry, now comes the fun 'lets parse' bit
            lines_processed = 0
            found_header = False

            for line in lines:
                if found_header == False:
                    if not line:
                        print "Unable to find end of Contents-%s.gz header!" % ( arch[1])
                        sys.exit(255)

                    lines_processed += 1
                    p = re.compile('^FILE')
                    if p.match(line):
                        found_header = True
                    continue

                # The format is simple enough, *filename*, *section/package1,section/package2,etc*
                # Each file appears once per Contents file, so first, use some regex match
                # to split the two bits

                # Print out progress bar
                print "\rProcessed %d lines of %d (%%%.2f)" % (lines_processed, num_of_lines, (float(lines_processed)/num_of_lines)),

                # regex lifted from packages.d.o code
                p = re.compile('^(.+?)\s+(\S+)$')
                matchs = p.findall(line)
                filename = matchs[0][0]
                packages = matchs[0][1].split(',')

                # Iterate through each file's packages
                for package in packages:
                    p = re.compile('(\S+)/(\S+)$')
                    matchs = p.findall(package)

                    # Needed since the DB is unicode, and these files
                    # are ASCII
                    section_name = matchs[0][0]
                    package_name = matchs[0][1]

                    section_id = database.get_section_id(section_name)
                    package_id = database.get_latest_binary_version_id(package_name, section_id, suite_id, arch_id)

                    if package_id == None:
                        # Likely got an arch all package
                        package_id = database.get_latest_binary_version_id(package_name, section_id, suite_id, arch_all_id)

                    database.insert_content_path(package_id, filename)

                lines_processed += 1
            f.close()

    # Commit work
    print "Committing to database ..."
    projectB.query("COMMIT")

################################################################################

def main ():
    global Cnf, projectB, out
    out = sys.stdout

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Import-Contents::Options::Help"),
                 ('s',"suite","Import-Contents::Options::Suite","HasArg"),
                ]

    for i in [ "help", "suite" ]:
        if not Cnf.has_key("Import-Contents::Options::%s" % (i)):
            Cnf["Import-Contents::Options::%s" % (i)] = ""

    suites = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Import-Contents::Options")

    if Options["Help"]:
        usage()

    if Options["Suite"]:
        suites = utils.split_args(Options["Suite"])
    else:
        suites = Cnf.SubTree("Suite").List()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    import_contents(suites)

#######################################################################################

if __name__ == '__main__':
    main()
