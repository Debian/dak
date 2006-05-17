#!/usr/bin/env python

# Dependency check proposed-updates
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

import pg, sys, os
import dak.lib.utils, dak.lib.database
import apt_pkg, apt_inst

################################################################################

Cnf = None
projectB = None
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
                                print "Found %s as a real package." % (dak.lib.utils.pp_deps(parsed_dep))
                            unsat = 0
                            break
                # As a virtual?
                if stable_virtual.has_key(dep):
                    if stable_virtual[dep].has_key(arch):
                        if not constraint and not version:
                            if Options["debug"]:
                                print "Found %s as a virtual package." % (dak.lib.utils.pp_deps(parsed_dep))
                            unsat = 0
                            break
                # As part of the same .changes?
                epochless_version = dak.lib.utils.re_no_epoch.sub('', version)
                dep_filename = "%s_%s_%s.deb" % (dep, epochless_version, arch)
                if files.has_key(dep_filename):
                    if Options["debug"]:
                        print "Found %s in the same upload." % (dak.lib.utils.pp_deps(parsed_dep))
                    unsat = 0
                    break
                # Not found...
                # [FIXME: must be a better way ... ]
                error = "%s not found. [Real: " % (dak.lib.utils.pp_deps(parsed_dep))
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
                sys.stderr.write("MWAAP! %s: '%s' %s can not be satisifed:\n" % (filename, dak.lib.utils.pp_deps(parsed_dep), dep_type))
                for error in unsat:
                    sys.stderr.write("  %s\n" % (error))
                pkg_unsat = 1

    return pkg_unsat

def check_package(filename, files):
    try:
        control = apt_pkg.ParseSection(apt_inst.debExtractControl(dak.lib.utils.open_file(filename)))
    except:
        dak.lib.utils.warn("%s: debExtractControl() raised %s." % (filename, sys.exc_type))
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
    try:
        changes = dak.lib.utils.parse_changes(filename)
        files = dak.lib.utils.build_file_list(changes)
    except:
        dak.lib.utils.warn("Error parsing changes file '%s'" % (filename))
        return

    result = 0

    # Move to the pool directory
    cwd = os.getcwd()
    file = files.keys()[0]
    pool_dir = Cnf["Dir::Pool"] + '/' + dak.lib.utils.poolify(changes["source"], files[file]["component"])
    os.chdir(pool_dir)

    changes_result = 0
    for file in files.keys():
        if file.endswith(".deb"):
            result = check_package(file, files)
            if Options["verbose"]:
                pass_fail(file, result)
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
    file = dak.lib.utils.open_file(filename)

    cwd = os.getcwd()
    os.chdir("%s/dists/proposed-updates" % (Cnf["Dir::Root"]))

    for line in file.readlines():
        line = line.rstrip()
        if line.find('install') != -1:
            split_line = line.split()
            if len(split_line) != 2:
                dak.lib.utils.fubar("Parse error (not exactly 2 elements): %s" % (line))
            install_type = split_line[0]
            if install_type not in [ "install", "install-u", "sync-install" ]:
                dak.lib.utils.fubar("Unknown install type ('%s') from: %s" % (install_type, line))
            changes_filename = split_line[1]
            if Options["debug"]:
                print "Processing %s..." % (changes_filename)
            check_changes(changes_filename)
    file.close()

    os.chdir(cwd)

################################################################################

def parse_packages():
    global stable, stable_virtual, architectures

    # Parse the Packages files (since it's a sub-second operation on auric)
    suite = "stable"
    stable = {}
    components = Cnf.ValueList("Suite::%s::Components" % (suite))
    architectures = filter(dak.lib.utils.real_arch, Cnf.ValueList("Suite::%s::Architectures" % (suite)))
    for component in components:
        for architecture in architectures:
            filename = "%s/dists/%s/%s/binary-%s/Packages" % (Cnf["Dir::Root"], suite, component, architecture)
            packages = dak.lib.utils.open_file(filename, 'r')
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
    global Cnf, projectB, Options

    Cnf = dak.lib.utils.get_conf()

    Arguments = [('d', "debug", "Check-Proposed-Updates::Options::Debug"),
                 ('q',"quiet","Check-Proposed-Updates::Options::Quiet"),
                 ('v',"verbose","Check-Proposed-Updates::Options::Verbose"),
                 ('h',"help","Check-Proposed-Updates::Options::Help")]
    for i in [ "debug", "quiet", "verbose", "help" ]:
	if not Cnf.has_key("Check-Proposed-Updates::Options::%s" % (i)):
	    Cnf["Check-Proposed-Updates::Options::%s" % (i)] = ""

    arguments = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Check-Proposed-Updates::Options")

    if Options["Help"]:
        usage(0)
    if not arguments:
        dak.lib.utils.fubar("need at least one package name as an argument.")

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    dak.lib.database.init(Cnf, projectB)

    print "Parsing packages files...",
    parse_packages()
    print "done."

    for file in arguments:
        if file.endswith(".changes"):
            check_changes(file)
        elif file.endswith(".deb"):
            check_deb(file)
        elif file.endswith(".joey"):
            check_joey(file)
        else:
            dak.lib.utils.fubar("Unrecognised file type: '%s'." % (file))

#######################################################################################

if __name__ == '__main__':
    main()
