#! /usr/bin/env python3

"""
Check for obsolete binary packages

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000-2006 James Troup <james@nocrew.org>
@copyright: 2009      Torsten Werner <twerner@debian.org>
@license: GNU General Public License version 2 or later
"""

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

import functools
import os
import sys
import re
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils
from daklib.regexes import re_extract_src_version
from daklib.cruft import *

################################################################################

no_longer_in_suite = {} # Really should be static to add_nbs, but I'm lazy

source_binaries = {}
source_versions = {}

################################################################################


def usage(exit_code=0):
    print("""Usage: dak cruft-report
Check for obsolete or duplicated packages.

  -h, --help                show this help and exit.
  -m, --mode=MODE           chose the MODE to run in (full, daily, bdo).
  -s, --suite=SUITE         check suite SUITE.
  -R, --rdep-check          check reverse dependencies
  -w, --wanna-build-dump    where to find the copies of https://buildd.debian.org/stats/*.txt""")
    sys.exit(exit_code)

################################################################################


def add_nbs(nbs_d, source, version, package, suite_id, session):
    # Ensure the package is still in the suite (someone may have already removed it)
    if package in no_longer_in_suite:
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

    version_sort_key = functools.cmp_to_key(apt_pkg.version_compare)
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
        ql = q.fetchall()
        versions = []
        for i in ql:
            arch = i[0]
            version = i[1]
            if arch in architectures:
                versions.append(version)
        versions.sort(key=version_sort_key)
        if versions:
            latest_version = versions.pop()
        else:
            latest_version = None
        # Check for 'invalid' architectures
        versions_d = {}
        for i in ql:
            arch = i[0]
            version = i[1]
            if arch not in architectures:
                versions_d.setdefault(version, [])
                versions_d[version].append(arch)

        if versions_d != {}:
            anais_output += "\n (*) %s_%s [%s]: %s\n" % (binary, latest_version, source, architecture)
            for version in sorted(versions_d, key=version_sort_key):
                arches = sorted(versions_d[version])
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
        for (package, bver, sver) in nfu_packages[architecture]:
            output += "  * [%s] does not want %s (binary %s, source %s)\n" % (architecture, package, bver, sver)
            a2p[architecture].append(package)

    if output:
        print("Obsolete by Not-For-Us")
        print("----------------------")
        print()
        print(output)

        print("Suggested commands:")
        for architecture in a2p:
            if a2p[architecture]:
                print((" dak rm -o -m \"[auto-cruft] NFU\" -s %s -a %s -b %s" %
                    (suite.suite_name, architecture, " ".join(a2p[architecture]))))
        print()


def parse_nfu(architecture):
    cnf = Config()
    # utils/hpodder_1.1.5.0: Not-For-Us [optional:out-of-date]
    r = re.compile(r"^\w+/([^_]+)_.*: Not-For-Us")

    ret = set()

    filename = "%s/%s-all.txt" % (cnf["Cruft-Report::Options::Wanna-Build-Dump"], architecture)

    # Not all architectures may have a wanna-build dump, so we want to ignore missin
    # files
    if os.path.exists(filename):
        with open(filename) as f:
            for line in f:
                if line[0] == ' ':
                    continue

                m = r.match(line)
                if m:
                    ret.add(m.group(1))
    else:
        utils.warn("No wanna-build dump file for architecture %s" % architecture)
    return ret

################################################################################


def do_newer_version(lowersuite_name, highersuite_name, code, session):
    list = newer_version(lowersuite_name, highersuite_name, session)
    if len(list) > 0:
        nv_to_remove = []
        title = "Newer version in %s" % lowersuite_name
        print(title)
        print("-" * len(title))
        print()
        for i in list:
            (source, higher_version, lower_version) = i
            print(" o %s (%s, %s)" % (source, higher_version, lower_version))
            nv_to_remove.append(source)
        print()
        print("Suggested command:")
        print(" dak rm -m \"[auto-cruft] %s\" -s %s %s" % (code, highersuite_name,
                                                           " ".join(nv_to_remove)))
        print()

################################################################################


def reportWithoutSource(suite_name, suite_id, session, rdeps=False):
    rows = query_without_source(suite_id, session)
    title = 'packages without source in suite %s' % suite_name
    if rows.rowcount > 0:
        print('%s\n%s\n' % (title, '-' * len(title)))
    message = '"[auto-cruft] no longer built from source"'
    for row in rows:
        (package, version) = row
        print("* package %s in version %s is no longer built from source" %
            (package, version))
        print("  - suggested command:")
        print("    dak rm -m %s -s %s -a all -p -R -b %s" %
            (message, suite_name, package))
        if rdeps:
            if utils.check_reverse_depends([package], suite_name, [], session, True):
                print()
            else:
                print("  - No dependency problem found\n")
        else:
            print()


def queryNewerAll(suite_name, session):
    """searches for arch != all packages that have an arch == all
    package with a higher version in the same suite"""

    query = """
select bab1.package, bab1.version as oldver,
    array_to_string(array_agg(a.arch_string), ',') as oldarch,
    bab2.version as newver
    from bin_associations_binaries bab1
    join bin_associations_binaries bab2
        on bab1.package = bab2.package and bab1.version < bab2.version and
        bab1.suite = bab2.suite and bab1.architecture > 2 and
        bab2.architecture = 2
    join architecture a on bab1.architecture = a.id
    join suite s on bab1.suite = s.id
    where s.suite_name = :suite_name
    group by bab1.package, oldver, bab1.suite, newver"""
    return session.execute(query, {'suite_name': suite_name})


def reportNewerAll(suite_name, session):
    rows = queryNewerAll(suite_name, session)
    title = 'obsolete arch any packages in suite %s' % suite_name
    if rows.rowcount > 0:
        print('%s\n%s\n' % (title, '-' * len(title)))
    message = '"[auto-cruft] obsolete arch any package"'
    for row in rows:
        (package, oldver, oldarch, newver) = row
        print("* package %s is arch any in version %s but arch all in version %s" %
            (package, oldver, newver))
        print("  - suggested command:")
        print("    dak rm -o -m %s -s %s -a %s -p -b %s\n" %
            (message, suite_name, oldarch, package))


def reportNBS(suite_name, suite_id, rdeps=False):
    session = DBConn().session()
    nbsRows = queryNBS(suite_id, session)
    title = 'NBS packages in suite %s' % suite_name
    if nbsRows.rowcount > 0:
        print('%s\n%s\n' % (title, '-' * len(title)))
    for row in nbsRows:
        (pkg_list, arch_list, source, version) = row
        pkg_string = ' '.join(pkg_list)
        arch_string = ','.join(arch_list)
        print("* source package %s version %s no longer builds" %
            (source, version))
        print("  binary package(s): %s" % pkg_string)
        print("  on %s" % arch_string)
        print("  - suggested command:")
        message = '"[auto-cruft] NBS (no longer built by %s)"' % source
        print("    dak rm -o -m %s -s %s -a %s -p -R -b %s" %
            (message, suite_name, arch_string, pkg_string))
        if rdeps:
            if utils.check_reverse_depends(pkg_list, suite_name, arch_list, session, True):
                print()
            else:
                print("  - No dependency problem found\n")
        else:
            print()
    session.close()


def reportNBSMetadata(suite_name, suite_id, session, rdeps=False):
    rows = queryNBS_metadata(suite_id, session)
    title = 'NBS packages (from metadata) in suite %s' % suite_name
    if rows.rowcount > 0:
        print('%s\n%s\n' % (title, '-' * len(title)))
    for row in rows:
        (packages, architecture, source, version) = row
        print("* source package %s version %s no longer builds" %
            (source, version))
        print("  binary package(s): %s" % packages)
        print("  on %s" % architecture)
        print("  - suggested command:")
        message = '"[auto-cruft] NBS (no longer built by %s - based on source metadata)"' % source
        print("    dak rm -o -m %s -s %s -a %s -p -R -b %s" %
            (message, suite_name, architecture, packages))
        if rdeps:
            archs = [architecture]
            if architecture == "all":
                # when archs is None, rdeps are checked on all archs in the suite
                archs = None
            if utils.check_reverse_depends(packages.split(), suite_name, archs, session, True):
                print()
            else:
                print("  - No dependency problem found\n")
        else:
            print()


def reportAllNBS(suite_name, suite_id, session, rdeps=False):
    reportWithoutSource(suite_name, suite_id, session, rdeps)
    reportNewerAll(suite_name, session)
    reportNBS(suite_name, suite_id, rdeps)

################################################################################


def do_dubious_nbs(dubious_nbs):
    print("Dubious NBS")
    print("-----------")
    print()

    version_sort_key = functools.cmp_to_key(apt_pkg.version_compare)
    for source in sorted(dubious_nbs):
        print(" * %s_%s builds: %s" % (source,
                                       source_versions.get(source, "??"),
                                       source_binaries.get(source, "(source does not exist)")))
        print("      won't admit to building:")
        versions = sorted(dubious_nbs[source], key=version_sort_key)
        for version in versions:
            packages = sorted(dubious_nbs[source][version])
            print("        o %s: %s" % (version, ", ".join(packages)))

        print()

################################################################################


def obsolete_source(suite_name, session):
    """returns obsolete source packages for suite_name without binaries
    in the same suite sorted by install_date; install_date should help
    detecting source only (or binary throw away) uploads; duplicates in
    the suite are skipped

    subquery 'source_suite_unique' returns source package names from
    suite without duplicates; the rationale behind is that neither
    cruft-report nor rm cannot handle duplicates (yet)"""

    query = """
WITH source_suite_unique AS
    (SELECT source, suite
        FROM source_suite GROUP BY source, suite HAVING count(*) = 1)
SELECT ss.src, ss.source, ss.version,
    to_char(ss.install_date, 'YYYY-MM-DD') AS install_date
    FROM source_suite ss
    JOIN source_suite_unique ssu
        ON ss.source = ssu.source AND ss.suite = ssu.suite
    JOIN suite s ON s.id = ss.suite
    LEFT JOIN bin_associations_binaries bab
        ON ss.src = bab.source AND ss.suite = bab.suite
    WHERE s.suite_name = :suite_name AND bab.id IS NULL
      AND now() - ss.install_date > '1 day'::interval
    ORDER BY install_date"""
    args = {'suite_name': suite_name}
    return session.execute(query, args)


def source_bin(source, session):
    """returns binaries built by source for all or no suite grouped and
    ordered by package name"""

    query = """
SELECT b.package
    FROM binaries b
    JOIN src_associations_src sas ON b.source = sas.src
    WHERE sas.source = :source
    GROUP BY b.package
    ORDER BY b.package"""
    args = {'source': source}
    return session.execute(query, args)


def newest_source_bab(suite_name, package, session):
    """returns newest source that builds binary package in suite grouped
    and sorted by source and package name"""

    query = """
SELECT sas.source, MAX(sas.version) AS srcver
    FROM src_associations_src sas
    JOIN bin_associations_binaries bab ON sas.src = bab.source
    JOIN suite s on s.id = bab.suite
    WHERE s.suite_name = :suite_name AND bab.package = :package
        GROUP BY sas.source, bab.package
        ORDER BY sas.source, bab.package"""
    args = {'suite_name': suite_name, 'package': package}
    return session.execute(query, args)


def report_obsolete_source(suite_name, session):
    rows = obsolete_source(suite_name, session)
    if rows.rowcount == 0:
        return
    print("""Obsolete source packages in suite %s
----------------------------------%s\n""" %
        (suite_name, '-' * len(suite_name)))
    for os_row in rows.fetchall():
        (src, old_source, version, install_date) = os_row
        print(" * obsolete source %s version %s installed at %s" %
            (old_source, version, install_date))
        for sb_row in source_bin(old_source, session):
            (package, ) = sb_row
            print("   - has built binary %s" % package)
            for nsb_row in newest_source_bab(suite_name, package, session):
                (new_source, srcver) = nsb_row
                print("     currently built by source %s version %s" %
                    (new_source, srcver))
        print("   - suggested command:")
        rm_opts = "-S -p -m \"[auto-cruft] obsolete source package\""
        print("     dak rm -s %s %s %s\n" % (suite_name, rm_opts, old_source))


def get_suite_binaries(suite, session):
    # Initalize a large hash table of all binary packages
    binaries = {}

    print("Getting a list of binary packages in %s..." % suite.suite_name)
    q = session.execute("""SELECT distinct b.package
                             FROM binaries b, bin_associations ba
                            WHERE ba.suite = :suiteid AND ba.bin = b.id""",
                           {'suiteid': suite.suite_id})
    for i in q.fetchall():
        binaries[i[0]] = ""

    return binaries

################################################################################


def report_outdated_nonfree(suite, session, rdeps=False):

    packages = {}
    query = """WITH outdated_sources AS (
                 SELECT s.source, s.version, s.id
                 FROM source s
                 JOIN src_associations sa ON sa.source = s.id
                 WHERE sa.suite IN (
                   SELECT id
                   FROM suite
                   WHERE suite_name = :suite )
                 AND sa.created < (now() - interval :delay)
                 EXCEPT SELECT s.source, max(s.version) AS version, max(s.id)
                 FROM source s
                 JOIN src_associations sa ON sa.source = s.id
                 WHERE sa.suite IN (
                   SELECT id
                   FROM suite
                   WHERE suite_name = :suite )
                 AND sa.created < (now() - interval :delay)
                 GROUP BY s.source ),
               binaries AS (
                 SELECT b.package, s.source, (
                   SELECT a.arch_string
                   FROM architecture a
                   WHERE a.id = b.architecture ) AS arch
                 FROM binaries b
                 JOIN outdated_sources s ON s.id = b.source
                 JOIN bin_associations ba ON ba.bin = b.id
                 JOIN override o ON o.package = b.package AND o.suite = ba.suite
                 WHERE ba.suite IN (
                   SELECT id
                   FROM suite
                   WHERE suite_name = :suite )
                 AND o.component IN (
                   SELECT id
                   FROM component
                   WHERE name = 'non-free' ) )
               SELECT DISTINCT package, source, arch
               FROM binaries
               ORDER BY source, package, arch"""

    res = session.execute(query, {'suite': suite, 'delay': "'15 days'"})
    for package in res:
        binary = package[0]
        source = package[1]
        arch = package[2]
        if arch == 'all':
            continue
        if source not in packages:
            packages[source] = {}
        if binary not in packages[source]:
            packages[source][binary] = set()
        packages[source][binary].add(arch)
    if packages:
        title = 'Outdated non-free binaries in suite %s' % suite
        message = '"[auto-cruft] outdated non-free binaries"'
        print('%s\n%s\n' % (title, '-' * len(title)))
        for source in sorted(packages):
            archs = set()
            binaries = set()
            print('* package %s has outdated non-free binaries' % source)
            print('  - suggested command:')
            for binary in sorted(packages[source]):
                binaries.add(binary)
                archs = archs.union(packages[source][binary])
            print('    dak rm -o -m %s -s %s -a %s -p -R -b %s' %
                   (message, suite, ','.join(archs), ' '.join(binaries)))
            if rdeps:
                if utils.check_reverse_depends(list(binaries), suite, archs, session, True):
                    print()
                else:
                    print("  - No dependency problem found\n")
            else:
                print()

################################################################################


def main():
    global suite, suite_id, source_binaries, source_versions

    cnf = Config()

    Arguments = [('h', "help", "Cruft-Report::Options::Help"),
                 ('m', "mode", "Cruft-Report::Options::Mode", "HasArg"),
                 ('R', "rdep-check", "Cruft-Report::Options::Rdep-Check"),
                 ('s', "suite", "Cruft-Report::Options::Suite", "HasArg"),
                 ('w', "wanna-build-dump", "Cruft-Report::Options::Wanna-Build-Dump", "HasArg")]
    for i in ["help", "Rdep-Check"]:
        key = "Cruft-Report::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    cnf["Cruft-Report::Options::Suite"] = cnf.get("Dinstall::DefaultSuite", "unstable")

    if "Cruft-Report::Options::Mode" not in cnf:
        cnf["Cruft-Report::Options::Mode"] = "daily"

    if "Cruft-Report::Options::Wanna-Build-Dump" not in cnf:
        cnf["Cruft-Report::Options::Wanna-Build-Dump"] = "/srv/ftp-master.debian.org/scripts/nfu"

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.subtree("Cruft-Report::Options")
    if Options["Help"]:
        usage()

    if Options["Rdep-Check"]:
        rdeps = True
    else:
        rdeps = False

    # Set up checks based on mode
    if Options["Mode"] == "daily":
        checks = ["nbs", "nviu", "nvit", "obsolete source", "outdated non-free", "nfu", "nbs metadata"]
    elif Options["Mode"] == "full":
        checks = ["nbs", "nviu", "nvit", "obsolete source", "outdated non-free", "nfu", "nbs metadata", "dubious nbs", "bnb", "bms", "anais"]
    elif Options["Mode"] == "bdo":
        checks = ["nbs",  "obsolete source"]
    else:
        utils.warn("%s is not a recognised mode - only 'full', 'daily' or 'bdo' are understood." % (Options["Mode"]))
        usage(1)

    session = DBConn().session()

    bin_pkgs = {}
    src_pkgs = {}
    bin2source = {}
    bins_in_suite = {}
    nbs = {}
    source_versions = {}

    anais_output = ""

    nfu_packages = {}

    suite = get_suite(Options["Suite"].lower(), session)
    if not suite:
        utils.fubar("Cannot find suite %s" % Options["Suite"].lower())

    suite_id = suite.suite_id
    suite_name = suite.suite_name.lower()

    if "obsolete source" in checks:
        report_obsolete_source(suite_name, session)

    if "nbs" in checks:
        reportAllNBS(suite_name, suite_id, session, rdeps)

    if "nbs metadata" in checks:
        reportNBSMetadata(suite_name, suite_id, session, rdeps)

    if "outdated non-free" in checks:
        report_outdated_nonfree(suite_name, session, rdeps)

    bin_not_built = {}

    if "bnb" in checks:
        bins_in_suite = get_suite_binaries(suite, session)

    # Checks based on the Sources files
    components = get_component_names(session)
    for component in components:
        filename = "%s/dists/%s/%s/source/Sources" % (suite.archive.path, suite_name, component)
        filename = utils.find_possibly_compressed_file(filename)
        with apt_pkg.TagFile(filename) as Sources:
            while Sources.step():
                source = Sources.section.find('Package')
                source_version = Sources.section.find('Version')
                architecture = Sources.section.find('Architecture')
                binaries = Sources.section.find('Binary')
                binaries_list = [i.strip() for i in binaries.split(',')]

                if "bnb" in checks:
                    # Check for binaries not built on any architecture.
                    for binary in binaries_list:
                        if binary not in bins_in_suite:
                            bin_not_built.setdefault(source, {})
                            bin_not_built[source][binary] = ""

                if "anais" in checks:
                    anais_output += do_anais(architecture, binaries_list, source, session)

                # build indices for checking "no source" later
                source_index = component + '/' + source
                src_pkgs[source] = source_index
                for binary in binaries_list:
                    bin_pkgs[binary] = source
                source_binaries[source] = binaries
                source_versions[source] = source_version

    # Checks based on the Packages files
    check_components = components[:]
    if suite_name != "experimental":
        check_components.append('main/debian-installer')

    for component in check_components:
        architectures = [a.arch_string for a in get_suite_architectures(suite_name,
                                                                         skipsrc=True, skipall=True,
                                                                         session=session)]
        for architecture in architectures:
            if component == 'main/debian-installer' and re.match("kfreebsd", architecture):
                continue

            if "nfu" in checks:
                nfu_packages.setdefault(architecture, [])
                nfu_entries = parse_nfu(architecture)

            filename = "%s/dists/%s/%s/binary-%s/Packages" % (suite.archive.path, suite_name, component, architecture)
            filename = utils.find_possibly_compressed_file(filename)
            with apt_pkg.TagFile(filename) as Packages:
                while Packages.step():
                    package = Packages.section.find('Package')
                    source = Packages.section.find('Source', "")
                    version = Packages.section.find('Version')
                    if source == "":
                        source = package
                    if package in bin2source and \
                           apt_pkg.version_compare(version, bin2source[package]["version"]) > 0:
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
                    if package not in bin_pkgs:
                        nbs.setdefault(source, {})
                        nbs[source].setdefault(package, {})
                        nbs[source][package][version] = ""
                    else:
                        if "nfu" in checks:
                            if package in nfu_entries and \
                                   version != source_versions[source]: # only suggest to remove out-of-date packages
                                nfu_packages[architecture].append((package, version, source_versions[source]))

    # Distinguish dubious (version numbers match) and 'real' NBS (they don't)
    dubious_nbs = {}
    version_sort_key = functools.cmp_to_key(apt_pkg.version_compare)
    for source in nbs:
        for package in nbs[source]:
            latest_version = max(nbs[source][package], key=version_sort_key)
            source_version = source_versions.get(source, "0")
            if apt_pkg.version_compare(latest_version, source_version) == 0:
                add_nbs(dubious_nbs, source, latest_version, package, suite_id, session)

    if "nviu" in checks:
        do_newer_version('unstable', 'experimental', 'NVIU', session)

    if "nvit" in checks:
        do_newer_version('testing', 'testing-proposed-updates', 'NVIT', session)

    ###

    if Options["Mode"] == "full":
        print("=" * 75)
        print()

    if "nfu" in checks:
        do_nfu(nfu_packages)

    if "bnb" in checks:
        print("Unbuilt binary packages")
        print("-----------------------")
        print()
        for source in sorted(bin_not_built):
            binaries = sorted(bin_not_built[source])
            print(" o %s: %s" % (source, ", ".join(binaries)))
        print()

    if "bms" in checks:
        report_multiple_source(suite)

    if "anais" in checks:
        print("Architecture Not Allowed In Source")
        print("----------------------------------")
        print(anais_output)
        print()

    if "dubious nbs" in checks:
        do_dubious_nbs(dubious_nbs)


################################################################################

if __name__ == '__main__':
    main()
