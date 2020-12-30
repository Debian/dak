#! /usr/bin/env python3

"""
Check for obsolete binary packages

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000-2006 James Troup <james@nocrew.org>
@copyright: 2009      Torsten Werner <twerner@debian.org>
@copyright: 2015      Niels Thykier <niels@thykier.net>
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

# | priviledged positions? What privilege? The honour of working harder
# | than most people for absolutely no recognition?
#
# Manoj Srivastava <srivasta@debian.org> in <87lln8aqfm.fsf@glaurung.internal.golden-gryphon.com>

################################################################################

import sqlalchemy.sql as sql
import sys
import apt_pkg
from itertools import chain, product
from collections import defaultdict

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils
from daklib.cruft import *
from daklib.rm import remove, ReverseDependencyChecker

################################################################################


def usage(exit_code=0):
    print("""Usage: dak auto-decruft
Automatic removal of common kinds of cruft

  -h, --help                show this help and exit.
  -n, --dry-run             don't do anything, just show what would have been done
  -s, --suite=SUITE         check suite SUITE.
  --if-newer-version-in OS  remove all packages in SUITE with a lower version than
                            in OS (e.g. -s experimental --if-newer-version-in
                            unstable)
  --if-newer-version-in-rm-msg RMMSG
                            use RMMSG in the removal message (e.g. "NVIU")
  --decruft-equal-versions  use with --if-newer-version-in to also decruft versions
                            that are identical in both suites.
  """)
    sys.exit(exit_code)

################################################################################


def compute_sourceless_groups(suite_id, session):
    """Find binaries without a source

    @type suite_id: int
    @param suite_id: The id of the suite denoted by suite_name

    @type session: SQLA Session
    @param session: The database session in use
    """""
    rows = query_without_source(suite_id, session)
    message = '[auto-cruft] no longer built from source, no reverse dependencies'
    arch = get_architecture('all', session=session)
    arch_all_id_tuple = tuple([arch.arch_id])
    arch_all_list = ["all"]
    for row in rows:
        package = row[0]
        group_info = {
            "name": "sourceless:%s" % package,
            "packages": tuple([package]),
            "architectures": arch_all_list,
            "architecture_ids": arch_all_id_tuple,
            "message": message,
            "removal_request": {
                package: arch_all_list,
            },
        }
        yield group_info


def compute_nbs_groups(suite_id, suite_name, session):
    """Find binaries no longer built

    @type suite_id: int
    @param suite_id: The id of the suite denoted by suite_name

    @type suite_name: string
    @param suite_name: The name of the suite to remove from

    @type session: SQLA Session
    @param session: The database session in use
    """""
    rows = queryNBS(suite_id, session)
    arch2ids = dict((a.arch_string, a.arch_id) for a in get_suite_architectures(suite_name))

    for row in rows:
        (pkg_list, arch_list, source, _) = row
        message = '[auto-cruft] NBS (no longer built by %s, no reverse dependencies)' % source
        removal_request = dict((pkg, arch_list) for pkg in pkg_list)
        group_info = {
            "name": "NBS:%s" % source,
            "packages": tuple(sorted(pkg_list)),
            "architectures": sorted(arch_list),
            "architecture_ids": tuple(arch2ids[arch] for arch in arch_list),
            "message": message,
            "removal_request": removal_request,
        }
        yield group_info


def remove_groups(groups, suite_id, suite_name, session):
    for group in groups:
        message = group["message"]
        params = {
            "architecture_ids": group["architecture_ids"],
            "packages": group["packages"],
            "suite_id": suite_id
        }
        q = session.execute(sql.text("""
            SELECT b.package, b.version, a.arch_string, b.id
            FROM binaries b
                JOIN bin_associations ba ON b.id = ba.bin
                JOIN architecture a ON b.architecture = a.id
                JOIN suite su ON ba.suite = su.id
            WHERE a.id IN :architecture_ids AND b.package IN :packages AND su.id = :suite_id
            """), params)

        remove(session, message, [suite_name], list(q), partial=True, whoami="DAK's auto-decrufter")


def dedup(*args):
    seen = set()
    for iterable in args:
        for value in iterable:
            if value not in seen:
                seen.add(value)
                yield value


def merge_group(groupA, groupB):
    """Merges two removal groups into one

    Note that some values are taken entirely from groupA (e.g. name and message)

    @type groupA: dict
    @param groupA: A removal group

    @type groupB: dict
    @param groupB: Another removal group

    @rtype: dict
    @returns: A merged group
    """
    pkg_list = sorted(dedup(groupA["packages"], groupB["packages"]))
    arch_list = sorted(dedup(groupA["architectures"], groupB["architectures"]))
    arch_list_id = dedup(groupA["architecture_ids"], groupB["architecture_ids"])
    removalA = groupA["removal_request"]
    removalB = groupB["removal_request"]
    new_removal = {}
    for pkg in dedup(removalA, removalB):
        listA = removalA[pkg] if pkg in removalA else []
        listB = removalB[pkg] if pkg in removalB else []
        new_removal[pkg] = sorted(dedup(listA, listB))

    merged_group = {
        "name": groupA["name"],
        "packages": tuple(pkg_list),
        "architectures": arch_list,
        "architecture_ids": tuple(arch_list_id),
        "message": groupA["message"],
        "removal_request": new_removal,
    }

    return merged_group


def auto_decruft_suite(suite_name, suite_id, session, dryrun, debug):
    """Run the auto-decrufter on a given suite

    @type suite_name: string
    @param suite_name: The name of the suite to remove from

    @type suite_id: int
    @param suite_id: The id of the suite denoted by suite_name

    @type session: SQLA Session
    @param session: The database session in use

    @type dryrun: bool
    @param dryrun: If True, just print the actions rather than actually doing them

    @type debug: bool
    @param debug: If True, print some extra information
    """
    all_architectures = [a.arch_string for a in get_suite_architectures(suite_name)]
    pkg_arch2groups = defaultdict(set)
    group_order = []
    groups = {}
    full_removal_request = []
    group_generator = chain(
        compute_sourceless_groups(suite_id, session),
        compute_nbs_groups(suite_id, suite_name, session)
    )
    for group in group_generator:
        group_name = group["name"]
        pkgs = group["packages"]
        affected_archs = group["architectures"]
        # If we remove an arch:all package, then the breakage can occur on any
        # of the architectures.
        if "all" in affected_archs:
            affected_archs = all_architectures
        for pkg_arch in product(pkgs, affected_archs):
            pkg_arch2groups[pkg_arch].add(group_name)
        if group_name not in groups:
            groups[group_name] = group
            group_order.append(group_name)
        else:
            # This case usually happens when versions differ between architectures...
            if debug:
                print("N: Merging group %s" % (group_name))
            groups[group_name] = merge_group(groups[group_name], group)

    for group_name in group_order:
        removal_request = groups[group_name]["removal_request"]
        full_removal_request.extend(removal_request.items())

    if not groups:
        if debug:
            print("N: Found no candidates")
        return

    if debug:
        print("N: Considering to remove the following packages:")
        for group_name in sorted(groups):
            group_info = groups[group_name]
            pkgs = group_info["packages"]
            archs = group_info["architectures"]
            print("N: * %s: %s [%s]" % (group_name, ", ".join(pkgs), " ".join(archs)))

    if debug:
        print("N: Compiling ReverseDependencyChecker (RDC) - please hold ...")
    rdc = ReverseDependencyChecker(session, suite_name)
    if debug:
        print("N: Computing initial breakage...")

    breakage = rdc.check_reverse_depends(full_removal_request)
    while breakage:
        by_breakers = [(len(breakage[x]), x, breakage[x]) for x in breakage]
        by_breakers.sort(reverse=True)
        if debug:
            print("N: - Removal would break %s (package, architecture)-pairs" % (len(breakage)))
            print("N: - full breakage:")
            for _, breaker, broken in by_breakers:
                bname = "%s/%s" % breaker
                broken_str = ", ".join("%s/%s" % b for b in sorted(broken))
                print("N:    * %s => %s" % (bname, broken_str))

        averted_breakage = set()

        for _, package_arch, breakage in by_breakers:
            if breakage <= averted_breakage:
                # We already avoided this break
                continue
            guilty_groups = pkg_arch2groups[package_arch]

            if not guilty_groups:
                utils.fubar("Cannot figure what group provided %s" % str(package_arch))

            if debug:
                # Only output it, if it truly a new group being discarded
                # - a group can reach this part multiple times, if it breaks things on
                #   more than one architecture.  This being rather common in fact.
                already_discard = True
                if any(group_name for group_name in guilty_groups if group_name in groups):
                    already_discard = False

                if not already_discard:
                    avoided = sorted(breakage - averted_breakage)
                    print("N: - skipping removal of %s (breakage: %s)" % (", ".join(sorted(guilty_groups)), str(avoided)))

            averted_breakage |= breakage
            for group_name in guilty_groups:
                if group_name in groups:
                    del groups[group_name]

        if not groups:
            if debug:
                print("N: Nothing left to remove")
            return

        if debug:
            print("N: Now considering to remove: %s" % str(", ".join(sorted(groups.keys()))))

        # Rebuild the removal request with the remaining groups and off
        # we go to (not) break the world once more time
        full_removal_request = []
        for group_info in groups.values():
            full_removal_request.extend(group_info["removal_request"].items())
        breakage = rdc.check_reverse_depends(full_removal_request)

    if debug:
        print("N: Removal looks good")

    if dryrun:
        print("Would remove the equivalent of:")
        for group_name in group_order:
            if group_name not in groups:
                continue
            group_info = groups[group_name]
            pkgs = group_info["packages"]
            archs = group_info["architectures"]
            message = group_info["message"]

            # Embed the -R just in case someone wants to run it manually later
            print('    dak rm -m "{message}" -s {suite} -a {architectures} -p -R -b {packages}'.format(
                message=message, suite=suite_name,
                architectures=",".join(archs), packages=" ".join(pkgs),
            ))

        print()
        print("Note: The removals may be interdependent.  A non-breaking result may require the execution of all")
        print("of the removals")
    else:
        remove_groups(groups.values(), suite_id, suite_name, session)


def sources2removals(source_list, suite_id, session):
    """Compute removals items given a list of names of source packages

    @type source_list: list
    @param source_list: A list of names of source packages

    @type suite_id: int
    @param suite_id: The id of the suite from which these sources should be removed

    @type session: SQLA Session
    @param session: The database session in use

    @rtype: list
    @return: A list of items to be removed to remove all sources and their binaries from the given suite
    """
    to_remove = []
    params = {"suite_id": suite_id, "sources": tuple(source_list)}
    q = session.execute(sql.text("""
                    SELECT s.source, s.version, 'source', s.id
                    FROM source s
                         JOIN src_associations sa ON sa.source = s.id
                    WHERE sa.suite = :suite_id AND s.source IN :sources"""), params)
    to_remove.extend(q)
    q = session.execute(sql.text("""
                    SELECT b.package, b.version, a.arch_string, b.id
                    FROM binaries b
                         JOIN bin_associations ba ON b.id = ba.bin
                         JOIN architecture a ON b.architecture = a.id
                         JOIN source s ON b.source = s.id
                    WHERE ba.suite = :suite_id AND s.source IN :sources"""), params)
    to_remove.extend(q)
    return to_remove


def decruft_newer_version_in(othersuite, suite_name, suite_id, rm_msg, session, dryrun, decruft_equal_versions):
    """Compute removals items given a list of names of source packages

    @type othersuite: str
    @param othersuite: The name of the suite to compare with (e.g. "unstable" for "NVIU")

    @type suite: str
    @param suite: The name of the suite from which to do removals (e.g. "experimental" for "NVIU")

    @type suite_id: int
    @param suite_id: The id of the suite from which these sources should be removed

    @type rm_msg: str
    @param rm_msg: The removal message (or tag, e.g. "NVIU")

    @type session: SQLA Session
    @param session: The database session in use

    @type dryrun: bool
    @param dryrun: If True, just print the actions rather than actually doing them

    @type decruft_equal_versions: bool
    @param decruft_equal_versions: If True, use >= instead of > for finding decruftable packages.
    """
    nvi_list = [x[0] for x in newer_version(othersuite, suite_name, session, include_equal=decruft_equal_versions)]
    if nvi_list:
        message = "[auto-cruft] %s" % rm_msg
        if dryrun:
            print("    dak rm -m \"%s\" -s %s %s" % (message, suite_name, " ".join(nvi_list)))
        else:
            removals = sources2removals(nvi_list, suite_id, session)
            remove(session, message, [suite_name], removals, whoami="DAK's auto-decrufter")

################################################################################


def main():
    global Options
    cnf = Config()

    Arguments = [('h', "help", "Auto-Decruft::Options::Help"),
                 ('n', "dry-run", "Auto-Decruft::Options::Dry-Run"),
                 ('d', "debug", "Auto-Decruft::Options::Debug"),
                 ('s', "suite", "Auto-Decruft::Options::Suite", "HasArg"),
                 # The "\0" seems to be the only way to disable short options.
                 ("\0", 'if-newer-version-in', "Auto-Decruft::Options::OtherSuite", "HasArg"),
                 ("\0", 'if-newer-version-in-rm-msg', "Auto-Decruft::Options::OtherSuiteRMMsg", "HasArg"),
                 ("\0", 'decruft-equal-versions', "Auto-Decruft::Options::OtherSuiteDecruftEqual")
                ]
    for i in ["help", "Dry-Run", "Debug", "OtherSuite", "OtherSuiteRMMsg", "OtherSuiteDecruftEqual"]:
        key = "Auto-Decruft::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    cnf["Auto-Decruft::Options::Suite"] = cnf.get("Dinstall::DefaultSuite", "unstable")

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.subtree("Auto-Decruft::Options")
    if Options["Help"]:
        usage()

    debug = False
    dryrun = False
    decruft_equal_versions = False
    if Options["Dry-Run"]:
        dryrun = True
    if Options["Debug"]:
        debug = True
    if Options["OtherSuiteDecruftEqual"]:
        decruft_equal_versions = True

    if Options["OtherSuite"] and not Options["OtherSuiteRMMsg"]:
        utils.fubar("--if-newer-version-in requires --if-newer-version-in-rm-msg")

    session = DBConn().session()

    suite = get_suite(Options["Suite"].lower(), session)
    if not suite:
        utils.fubar("Cannot find suite %s" % Options["Suite"].lower())

    suite_id = suite.suite_id
    suite_name = suite.suite_name.lower()

    auto_decruft_suite(suite_name, suite_id, session, dryrun, debug)

    if Options["OtherSuite"]:
        osuite = get_suite(Options["OtherSuite"].lower(), session).suite_name
        decruft_newer_version_in(osuite, suite_name, suite_id, Options["OtherSuiteRMMsg"], session, dryrun, decruft_equal_versions)

    if not dryrun:
        session.commit()

################################################################################


if __name__ == '__main__':
    main()
