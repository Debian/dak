#!/usr/bin/env python

""" Dependency check proposed-updates """
# Copyright (C) 2001, 2002, 2004, 2006  James Troup <james@nocrew.org>

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

# | > amd64 is more mature than even some released architectures
# |
# | This might be true of the architecture, unfortunately it seems to be the
# | exact opposite for most of the people involved with it.
#
# <1089213290.24029.6.camel@descent.netsplit.com>

################################################################################

import sys, os
import apt_pkg, apt_inst

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils
from daklib.regexes import re_no_epoch

################################################################################

Options = None
stable = {}
stable_virtual = {}
architectures = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak check-proposed-updates [OPTION] <CHANGES FILE | DEB FILE | ADMIN FILE>[...]
(Very) Basic dependency checking for proposed-updates.

  -q, --quiet                be quieter about what is being done
  -v, --verbose              be more verbose about what is being done
  -h, --help                 show this help and exit

Need either changes files, deb files or an admin.txt file with a '.joey' suffix."""
    sys.exit(exit_code)

################################################################################

def d_test (dict, key, positive, negative):
    if not dict:
        return negative
    if dict.has_key(key):
        return positive
    else:
        return negative

################################################################################

def check_dep (depends, dep_type, check_archs, filename, files):
    pkg_unsat = 0
    for arch in check_archs:
        for parsed_dep in apt_pkg.ParseDepends(depends):
            unsat = []
            for atom in parsed_dep:
                (dep, version, constraint) = atom
                # As a real package?
                if stable.has_key(dep):
                    if stable[dep].has_key(arch):
                        if apt_pkg.CheckDep(stable[dep][arch], constraint, version):
                            if Options["debug"]:
                                print "Found %s as a real package." % (utils.pp_deps(parsed_dep))
                            unsat = 0
                            break
                # As a virtual?
                if stable_virtual.has_key(dep):
                    if stable_virtual[dep].has_key(arch):
                        if not constraint and not version:
                            if Options["debug"]:
                                print "Found %s as a virtual package." % (utils.pp_deps(parsed_dep))
                            unsat = 0
                            break
                # As part of the same .changes?
                epochless_version = re_no_epoch.sub('', version)
                dep_filename = "%s_%s_%s.deb" % (dep, epochless_version, arch)
                if files.has_key(dep_filename):
                    if Options["debug"]:
                        print "Found %s in the same upload." % (utils.pp_deps(parsed_dep))
                    unsat = 0
                    break
                # Not found...
                # [FIXME: must be a better way ... ]
                error = "%s not found. [Real: " % (utils.pp_deps(parsed_dep))
                if stable.has_key(dep):
                    if stable[dep].has_key(arch):
                        error += "%s:%s:%s" % (dep, arch, stable[dep][arch])
                    else:
                        error += "%s:-:-" % (dep)
                else:
                    error += "-:-:-"
                error += ", Virtual: "
                if stable_virtual.has_key(dep):
                    if stable_virtual[dep].has_key(arch):
                        error += "%s:%s" % (dep, arch)
                    else:
                        error += "%s:-"
                else:
                    error += "-:-"
                error += ", Upload: "
                if files.has_key(dep_filename):
                    error += "yes"
                else:
                    error += "no"
                error += "]"
                unsat.append(error)

            if unsat:
                sys.stderr.write("MWAAP! %s: '%s' %s can not be satisifed:\n" % (filename, utils.pp_deps(parsed_dep), dep_type))
                for error in unsat:
                    sys.stderr.write("  %s\n" % (error))
                pkg_unsat = 1

    return pkg_unsat

def check_package(filename, files):
    try:
        control = apt_pkg.ParseSection(apt_inst.debExtractControl(utils.open_file(filename)))
    except:
        utils.warn("%s: debExtractControl() raised %s." % (filename, sys.exc_type))
        return 1
    Depends = control.Find("Depends")
    Pre_Depends = control.Find("Pre-Depends")
    #Recommends = control.Find("Recommends")
    pkg_arch = control.Find("Architecture")
    base_file = os.path.basename(filename)
    if pkg_arch == "all":
        check_archs = architectures
    else:
        check_archs = [pkg_arch]

    pkg_unsat = 0
    if Pre_Depends:
        pkg_unsat += check_dep(Pre_Depends, "pre-dependency", check_archs, base_file, files)

    if Depends:
        pkg_unsat += check_dep(Depends, "dependency", check_archs, base_file, files)
    #if Recommends:
    #pkg_unsat += check_dep(Recommends, "recommendation", check_archs, base_file, files)

    return pkg_unsat

################################################################################

def pass_fail (filename, result):
    if not Options["quiet"]:
        print "%s:" % (os.path.basename(filename)),
        if result:
            print "FAIL"
        else:
            print "ok"

################################################################################

def check_changes (filename):
    cnf = Config()

    try:
        changes = utils.parse_changes(filename)
        files = utils.build_file_list(changes)
    except ChangesUnicodeError:
        utils.warn("Improperly encoded changes file, not utf-8")
        return
    except:
        utils.warn("Error parsing changes file '%s'" % (filename))
        return

    result = 0

    # Move to the pool directory
    cwd = os.getcwd()
    f = files.keys()[0]
    pool_dir = cnf["Dir::Pool"] + '/' + utils.poolify(changes["source"], files[f]["component"])
    os.chdir(pool_dir)

    changes_result = 0
    for f in files.keys():
        if f.endswith(".deb"):
            result = check_package(f, files)
            if Options["verbose"]:
                pass_fail(f, result)
            changes_result += result

    pass_fail (filename, changes_result)

    # Move back
    os.chdir(cwd)

################################################################################

def check_deb (filename):
    result = check_package(filename, {})
    pass_fail(filename, result)


################################################################################

def check_joey (filename):
    cnf = Config()

    f = utils.open_file(filename)

    cwd = os.getcwd()
    os.chdir("%s/dists/proposed-updates" % (cnf["Dir::Root"]))

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
    f.close()

    os.chdir(cwd)

################################################################################

def parse_packages():
    global stable, stable_virtual, architectures

    cnf = Config()

    # Parse the Packages files (since it's a sub-second operation on auric)
    suite = "stable"
    stable = {}
    components = cnf.ValueList("Suite::%s::Components" % (suite))
    architectures = [ a.arch_string for a in get_suite_architectures(suite, skipsrc=True, skipall=True) ]
    for component in components:
        for architecture in architectures:
            filename = "%s/dists/%s/%s/binary-%s/Packages" % (cnf["Dir::Root"], suite, component, architecture)
            packages = utils.open_file(filename, 'r')
            Packages = apt_pkg.ParseTagFile(packages)
            while Packages.Step():
                package = Packages.Section.Find('Package')
                version = Packages.Section.Find('Version')
                provides = Packages.Section.Find('Provides')
                if not stable.has_key(package):
                    stable[package] = {}
                stable[package][architecture] = version
                if provides:
                    for virtual_pkg in provides.split(","):
                        virtual_pkg = virtual_pkg.strip()
                        if not stable_virtual.has_key(virtual_pkg):
                            stable_virtual[virtual_pkg] = {}
                        stable_virtual[virtual_pkg][architecture] = "NA"
            packages.close()

################################################################################

def main ():
    global Options

    cnf = Config()

    Arguments = [('d', "debug", "Check-Proposed-Updates::Options::Debug"),
                 ('q',"quiet","Check-Proposed-Updates::Options::Quiet"),
                 ('v',"verbose","Check-Proposed-Updates::Options::Verbose"),
                 ('h',"help","Check-Proposed-Updates::Options::Help")]
    for i in [ "debug", "quiet", "verbose", "help" ]:
        if not cnf.has_key("Check-Proposed-Updates::Options::%s" % (i)):
            cnf["Check-Proposed-Updates::Options::%s" % (i)] = ""

    arguments = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Check-Proposed-Updates::Options")

    if Options["Help"]:
        usage(0)
    if not arguments:
        utils.fubar("need at least one package name as an argument.")

    DBConn()

    print "Parsing packages files...",
    parse_packages()
    print "done."

    for f in arguments:
        if f.endswith(".changes"):
            check_changes(f)
        elif f.endswith(".deb"):
            check_deb(f)
        elif f.endswith(".joey"):
            check_joey(f)
        else:
            utils.fubar("Unrecognised file type: '%s'." % (f))

#######################################################################################

if __name__ == '__main__':
    main()
