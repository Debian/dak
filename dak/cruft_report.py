#!/usr/bin/env python

# Check for obsolete binary packages
# Copyright (C) 2000, 2001, 2002, 2003, 2004  James Troup <james@nocrew.org>
# $Id: rene,v 1.23 2005-04-16 09:19:20 rmurray Exp $

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

# ``If you're claiming that's a "problem" that needs to be "fixed",
#   you might as well write some letters to God about how unfair entropy
#   is while you're at it.'' -- 20020802143104.GA5628@azure.humbug.org.au

## TODO:  fix NBS looping for version, implement Dubious NBS, fix up output of duplicate source package stuff, improve experimental ?, add support for non-US ?, add overrides, avoid ANAIS for duplicated packages

################################################################################

import commands, pg, os, string, sys, time
import utils, db_access
import apt_pkg

################################################################################

Cnf = None
projectB = None
suite_id = None
no_longer_in_suite = {}; # Really should be static to add_nbs, but I'm lazy

source_binaries = {}
source_versions = {}

################################################################################

def usage(exit_code=0):
    print """Usage: rene
Check for obsolete or duplicated packages.

  -h, --help                show this help and exit.
  -m, --mode=MODE           chose the MODE to run in (full or daily).
  -s, --suite=SUITE         check suite SUITE."""
    sys.exit(exit_code)

################################################################################

def add_nbs(nbs_d, source, version, package):
    # Ensure the package is still in the suite (someone may have already removed it)
    if no_longer_in_suite.has_key(package):
        return
    else:
        q = projectB.query("SELECT b.id FROM binaries b, bin_associations ba WHERE ba.bin = b.id AND ba.suite = %s AND b.package = '%s' LIMIT 1" % (suite_id, package))
        if not q.getresult():
            no_longer_in_suite[package] = ""
            return

    nbs_d.setdefault(source, {})
    nbs_d[source].setdefault(version, {})
    nbs_d[source][version][package] = ""

################################################################################

# Check for packages built on architectures they shouldn't be.
def do_anais(architecture, binaries_list, source):
    if architecture == "any" or architecture == "all":
        return ""

    anais_output = ""
    architectures = {}
    for arch in architecture.split():
        architectures[arch.strip()] = ""
    for binary in binaries_list:
        q = projectB.query("SELECT a.arch_string, b.version FROM binaries b, bin_associations ba, architecture a WHERE ba.suite = %s AND ba.bin = b.id AND b.architecture = a.id AND b.package = '%s'" % (suite_id, binary))
        ql = q.getresult()
        versions = []
        for i in ql:
            arch = i[0]
            version = i[1]
            if architectures.has_key(arch):
                versions.append(version)
        versions.sort(apt_pkg.VersionCompare)
        if versions:
            latest_version = versions.pop()
        else:
            latest_version = None
        # Check for 'invalid' architectures
        versions_d = {}
        for i in ql:
            arch = i[0]
            version = i[1]
            if not architectures.has_key(arch):
                versions_d.setdefault(version, [])
                versions_d[version].append(arch)

        if versions_d != {}:
            anais_output += "\n (*) %s_%s [%s]: %s\n" % (binary, latest_version, source, architecture)
            versions = versions_d.keys()
            versions.sort(apt_pkg.VersionCompare)
            for version in versions:
                arches = versions_d[version]
                arches.sort()
                anais_output += "    o %s: %s\n" % (version, ", ".join(arches))
    return anais_output

################################################################################

def do_nviu():
    experimental_id = db_access.get_suite_id("experimental")
    if experimental_id == -1:
        return
    # Check for packages in experimental obsoleted by versions in unstable
    q = projectB.query("""
SELECT s.source, s.version AS experimental, s2.version AS unstable
  FROM src_associations sa, source s, source s2, src_associations sa2
  WHERE sa.suite = %s AND sa2.suite = %d AND sa.source = s.id
   AND sa2.source = s2.id AND s.source = s2.source
   AND versioncmp(s.version, s2.version) < 0""" % (experimental_id,
                                                   db_access.get_suite_id("unstable")))
    ql = q.getresult()
    if ql:
        nviu_to_remove = []
        print "Newer version in unstable"
        print "-------------------------"
        print 
        for i in ql:
            (source, experimental_version, unstable_version) = i
            print " o %s (%s, %s)" % (source, experimental_version, unstable_version)
            nviu_to_remove.append(source)
        print
        print "Suggested command:"
        print " melanie -m \"[rene] NVIU\" -s experimental %s" % (" ".join(nviu_to_remove))
        print

################################################################################

def do_nbs(real_nbs):
    output = "Not Built from Source\n"
    output += "---------------------\n\n"

    nbs_to_remove = []
    nbs_keys = real_nbs.keys()
    nbs_keys.sort()
    for source in nbs_keys:
        output += " * %s_%s builds: %s\n" % (source,
                                       source_versions.get(source, "??"),
                                       source_binaries.get(source, "(source does not exist)"))
        output += "      but no longer builds:\n"
        versions = real_nbs[source].keys()
        versions.sort(apt_pkg.VersionCompare)
        for version in versions:
            packages = real_nbs[source][version].keys()
            packages.sort()
            for pkg in packages:
                nbs_to_remove.append(pkg)
            output += "        o %s: %s\n" % (version, ", ".join(packages))

        output += "\n"

    if nbs_to_remove:
        print output

        print "Suggested command:"
        print " melanie -m \"[rene] NBS\" -b %s" % (" ".join(nbs_to_remove))
        print

################################################################################

def do_dubious_nbs(dubious_nbs):
    print "Dubious NBS"
    print "-----------"
    print 

    dubious_nbs_keys = dubious_nbs.keys()
    dubious_nbs_keys.sort()
    for source in dubious_nbs_keys:
        print " * %s_%s builds: %s" % (source,
                                       source_versions.get(source, "??"),
                                       source_binaries.get(source, "(source does not exist)"))
        print "      won't admit to building:"
        versions = dubious_nbs[source].keys()
        versions.sort(apt_pkg.VersionCompare)
        for version in versions:
            packages = dubious_nbs[source][version].keys()
            packages.sort()
            print "        o %s: %s" % (version, ", ".join(packages))

        print 

################################################################################

def do_obsolete_source(duplicate_bins, bin2source):
    obsolete = {}
    for key in duplicate_bins.keys():
        (source_a, source_b) = key.split('~')
        for source in [ source_a, source_b ]:
            if not obsolete.has_key(source):
                if not source_binaries.has_key(source):
                    # Source has already been removed
                    continue
                else:
                    obsolete[source] = map(string.strip,
                                           source_binaries[source].split(','))
            for binary in duplicate_bins[key]:
                if bin2source.has_key(binary) and bin2source[binary]["source"] == source:
                    continue
                if binary in obsolete[source]:
                    obsolete[source].remove(binary)

    to_remove = []
    output = "Obsolete source package\n"
    output += "-----------------------\n\n"
    obsolete_keys = obsolete.keys()
    obsolete_keys.sort()
    for source in obsolete_keys:
        if not obsolete[source]:
            to_remove.append(source)
            output += " * %s (%s)\n" % (source, source_versions[source])
            for binary in map(string.strip, source_binaries[source].split(',')):
                if bin2source.has_key(binary):
                    output += "    o %s (%s) is built by %s.\n" \
                          % (binary, bin2source[binary]["version"],
                             bin2source[binary]["source"])
                else:
                    output += "    o %s is not built.\n" % binary
            output += "\n"

    if to_remove:
        print output

        print "Suggested command:"
        print " melanie -S -p -m \"[rene] obsolete source package\" %s" % (" ".join(to_remove))
        print

################################################################################

def main ():
    global Cnf, projectB, suite_id, source_binaries, source_versions

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Rene::Options::Help"),
                 ('m',"mode","Rene::Options::Mode", "HasArg"),
                 ('s',"suite","Rene::Options::Suite","HasArg")]
    for i in [ "help" ]:
	if not Cnf.has_key("Rene::Options::%s" % (i)):
	    Cnf["Rene::Options::%s" % (i)] = ""
    Cnf["Rene::Options::Suite"] = Cnf["Dinstall::DefaultSuite"]

    if not Cnf.has_key("Rene::Options::Mode"):
        Cnf["Rene::Options::Mode"] = "daily"

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Rene::Options")
    if Options["Help"]:
	usage()

    # Set up checks based on mode
    if Options["Mode"] == "daily":
        checks = [ "nbs", "nviu", "obsolete source" ]
    elif Options["Mode"] == "full":
        checks = [ "nbs", "nviu", "obsolete source", "dubious nbs", "bnb", "bms", "anais" ]
    else:
        utils.warn("%s is not a recognised mode - only 'full' or 'daily' are understood." % (Options["Mode"]))
        usage(1)

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    db_access.init(Cnf, projectB)

    bin_pkgs = {}
    src_pkgs = {}
    bin2source = {}
    bins_in_suite = {}
    nbs = {}
    source_versions = {}

    anais_output = ""
    duplicate_bins = {}

    suite = Options["Suite"]
    suite_id = db_access.get_suite_id(suite)

    bin_not_built = {}

    if "bnb" in checks:
        # Initalize a large hash table of all binary packages
        before = time.time()
        sys.stderr.write("[Getting a list of binary packages in %s..." % (suite))
        q = projectB.query("SELECT distinct b.package FROM binaries b, bin_associations ba WHERE ba.suite = %s AND ba.bin = b.id" % (suite_id))
        ql = q.getresult()
        sys.stderr.write("done. (%d seconds)]\n" % (int(time.time()-before)))
        for i in ql:
            bins_in_suite[i[0]] = ""

    # Checks based on the Sources files
    components = Cnf.ValueList("Suite::%s::Components" % (suite))
    for component in components:
        filename = "%s/dists/%s/%s/source/Sources.gz" % (Cnf["Dir::Root"], suite, component)
        # apt_pkg.ParseTagFile needs a real file handle and can't handle a GzipFile instance...
        temp_filename = utils.temp_filename()
        (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
        if (result != 0):
            sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
            sys.exit(result)
        sources = utils.open_file(temp_filename)
        Sources = apt_pkg.ParseTagFile(sources)
        while Sources.Step():
            source = Sources.Section.Find('Package')
            source_version = Sources.Section.Find('Version')
            architecture = Sources.Section.Find('Architecture')
            binaries = Sources.Section.Find('Binary')
            binaries_list = map(string.strip, binaries.split(','))

            if "bnb" in checks:
                # Check for binaries not built on any architecture.
                for binary in binaries_list:
                    if not bins_in_suite.has_key(binary):
                        bin_not_built.setdefault(source, {})
                        bin_not_built[source][binary] = ""

            if "anais" in checks:
                anais_output += do_anais(architecture, binaries_list, source)

            # Check for duplicated packages and build indices for checking "no source" later
            source_index = component + '/' + source
            if src_pkgs.has_key(source):
                print " %s is a duplicated source package (%s and %s)" % (source, source_index, src_pkgs[source])
            src_pkgs[source] = source_index
            for binary in binaries_list:
                if bin_pkgs.has_key(binary):
                    key_list = [ source, bin_pkgs[binary] ]
                    key_list.sort()
                    key = '~'.join(key_list)
                    duplicate_bins.setdefault(key, [])
                    duplicate_bins[key].append(binary)
                bin_pkgs[binary] = source
            source_binaries[source] = binaries
            source_versions[source] = source_version

        sources.close()
        os.unlink(temp_filename)

    # Checks based on the Packages files
    for component in components + ['main/debian-installer']:
        architectures = filter(utils.real_arch, Cnf.ValueList("Suite::%s::Architectures" % (suite)))
        for architecture in architectures:
            filename = "%s/dists/%s/%s/binary-%s/Packages.gz" % (Cnf["Dir::Root"], suite, component, architecture)
            # apt_pkg.ParseTagFile needs a real file handle
            temp_filename = utils.temp_filename()
            (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
            if (result != 0):
                sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
                sys.exit(result)
            packages = utils.open_file(temp_filename)
            Packages = apt_pkg.ParseTagFile(packages)
            while Packages.Step():
                package = Packages.Section.Find('Package')
                source = Packages.Section.Find('Source', "")
                version = Packages.Section.Find('Version')
                if source == "":
                    source = package
                if bin2source.has_key(package) and \
                       apt_pkg.VersionCompare(version, bin2source[package]["version"]) > 0:
                    bin2source[package]["version"] = version
                    bin2source[package]["source"] = source
                else:
                    bin2source[package] = {}
                    bin2source[package]["version"] = version
                    bin2source[package]["source"] = source
                if source.find("(") != -1:
                    m = utils.re_extract_src_version.match(source)
                    source = m.group(1)
                    version = m.group(2)
                if not bin_pkgs.has_key(package):
                    nbs.setdefault(source,{})
                    nbs[source].setdefault(package, {})
                    nbs[source][package][version] = ""
                else:
                    previous_source = bin_pkgs[package]
                    if previous_source != source:
                        key_list = [ source, previous_source ]
                        key_list.sort()
                        key = '~'.join(key_list)
                        duplicate_bins.setdefault(key, [])
                        if package not in duplicate_bins[key]:
                            duplicate_bins[key].append(package)
            packages.close()
            os.unlink(temp_filename)
    
    if "obsolete source" in checks:
        do_obsolete_source(duplicate_bins, bin2source)

    # Distinguish dubious (version numbers match) and 'real' NBS (they don't)
    dubious_nbs = {}
    real_nbs = {}
    for source in nbs.keys():
        for package in nbs[source].keys():
            versions = nbs[source][package].keys()
            versions.sort(apt_pkg.VersionCompare)
            latest_version = versions.pop()
            source_version = source_versions.get(source,"0")
            if apt_pkg.VersionCompare(latest_version, source_version) == 0:
                add_nbs(dubious_nbs, source, latest_version, package)
            else:
                add_nbs(real_nbs, source, latest_version, package)

    if "nviu" in checks:
        do_nviu()

    if "nbs" in checks:
        do_nbs(real_nbs)

    ###

    if Options["Mode"] == "full":
        print "="*75
        print

    if "bnb" in checks:
        print "Unbuilt binary packages"
        print "-----------------------"
        print
        keys = bin_not_built.keys()
        keys.sort()
        for source in keys:
            binaries = bin_not_built[source].keys()
            binaries.sort()
            print " o %s: %s" % (source, ", ".join(binaries))
        print 

    if "bms" in checks:
        print "Built from multiple source packages"
        print "-----------------------------------"
        print 
        keys = duplicate_bins.keys()
        keys.sort()
        for key in keys:
            (source_a, source_b) = key.split("~")
            print " o %s & %s => %s" % (source_a, source_b, ", ".join(duplicate_bins[key]))
        print 

    if "anais" in checks:
        print "Architecture Not Allowed In Source"
        print "----------------------------------"
        print anais_output
        print 

    if "dubious nbs" in checks:
        do_dubious_nbs(dubious_nbs)


################################################################################

if __name__ == '__main__':
    main()
