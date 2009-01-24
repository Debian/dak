#!/usr/bin/env python

# Remove obsolete .changes files from proposed-updates
# Copyright (C) 2001, 2002, 2003, 2004, 2006, 2008  James Troup <james@nocrew.org>

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

import os, pg, sys
import apt_pkg
from daklib import database
from daklib import utils
from daklib.regexes import re_isdeb, re_isadeb, re_issource, re_no_epoch

################################################################################

Cnf = None
projectB = None
Options = None
pu = {}

################################################################################

def usage (exit_code=0):
    print """Usage: dak clean-proposed-updates [OPTION] <CHANGES FILE | ADMIN FILE>[...]
Remove obsolete changes files from proposed-updates.

  -v, --verbose              be more verbose about what is being done
  -h, --help                 show this help and exit

Need either changes files or an admin.txt file with a '.joey' suffix."""
    sys.exit(exit_code)

################################################################################

def check_changes (filename):
    try:
        changes = utils.parse_changes(filename)
        files = utils.build_file_list(changes)
    except:
        utils.warn("Couldn't read changes file '%s'." % (filename))
        return
    num_files = len(files.keys())
    for f in files.keys():
        if re_isadeb.match(f):
            m = re_isdeb.match(f)
            pkg = m.group(1)
            version = m.group(2)
            arch = m.group(3)
            if Options["debug"]:
                print "BINARY: %s ==> %s_%s_%s" % (f, pkg, version, arch)
        else:
            m = re_issource.match(f)
            if m:
                pkg = m.group(1)
                version = m.group(2)
                ftype = m.group(3)
                if ftype != "dsc":
                    del files[f]
                    num_files -= 1
                    continue
                arch = "source"
                if Options["debug"]:
                    print "SOURCE: %s ==> %s_%s_%s" % (f, pkg, version, arch)
            else:
                utils.fubar("unknown type, fix me")
        if not pu.has_key(pkg):
            # FIXME
            utils.warn("%s doesn't seem to exist in %s?? (from %s [%s])" % (pkg, Options["suite"], f, filename))
            continue
        if not pu[pkg].has_key(arch):
            # FIXME
            utils.warn("%s doesn't seem to exist for %s in %s?? (from %s [%s])" % (pkg, arch, Options["suite"], f, filename))
            continue
        pu_version = re_no_epoch.sub('', pu[pkg][arch])
        if pu_version == version:
            if Options["verbose"]:
                print "%s: ok" % (f)
        else:
            if Options["verbose"]:
                print "%s: superseded, removing. [%s]" % (f, pu_version)
            del files[f]

    new_num_files = len(files.keys())
    if new_num_files == 0:
        print "%s: no files left, superseded by %s" % (filename, pu_version)
        dest = Cnf["Dir::Morgue"] + "/misc/"
        if not Options["no-action"]:
            utils.move(filename, dest)
    elif new_num_files < num_files:
        print "%s: lost files, MWAAP." % (filename)
    else:
        if Options["verbose"]:
            print "%s: ok" % (filename)

################################################################################

def check_joey (filename):
    f = utils.open_file(filename)

    cwd = os.getcwd()
    os.chdir("%s/dists/%s" % (Cnf["Dir::Root"]), Options["suite"])

    for line in f.readlines():
        line = line.rstrip()
        if line.find('install') != -1:
            split_line = line.split()
            if len(split_line) != 2:
                utils.fubar("Parse error (not exactly 2 elements): %s" % (line))
            install_type = split_line[0]
            if install_type not in [ "install", "install-u", "sync-install" ]:
                utils.fubar("Unknown install type ('%s') from: %s" % (install_type, line))
            changes_filename = split_line[1]
            if Options["debug"]:
                print "Processing %s..." % (changes_filename)
            check_changes(changes_filename)

    os.chdir(cwd)

################################################################################

def init_pu ():
    global pu

    q = projectB.query("""
SELECT b.package, b.version, a.arch_string
  FROM bin_associations ba, binaries b, suite su, architecture a
  WHERE b.id = ba.bin AND ba.suite = su.id
    AND su.suite_name = '%s' AND a.id = b.architecture
UNION SELECT s.source, s.version, 'source'
  FROM src_associations sa, source s, suite su
  WHERE s.id = sa.source AND sa.suite = su.id
    AND su.suite_name = '%s'
ORDER BY package, version, arch_string
""" % (Options["suite"], Options["suite"]))
    ql = q.getresult()
    for i in ql:
        pkg = i[0]
        version = i[1]
        arch = i[2]
        if not pu.has_key(pkg):
            pu[pkg] = {}
        pu[pkg][arch] = version

def main ():
    global Cnf, projectB, Options

    Cnf = utils.get_conf()

    Arguments = [('d', "debug", "Clean-Proposed-Updates::Options::Debug"),
                 ('v', "verbose", "Clean-Proposed-Updates::Options::Verbose"),
                 ('h', "help", "Clean-Proposed-Updates::Options::Help"),
                 ('s', "suite", "Clean-Proposed-Updates::Options::Suite", "HasArg"),
                 ('n', "no-action", "Clean-Proposed-Updates::Options::No-Action"),]
    for i in [ "debug", "verbose", "help", "no-action" ]:
        if not Cnf.has_key("Clean-Proposed-Updates::Options::%s" % (i)):
            Cnf["Clean-Proposed-Updates::Options::%s" % (i)] = ""

    # suite defaults to proposed-updates
    if not Cnf.has_key("Clean-Proposed-Updates::Options::Suite"):
        Cnf["Clean-Proposed-Updates::Options::Suite"] = "proposed-updates"

    arguments = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Clean-Proposed-Updates::Options")

    if Options["Help"]:
        usage(0)
    if not arguments:
        utils.fubar("need at least one package name as an argument.")

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    init_pu()

    for f in arguments:
        if f.endswith(".changes"):
            check_changes(f)
        elif f.endswith(".joey"):
            check_joey(f)
        else:
            utils.fubar("Unrecognised file type: '%s'." % (f))

#######################################################################################

if __name__ == '__main__':
    main()
