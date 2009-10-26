#!/usr/bin/env python

""" Check for obsolete binary packages """
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

# ``If you're claiming that's a "problem" that needs to be "fixed",
#   you might as well write some letters to God about how unfair entropy
#   is while you're at it.'' -- 20020802143104.GA5628@azure.humbug.org.au

## TODO:  fix NBS looping for version, implement Dubious NBS, fix up output of
##        duplicate source package stuff, improve experimental ?, add overrides,
##        avoid ANAIS for duplicated packages

################################################################################

import commands, os, sys, time, re
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils
from daklib.regexes import re_extract_src_version

################################################################################

no_longer_in_suite = {}; # Really should be static to add_nbs, but I'm lazy

source_binaries = {}
source_versions = {}

################################################################################

def usage(exit_code=0):
    print """Usage: dak cruft-report
Check for obsolete or duplicated packages.

  -h, --help                show this help and exit.
  -m, --mode=MODE           chose the MODE to run in (full or daily).
  -s, --suite=SUITE         check suite SUITE.
  -w, --wanna-build-dump    where to find the copies of http://buildd.debian.org/stats/*.txt"""
    sys.exit(exit_code)

################################################################################

def add_nbs(nbs_d, source, version, package, suite_id, session):
    # Ensure the package is still in the suite (someone may have already removed it)
    if no_longer_in_suite.has_key(package):
        return
    else:
        q = session.execute("""SELECT b.id FROM binaries b, bin_associations ba
                                WHERE ba.bin = b.id AND ba.suite = :suite_id
                                  AND b.package = :package LIMIT 1""", {'suite_id': suite_id,
                                                                         'package': package})
        if not q.fetchall():
            no_longer_in_suite[package] = ""
            return

    nbs_d.setdefault(source, {})
    nbs_d[source].setdefault(version, {})
    nbs_d[source][version][package] = ""

################################################################################

# Check for packages built on architectures they shouldn't be.
def do_anais(architecture, binaries_list, source, session):
    if architecture == "any" or architecture == "all":
        return ""

    anais_output = ""
    architectures = {}
    for arch in architecture.split():
        architectures[arch.strip()] = ""
    for binary in binaries_list:
        q = session.execute("""SELECT a.arch_string, b.version
                                FROM binaries b, bin_associations ba, architecture a
                               WHERE ba.suite = :suiteid AND ba.bin = b.id
                                 AND b.architecture = a.id AND b.package = :package""",
                             {'suiteid': suite_id, 'package': binary})
        versions = []
        for i in q.fetchall():
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

# Check for out-of-date binaries on architectures that do not want to build that
# package any more, and have them listed as Not-For-Us
def do_nfu(nfu_packages):
    output = ""
    
    a2p = {}

    for architecture in nfu_packages:
        a2p[architecture] = []
        for (package,bver,sver) in nfu_packages[architecture]:
            output += "  * [%s] does not want %s (binary %s, source %s)\n" % (architecture, package, bver, sver)
            a2p[architecture].append(package)


    if output:
        print "Obsolete by Not-For-Us"
        print "----------------------"
        print
        print output

        print "Suggested commands:"
        for architecture in a2p:
            if a2p[architecture]:
                print (" dak rm -m \"[auto-cruft] NFU\" -s %s -a %s -b %s" % 
                    (suite, architecture, " ".join(a2p[architecture])))
        print

def parse_nfu(architecture):
    cnf = Config()
    # utils/hpodder_1.1.5.0: Not-For-Us [optional:out-of-date]
    r = re.compile("^\w+/([^_]+)_.*: Not-For-Us")

    ret = set()
    
    filename = "%s/%s-all.txt" % (cnf["Cruft-Report::Options::Wanna-Build-Dump"], architecture)

    # Not all architectures may have a wanna-build dump, so we want to ignore missin
    # files
    if os.path.exists(filename):
        f = utils.open_file(filename)
        for line in f:
            if line[0] == ' ':
                continue

            m = r.match(line)
            if m:
                ret.add(m.group(1))

        f.close()
    else:
        utils.warn("No wanna-build dump file for architecture %s" % architecture)
    return ret

################################################################################

def do_newer_version(lowersuite_name, highersuite_name, code, session):
    lowersuite = get_suite(lowersuite_name, session)
    if not lowersuite:
        return

    highersuite = get_suite(highersuite_name, session)
    if not highersuite:
        return

    # Check for packages in $highersuite obsoleted by versions in $lowersuite
    q = session.execute("""
SELECT s.source, s.version AS lower, s2.version AS higher
  FROM src_associations sa, source s, source s2, src_associations sa2
  WHERE sa.suite = :highersuite_id AND sa2.suite = :lowersuite_id AND sa.source = s.id
   AND sa2.source = s2.id AND s.source = s2.source
   AND s.version < s2.version""", {'lowersuite_id': lowersuite.suite_id,
                                    'highersuite_id': highersuite.suite_id})
    ql = q.fetchall()
    if ql:
        nv_to_remove = []
        print "Newer version in %s" % lowersuite.suite_name
        print "-----------------" + "-" * len(lowersuite.suite_name)
        print
        for i in ql:
            (source, higher_version, lower_version) = i
            print " o %s (%s, %s)" % (source, higher_version, lower_version)
            nv_to_remove.append(source)
        print
        print "Suggested command:"
        print " dak rm -m \"[auto-cruft] %s\" -s %s %s" % (code, highersuite.suite_name,
                                                           " ".join(nv_to_remove))
        print

################################################################################

def do_nbs(real_nbs):
    output = "Not Built from Source\n"
    output += "---------------------\n\n"

    cmd_output = ""
    nbs_keys = real_nbs.keys()
    nbs_keys.sort()
    for source in nbs_keys:
        output += " * %s_%s builds: %s\n" % (source,
                                       source_versions.get(source, "??"),
                                       source_binaries.get(source, "(source does not exist)"))
        output += "      but no longer builds:\n"
        versions = real_nbs[source].keys()
        versions.sort(apt_pkg.VersionCompare)
        all_packages = []
        for version in versions:
            packages = real_nbs[source][version].keys()
            packages.sort()
            all_packages.extend(packages)
            output += "        o %s: %s\n" % (version, ", ".join(packages))
        if all_packages:
            all_packages.sort()
            cmd_output += " dak rm -m \"[auto-cruft] NBS (was built by %s)\" -s %s -b %s\n\n" % (source, suite.suite_name, " ".join(all_packages))

        output += "\n"

    if len(cmd_output):
        print output
        print "Suggested commands:\n"
        print cmd_output

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
        (source_a, source_b) = key.split('_')
        for source in [ source_a, source_b ]:
            if not obsolete.has_key(source):
                if not source_binaries.has_key(source):
                    # Source has already been removed
                    continue
                else:
                    obsolete[source] = [ i.strip() for i in source_binaries[source].split(',') ]
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
            for binary in [ i.strip() for i in source_binaries[source].split(',') ]:
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
        print " dak rm -S -p -m \"[auto-cruft] obsolete source package\" %s" % (" ".join(to_remove))
        print

def get_suite_binaries(suite, session):
    # Initalize a large hash table of all binary packages
    binaries = {}

    print "Getting a list of binary packages in %s..." % suite.suite_name
    q = session.execute("""SELECT distinct b.package
                             FROM binaries b, bin_associations ba
                            WHERE ba.suite = :suiteid AND ba.bin = b.id""",
                           {'suiteid': suite.suite_id})
    for i in q.fetchall():
        binaries[i[0]] = ""

    return binaries

################################################################################

def main ():
    global suite, suite_id, source_binaries, source_versions

    cnf = Config()

    Arguments = [('h',"help","Cruft-Report::Options::Help"),
                 ('m',"mode","Cruft-Report::Options::Mode", "HasArg"),
                 ('s',"suite","Cruft-Report::Options::Suite","HasArg"),
                 ('w',"wanna-build-dump","Cruft-Report::Options::Wanna-Build-Dump","HasArg")]
    for i in [ "help" ]:
        if not cnf.has_key("Cruft-Report::Options::%s" % (i)):
            cnf["Cruft-Report::Options::%s" % (i)] = ""
    cnf["Cruft-Report::Options::Suite"] = cnf["Dinstall::DefaultSuite"]

    if not cnf.has_key("Cruft-Report::Options::Mode"):
        cnf["Cruft-Report::Options::Mode"] = "daily"

    if not cnf.has_key("Cruft-Report::Options::Wanna-Build-Dump"):
        cnf["Cruft-Report::Options::Wanna-Build-Dump"] = "/srv/ftp.debian.org/scripts/nfu"

    apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.SubTree("Cruft-Report::Options")
    if Options["Help"]:
        usage()

    # Set up checks based on mode
    if Options["Mode"] == "daily":
        checks = [ "nbs", "nviu", "obsolete source" ]
    elif Options["Mode"] == "full":
        checks = [ "nbs", "nviu", "obsolete source", "nfu", "dubious nbs", "bnb", "bms", "anais" ]
    else:
        utils.warn("%s is not a recognised mode - only 'full' or 'daily' are understood." % (Options["Mode"]))
        usage(1)

    session = DBConn().session()

    bin_pkgs = {}
    src_pkgs = {}
    bin2source = {}
    bins_in_suite = {}
    nbs = {}
    source_versions = {}

    anais_output = ""
    duplicate_bins = {}

    nfu_packages = {}

    suite = get_suite(Options["Suite"].lower(), session)
    suite_id = suite.suite_id
    suite_name = suite.suite_name.lower()

    bin_not_built = {}

    if "bnb" in checks:
        bins_in_suite = get_suite_binaries(suite_name, session)

    # Checks based on the Sources files
    components = cnf.ValueList("Suite::%s::Components" % (suite_name))
    for component in components:
        filename = "%s/dists/%s/%s/source/Sources.gz" % (cnf["Dir::Root"], suite_name, component)
        # apt_pkg.ParseTagFile needs a real file handle and can't handle a GzipFile instance...
        (fd, temp_filename) = utils.temp_filename()
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
            binaries_list = [ i.strip() for i in  binaries.split(',') ]

            if "bnb" in checks:
                # Check for binaries not built on any architecture.
                for binary in binaries_list:
                    if not bins_in_suite.has_key(binary):
                        bin_not_built.setdefault(source, {})
                        bin_not_built[source][binary] = ""

            if "anais" in checks:
                anais_output += do_anais(architecture, binaries_list, source, session)

            # Check for duplicated packages and build indices for checking "no source" later
            source_index = component + '/' + source
            if src_pkgs.has_key(source):
                print " %s is a duplicated source package (%s and %s)" % (source, source_index, src_pkgs[source])
            src_pkgs[source] = source_index
            for binary in binaries_list:
                if bin_pkgs.has_key(binary):
                    key_list = [ source, bin_pkgs[binary] ]
                    key_list.sort()
                    key = '_'.join(key_list)
                    duplicate_bins.setdefault(key, [])
                    duplicate_bins[key].append(binary)
                bin_pkgs[binary] = source
            source_binaries[source] = binaries
            source_versions[source] = source_version

        sources.close()
        os.unlink(temp_filename)

    # Checks based on the Packages files
    check_components = components[:]
    if suite_name != "experimental":
        check_components.append('main/debian-installer');

    for component in check_components:
        architectures = [ a.arch_string for a in get_suite_architectures(suite_name,
                                                                         skipsrc=True, skipall=True,
                                                                         session=session) ]
        for architecture in architectures:
            if component == 'main/debian-installer' and re.match("kfreebsd", architecture):
                continue
            filename = "%s/dists/%s/%s/binary-%s/Packages.gz" % (cnf["Dir::Root"], suite_name, component, architecture)
            # apt_pkg.ParseTagFile needs a real file handle
            (fd, temp_filename) = utils.temp_filename()
            (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
            if (result != 0):
                sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
                sys.exit(result)

            if "nfu" in checks:
                nfu_packages.setdefault(architecture,[])
                nfu_entries = parse_nfu(architecture)

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
                    m = re_extract_src_version.match(source)
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
                        key = '_'.join(key_list)
                        duplicate_bins.setdefault(key, [])
                        if package not in duplicate_bins[key]:
                            duplicate_bins[key].append(package)
                    if "nfu" in checks:
                        if package in nfu_entries and \
                               version != source_versions[source]: # only suggest to remove out-of-date packages
                            nfu_packages[architecture].append((package,version,source_versions[source]))
                    
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
                add_nbs(dubious_nbs, source, latest_version, package, suite_id, session)
            else:
                add_nbs(real_nbs, source, latest_version, package, suite_id, session)

    if "nviu" in checks:
        do_newer_version('unstable', 'experimental', 'NVIU', session)

    if "nbs" in checks:
        do_nbs(real_nbs)

    ###

    if Options["Mode"] == "full":
        print "="*75
        print

    if "nfu" in checks:
        do_nfu(nfu_packages)

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
            (source_a, source_b) = key.split("_")
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
