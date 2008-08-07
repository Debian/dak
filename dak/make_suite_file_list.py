#!/usr/bin/env python

# Generate file lists used by apt-ftparchive to generate Packages and Sources files
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>

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

# <elmo> I'm doing it in python btw.. nothing against your monster
#        SQL, but the python wins in terms of speed and readiblity
# <aj> bah
# <aj> you suck!!!!!
# <elmo> sorry :(
# <aj> you are not!!!
# <aj> you mock my SQL!!!!
# <elmo> you want have contest of skillz??????
# <aj> all your skillz are belong to my sql!!!!
# <elmo> yo momma are belong to my python!!!!
# <aj> yo momma was SQLin' like a pig last night!

################################################################################

import copy, os, pg, sys
import apt_pkg
import symlink_dists
from daklib import database
from daklib import logging
from daklib import utils

################################################################################

projectB = None
Cnf = None
Logger = None
Options = None

################################################################################

def Dict(**dict): return dict

################################################################################

def usage (exit_code=0):
    print """Usage: dak make-suite-file-list [OPTION]
Write out file lists suitable for use with apt-ftparchive.

  -a, --architecture=ARCH   only write file lists for this architecture
  -c, --component=COMPONENT only write file lists for this component
  -f, --force               ignore Untouchable suite directives in dak.conf
  -h, --help                show this help and exit
  -n, --no-delete           don't delete older versions
  -s, --suite=SUITE         only write file lists for this suite

ARCH, COMPONENT and SUITE can be space separated lists, e.g.
    --architecture=\"m68k i386\""""
    sys.exit(exit_code)

################################################################################

def version_cmp(a, b):
    return -apt_pkg.VersionCompare(a[0], b[0])

#####################################################

def delete_packages(delete_versions, pkg, dominant_arch, suite,
                    dominant_version, delete_table, delete_col, packages):
    suite_id = database.get_suite_id(suite)
    for version in delete_versions:
        delete_unique_id = version[1]
        if not packages.has_key(delete_unique_id):
            continue
        delete_version = version[0]
        delete_id = packages[delete_unique_id]["id"]
        delete_arch = packages[delete_unique_id]["arch"]
        if not Cnf.Find("Suite::%s::Untouchable" % (suite)) or Options["Force"]:
            if Options["No-Delete"]:
                print "Would delete %s_%s_%s in %s in favour of %s_%s" % (pkg, delete_arch, delete_version, suite, dominant_version, dominant_arch)
            else:
                Logger.log(["dominated", pkg, delete_arch, delete_version, dominant_version, dominant_arch])
                projectB.query("DELETE FROM %s WHERE suite = %s AND %s = %s" % (delete_table, suite_id, delete_col, delete_id))
            del packages[delete_unique_id]
        else:
            if Options["No-Delete"]:
                print "Would delete %s_%s_%s in favour of %s_%s, but %s is untouchable" % (pkg, delete_arch, delete_version, dominant_version, dominant_arch, suite)
            else:
                Logger.log(["dominated but untouchable", pkg, delete_arch, delete_version, dominant_version, dominant_arch])

#####################################################

# Per-suite&pkg: resolve arch-all, vs. arch-any, assumes only one arch-all
def resolve_arch_all_vs_any(versions, packages):
    arch_all_version = None
    arch_any_versions = copy.copy(versions)
    for i in arch_any_versions:
        unique_id = i[1]
        arch = packages[unique_id]["arch"]
        if arch == "all":
            arch_all_versions = [i]
            arch_all_version = i[0]
            arch_any_versions.remove(i)
    # Sort arch: any versions into descending order
    arch_any_versions.sort(version_cmp)
    highest_arch_any_version = arch_any_versions[0][0]

    pkg = packages[unique_id]["pkg"]
    suite = packages[unique_id]["suite"]
    delete_table = "bin_associations"
    delete_col = "bin"

    if apt_pkg.VersionCompare(highest_arch_any_version, arch_all_version) < 1:
        # arch: all dominates
        delete_packages(arch_any_versions, pkg, "all", suite,
                        arch_all_version, delete_table, delete_col, packages)
    else:
        # arch: any dominates
        delete_packages(arch_all_versions, pkg, "any", suite,
                        highest_arch_any_version, delete_table, delete_col,
                        packages)

#####################################################

# Per-suite&pkg&arch: resolve duplicate versions
def remove_duplicate_versions(versions, packages):
    # Sort versions into descending order
    versions.sort(version_cmp)
    dominant_versions = versions[0]
    dominated_versions = versions[1:]
    (dominant_version, dominant_unqiue_id) = dominant_versions
    pkg = packages[dominant_unqiue_id]["pkg"]
    arch = packages[dominant_unqiue_id]["arch"]
    suite = packages[dominant_unqiue_id]["suite"]
    if arch == "source":
        delete_table = "src_associations"
        delete_col = "source"
    else: # !source
        delete_table = "bin_associations"
        delete_col = "bin"
    # Remove all but the highest
    delete_packages(dominated_versions, pkg, arch, suite,
                    dominant_version, delete_table, delete_col, packages)
    return [dominant_versions]

################################################################################

def cleanup(packages):
    # Build up the index used by the clean up functions
    d = {}
    for unique_id in packages.keys():
        suite = packages[unique_id]["suite"]
        pkg = packages[unique_id]["pkg"]
        arch = packages[unique_id]["arch"]
        version = packages[unique_id]["version"]
        d.setdefault(suite, {})
        d[suite].setdefault(pkg, {})
        d[suite][pkg].setdefault(arch, [])
        d[suite][pkg][arch].append([version, unique_id])
    # Clean up old versions
    for suite in d.keys():
        for pkg in d[suite].keys():
            for arch in d[suite][pkg].keys():
                versions = d[suite][pkg][arch]
                if len(versions) > 1:
                    d[suite][pkg][arch] = remove_duplicate_versions(versions, packages)

    # Arch: all -> any and vice versa
    for suite in d.keys():
        for pkg in d[suite].keys():
            arches = d[suite][pkg]
            # If we don't have any arch: all; we've nothing to do
            if not arches.has_key("all"):
                continue
            # Check to see if we have arch: all and arch: !all (ignoring source)
            num_arches = len(arches.keys())
            if arches.has_key("source"):
                num_arches -= 1
            # If we do, remove the duplicates
            if num_arches > 1:
                versions = []
                for arch in arches.keys():
                    if arch != "source":
                        versions.extend(d[suite][pkg][arch])
                resolve_arch_all_vs_any(versions, packages)

################################################################################

def write_legacy_mixed_filelist(suite, list, packages, dislocated_files):
    # Work out the filename
    filename = os.path.join(Cnf["Dir::Lists"], "%s_-_all.list" % (suite))
    output = utils.open_file(filename, "w")
    # Generate the final list of files
    files = {}
    for id in list:
        path = packages[id]["path"]
        filename = packages[id]["filename"]
        file_id = packages[id]["file_id"]
        if suite == "stable" and dislocated_files.has_key(file_id):
            filename = dislocated_files[file_id]
        else:
            filename = path + filename
        if files.has_key(filename):
            utils.warn("%s (in %s) is duplicated." % (filename, suite))
        else:
            files[filename] = ""
    # Sort the files since apt-ftparchive doesn't
    keys = files.keys()
    keys.sort()
    # Write the list of files out
    for file in keys:
        output.write(file+'\n')
    output.close()

############################################################

def write_filelist(suite, component, arch, type, list, packages, dislocated_files):
    # Work out the filename
    if arch != "source":
        if type == "udeb":
            arch = "debian-installer_binary-%s" % (arch)
        elif type == "deb":
            arch = "binary-%s" % (arch)
    filename = os.path.join(Cnf["Dir::Lists"], "%s_%s_%s.list" % (suite, component, arch))
    output = utils.open_file(filename, "w")
    # Generate the final list of files
    files = {}
    for id in list:
        path = packages[id]["path"]
        filename = packages[id]["filename"]
        file_id = packages[id]["file_id"]
        pkg = packages[id]["pkg"]
        if suite == "stable" and dislocated_files.has_key(file_id):
            filename = dislocated_files[file_id]
        else:
            filename = path + filename
        if files.has_key(pkg):
            utils.warn("%s (in %s/%s, %s) is duplicated." % (pkg, suite, component, filename))
        else:
            files[pkg] = filename
    # Sort the files since apt-ftparchive doesn't
    pkgs = files.keys()
    pkgs.sort()
    # Write the list of files out
    for pkg in pkgs:
        output.write(files[pkg]+'\n')
    output.close()

################################################################################

def write_filelists(packages, dislocated_files):
    # Build up the index to iterate over
    d = {}
    for unique_id in packages.keys():
        suite = packages[unique_id]["suite"]
        component = packages[unique_id]["component"]
        arch = packages[unique_id]["arch"]
        type = packages[unique_id]["type"]
        d.setdefault(suite, {})
        d[suite].setdefault(component, {})
        d[suite][component].setdefault(arch, {})
        d[suite][component][arch].setdefault(type, [])
        d[suite][component][arch][type].append(unique_id)
    # Flesh out the index
    if not Options["Suite"]:
        suites = Cnf.SubTree("Suite").List()
    else:
        suites = utils.split_args(Options["Suite"])
    for suite in [ i.lower() for i in suites ]:
        d.setdefault(suite, {})
        if not Options["Component"]:
            components = Cnf.ValueList("Suite::%s::Components" % (suite))
        else:
            components = utils.split_args(Options["Component"])
        udeb_components = Cnf.ValueList("Suite::%s::UdebComponents" % (suite))
        udeb_components = udeb_components
        for component in components:
            d[suite].setdefault(component, {})
            if component in udeb_components:
                binary_types = [ "deb", "udeb" ]
            else:
                binary_types = [ "deb" ]
            if not Options["Architecture"]:
                architectures = Cnf.ValueList("Suite::%s::Architectures" % (suite))
            else:
                architectures = utils.split_args(Options["Architectures"])
            for arch in [ i.lower() for i in architectures ]:
                d[suite][component].setdefault(arch, {})
                if arch == "source":
                    types = [ "dsc" ]
                else:
                    types = binary_types
                for type in types:
                    d[suite][component][arch].setdefault(type, [])
    # Then walk it
    for suite in d.keys():
        if Cnf.has_key("Suite::%s::Components" % (suite)):
            for component in d[suite].keys():
                for arch in d[suite][component].keys():
                    if arch == "all":
                        continue
                    for type in d[suite][component][arch].keys():
                        list = d[suite][component][arch][type]
                        # If it's a binary, we need to add in the arch: all debs too
                        if arch != "source":
                            archall_suite = Cnf.get("Make-Suite-File-List::ArchAllMap::%s" % (suite))
                            if archall_suite:
                                list.extend(d[archall_suite][component]["all"][type])
                            elif d[suite][component].has_key("all") and \
                                     d[suite][component]["all"].has_key(type):
                                list.extend(d[suite][component]["all"][type])
                        write_filelist(suite, component, arch, type, list,
                                       packages, dislocated_files)
        else: # legacy-mixed suite
            list = []
            for component in d[suite].keys():
                for arch in d[suite][component].keys():
                    for type in d[suite][component][arch].keys():
                        list.extend(d[suite][component][arch][type])
            write_legacy_mixed_filelist(suite, list, packages, dislocated_files)

################################################################################

# Want to use stable dislocation support: True or false?
def stable_dislocation_p():
    # If the support is not explicitly enabled, assume it's disabled
    if not Cnf.FindB("Dinstall::StableDislocationSupport"):
        return 0
    # If we don't have a stable suite, obviously a no-op
    if not Cnf.has_key("Suite::Stable"):
        return 0
    # If the suite(s) weren't explicitly listed, all suites are done
    if not Options["Suite"]:
        return 1
    # Otherwise, look in what suites the user specified
    suites = utils.split_args(Options["Suite"])

    if "stable" in suites:
        return 1
    else:
        return 0

################################################################################

def do_da_do_da():
    # If we're only doing a subset of suites, ensure we do enough to
    # be able to do arch: all mapping.
    if Options["Suite"]:
        suites = utils.split_args(Options["Suite"])
        for suite in suites:
            archall_suite = Cnf.get("Make-Suite-File-List::ArchAllMap::%s" % (suite))
            if archall_suite and archall_suite not in suites:
                utils.warn("Adding %s as %s maps Arch: all from it." % (archall_suite, suite))
                suites.append(archall_suite)
        Options["Suite"] = ",".join(suites)

    (con_suites, con_architectures, con_components, check_source) = \
                 utils.parse_args(Options)

    if stable_dislocation_p():
        dislocated_files = symlink_dists.find_dislocated_stable(Cnf, projectB)
    else:
        dislocated_files = {}

    query = """
SELECT b.id, b.package, a.arch_string, b.version, l.path, f.filename, c.name,
       f.id, su.suite_name, b.type
  FROM binaries b, bin_associations ba, architecture a, files f, location l,
       component c, suite su
  WHERE b.id = ba.bin AND b.file = f.id AND b.architecture = a.id
    AND f.location = l.id AND l.component = c.id AND ba.suite = su.id
    %s %s %s""" % (con_suites, con_architectures, con_components)
    if check_source:
        query += """
UNION
SELECT s.id, s.source, 'source', s.version, l.path, f.filename, c.name, f.id,
       su.suite_name, 'dsc'
  FROM source s, src_associations sa, files f, location l, component c, suite su
  WHERE s.id = sa.source AND s.file = f.id AND f.location = l.id
    AND l.component = c.id AND sa.suite = su.id %s %s""" % (con_suites, con_components)
    q = projectB.query(query)
    ql = q.getresult()
    # Build up the main index of packages
    packages = {}
    unique_id = 0
    for i in ql:
        (id, pkg, arch, version, path, filename, component, file_id, suite, type) = i
        # 'id' comes from either 'binaries' or 'source', so it's not unique
        unique_id += 1
        packages[unique_id] = Dict(id=id, pkg=pkg, arch=arch, version=version,
                                   path=path, filename=filename,
                                   component=component, file_id=file_id,
                                   suite=suite, type = type)
    cleanup(packages)
    write_filelists(packages, dislocated_files)

################################################################################

def main():
    global Cnf, projectB, Options, Logger

    Cnf = utils.get_conf()
    Arguments = [('a', "architecture", "Make-Suite-File-List::Options::Architecture", "HasArg"),
                 ('c', "component", "Make-Suite-File-List::Options::Component", "HasArg"),
                 ('h', "help", "Make-Suite-File-List::Options::Help"),
                 ('n', "no-delete", "Make-Suite-File-List::Options::No-Delete"),
                 ('f', "force", "Make-Suite-File-List::Options::Force"),
                 ('s', "suite", "Make-Suite-File-List::Options::Suite", "HasArg")]
    for i in ["architecture", "component", "help", "no-delete", "suite", "force" ]:
        if not Cnf.has_key("Make-Suite-File-List::Options::%s" % (i)):
            Cnf["Make-Suite-File-List::Options::%s" % (i)] = ""
    apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Make-Suite-File-List::Options")
    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)
    Logger = logging.Logger(Cnf, "make-suite-file-list")
    do_da_do_da()
    Logger.close()

#########################################################################################

if __name__ == '__main__':
    main()
