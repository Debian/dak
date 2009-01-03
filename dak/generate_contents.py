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
import gzip, apt_pkg
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

def generate_contents(suites):
    global projectB, Cnf
    # Ok, the contents information is in the database

    # We need to work and get the contents, and print it out on a per
    # architectual basis

    # Read in the contents file header
    header = False
    if Cnf.has_key("Generate-Contents::Header"):
        h = open(Cnf["Generate-Contents::Header"], "r")
        header = h.read()
        h.close()

    # Get our suites, and the architectures
    for s in [i.lower() for i in suites]:
        suite_id = database.get_suite_id(s)

        q = projectB.query("SELECT s.architecture, a.arch_string FROM suite_architectures s JOIN architecture a ON (s.architecture=a.id) WHERE suite = '%d'" % suite_id)

        arch_list = [ ]
        for r in q.getresult():
            if r[1] != "source" and r[1] != "all":
                arch_list.append((r[0], r[1]))

        arch_all_id = database.get_architecture_id("all")

        # Time for the query from hell. Essentially, we need to get the assiocations, the filenames, the paths,
        # and all that fun stuff from the database.

        for arch_id in arch_list:
            q = projectB.query("""SELECT p.path||'/'||n.file, comma_separated_list(s.section||'/'||b.package) FROM content_associations c JOIN content_file_paths p ON (c.filepath=p.id) JOIN content_file_names n ON (c.filename=n.id) JOIN binaries b ON (b.id=c.binary_pkg) JOIN bin_associations ba ON (b.id=ba.bin) JOIN override o ON (o.package=b.package) JOIN section s ON (s.id=o.section) WHERE (b.architecture = '%d' OR b.architecture = '%d') AND ba.suite = '%d' AND b.type = 'deb' GROUP BY (p.path||'/'||n.file)""" % (arch_id[0], arch_all_id, suite_id))

            f = gzip.open(Cnf["Dir::Root"] + "dists/%s/Contents-%s.gz" % (s, arch_id[1]), "w")

            if header:
                f.write(header)

            for contents in q.getresult():
                f.write(contents[0] + "\t\t\t" + contents[-1] + "\n")

            f.close()

        # The MORE fun part. Ok, udebs need their own contents files, udeb, and udeb-nf (not-free)
        # This is HORRIBLY debian specific :-/
        # First off, udeb

        section_id = database.get_section_id('debian-installer') # all udebs should be here)

        if section_id != -1:
            q = projectB.query("""SELECT p.path||'/'||n.file, comma_separated_list(s.section||'/'||b.package) FROM content_associations c JOIN content_file_paths p ON (c.filepath=p.id) JOIN content_file_names n ON (c.filename=n.id) JOIN binaries b ON (b.id=c.binary_pkg) JOIN bin_associations ba ON (b.id=ba.bin) JOIN override o ON (o.package=b.package) JOIN section s ON (s.id=o.section) WHERE s.id = '%d' AND ba.suite = '%d' AND b.type = 'udeb' GROUP BY (p.path||'/'||n.file)""" % (section_id, suite_id))

            f = gzip.open(Cnf["Dir::Root"] + "dists/%s/Contents-udeb.gz" % (s), "w")

            if header:
                f.write(header)

            for contents in q.getresult():
                f.write(contents[0] + "\t\t\t" + contents[-1] + "\n")

            f.close()

        # Once more, with non-free
        section_id = database.get_section_id('non-free/debian-installer') # all udebs should be here)

        if section_id != -1:
            q = projectB.query("""SELECT p.path||'/'||n.file, comma_separated_list(s.section||'/'||b.package) FROM content_associations c JOIN content_file_paths p ON (c.filepath=p.id) JOIN content_file_names n ON (c.filename=n.id) JOIN binaries b ON (b.id=c.binary_pkg) JOIN bin_associations ba ON (b.id=ba.bin) JOIN override o ON (o.package=b.package) JOIN section s ON (s.id=o.section) WHERE s.id = '%d' AND ba.suite = '%d' AND b.type = 'udeb' GROUP BY (p.path||'/'||n.file)""" % (section_id, suite_id))

            f = gzip.open(Cnf["Dir::Root"] + "dists/%s/Contents-udeb-nf.gz" % (s), "w")

            if header:
                f.write(header)

            for contents in q.getresult():
                f.write(contents[0] + "\t\t\t" + contents[-1] + "\n")

            f.close()

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
