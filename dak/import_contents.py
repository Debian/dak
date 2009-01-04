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
has_opened_temp_file_lists = False
content_path_file = ""
content_name_file = ""
content_file_cache = {}
content_name_cache = {}
content_path_cache = {}

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
    global content_path_file, content_name_file, has_opened_temp_file_lists

    # have we seen this contents before?
    if content_file_cache.has_key(fullpath):
        return

    # split the path into basename, and pathname
    (path, file)  = os.path.split(fullpath)

    # Due to performance reasons, we need to get the entire filelists table
    # sorted first before we can do assiocation tables.
    if has_opened_temp_file_lists == False:
        content_path_file = open("/tmp/content_file_path.tmp", "w")
        content_name_file = open("/tmp/content_name_path.tmp", "w")
        has_opened_temp_file_lists = True

    if not content_path_cache.has_key(path):
        content_path_file.write("DEFAULT %s\n" % (path))
        content_path_cache[path] = 1

    if not content_name_cache.has_key(file):
        content_name_file.write("DEFAULT %s\n" % (file))
        content_name_cache[file] = 1
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

        q = projectB.query("SELECT s.architecture, a.arch_string FROM suite_architectures s JOIN architecture a ON (s.architecture=a.id) WHERE suite = '%d'" % suite_id)

        arch_list = [ ]
        for r in q.getresult():
            if r[1] != "source" and r[1] != "all":
                arch_list.append((r[0], r[1]))

        arch_all_id = database.get_architecture_id("all")

        for arch in arch_list:
            print "Processing %s/%s" % (s, arch[1])
            arch_id = database.get_architecture_id(arch[1])

            try:
                f = gzip.open(Cnf["Dir::Root"] + "dists/%s/Contents-%s.gz" % (s, arch[1]), "r")

            except:
                print "Unable to open dists/%s/Contents-%s.gz" % (s, arch[1])
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
                        print "Unable to find end of Contents-%s.gz header!" % ( arch[1])
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

    content_name_file.close()
    content_path_file.close()

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
