#!/usr/bin/env python2.4
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
has_opened_temp_file_lists = False
content_path_file = ""
content_name_file = ""
content_file_cache = set([])
content_name_cache = set([])
content_path_cache = set([])

################################################################################

def usage (exit_code=0):
    print """Usage: dak import-contents
Import Contents files

 -h, --help                 show this help and exit
 -s, --suite=SUITE         only write file lists for this suite
"""
    sys.exit(exit_code)

################################################################################

def cache_content_path(fullpath):
    global content_file_cache, contents_name_cache, content_path_cache

    # have we seen this contents before?
    if fullpath in content_file_cache:
        return

    # Add the new key to the cache
    content_file_cache.add(fullpath)

    # split the path into basename, and pathname
    (path, file)  = os.path.split(fullpath)

    # Due to performance reasons, we need to get the entire filelists table
    # sorted first before we can do assiocation tables.
    if path not in content_path_cache:
        content_path_cache.add(path)

    if file not in content_name_cache:
        content_name_cache.add(file)

    return

################################################################################

def import_contents(suites):
    global projectB, Cnf

    # Start transaction
    projectB.query("BEGIN WORK")

    # Needed to make sure postgreSQL doesn't freak out on some of the data
    projectB.query("SET CLIENT_ENCODING TO 'LATIN1'")

    # Precache everything
    #print "Precaching binary information, this will take a few moments ..."
    #database.preload_binary_id_cache()

    # Prep regexs
    line_regex = re.compile(r'^(.+?)\s+(\S+)$')
    pkg_regex = re.compile(r'(\S+)/(\S+)$')
    file_regex = re.compile('^FILE')

    # Get our suites, and the architectures
    for s in suites:
        suite_id = database.get_suite_id(s)

        arch_list = [ ]
        for r in Cnf.ValueList("Suite::%s::Architectures" % (s)):
            if r != "source" and r != "all":
                arch_list.append(r)

        arch_all_id = database.get_architecture_id("all")

        for arch in arch_list:
            print "Processing %s/%s" % (s, arch)
            arch_id = database.get_architecture_id(arch)

            try:
                f = gzip.open(Cnf["Dir::Root"] + "dists/%s/Contents-%s.gz" % (s, arch), "r")

            except:
                print "Unable to open dists/%s/Contents-%s.gz" % (s, arch)
                print "Skipping ..."
                continue

            # Get line count
            lines = f.readlines()
            num_of_lines = len(lines)

            # Ok, the file cursor is at the first entry, now comes the fun 'lets parse' bit
            lines_processed = 0
            found_header = False

            for line in lines:
                if found_header == False:
                    if not line:
                        print "Unable to find end of Contents-%s.gz header!" % (arch)
                        sys.exit(255)

                    lines_processed += 1
                    if file_regex.match(line):
                        found_header = True
                    continue

                # The format is simple enough, *filename*, *section/package1,section/package2,etc*
                # Each file appears once per Contents file, so first, use some regex match
                # to split the two bits

                # Print out progress bar
                print "\rProcessed %d lines of %d (%%%.2f)" % (lines_processed, num_of_lines, ((float(lines_processed)/num_of_lines)*100)),

                # regex lifted from packages.d.o code
                matchs = line_regex.findall(line)
                filename = matchs[0][0]
                packages = matchs[0][1].split(',')


                cache_content_path(filename)

                # Iterate through each file's packages
                #for package in packages:
                #    matchs = pkg_regex.findall(package)

                    # Needed since the DB is unicode, and these files
                    # are ASCII
                #    section_name = matchs[0][0]
                #    package_name = matchs[0][1]

                    #section_id = database.get_section_id(section_name)
                    #package_id = database.get_latest_binary_version_id(package_name, section_id, suite_id, arch_id)

               #     if package_id == None:
                        # This can happen if the Contents file refers to a non-existant package
                        # it seems Contents sometimes can be stale due to use of caches (i.e., hurd-i386)
                        # hurd-i386 was removed from the archive, but its Contents file still exists
                        # and is seemingly still updated. The sane thing to do is skip it and continue
               #         continue


                lines_processed += 1

            print "" # newline since the Progress bar doesn't print one
            f.close()

    # Commit work

    print "Committing to database ..."
    projectB.query("COPY content_file_names (file) FROM STDIN")

    for line in content_name_cache:
        projectB.putline("%s\n" % (line))

    projectB.endcopy()

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
