"""General purpose package removal code for ftpmaster

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
@copyright: 2010 Alexander Reichle-Schmehl <tolimar@debian.org>
@copyright: 2015      Niels Thykier <niels@thykier.net>
@license: GNU General Public License version 2 or later
"""
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
# Copyright (C) 2010 Alexander Reichle-Schmehl <tolimar@debian.org>

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

# From: Andrew Morton <akpm@osdl.org>
# Subject: 2.6.6-mm5
# To: linux-kernel@vger.kernel.org
# Date: Sat, 22 May 2004 01:36:36 -0700
# X-Mailer: Sylpheed version 0.9.7 (GTK+ 1.2.10; i386-redhat-linux-gnu)
#
# [...]
#
# Although this feature has been around for a while it is new code, and the
# usual cautions apply.  If it munches all your files please tell Jens and
# he'll type them in again for you.

################################################################################

import apt_pkg
import fcntl
import functools
import sqlalchemy.sql as sql
import email.utils
from re import sub
from collections import defaultdict
from .regexes import re_build_dep_arch

from daklib.dbconn import *
from daklib import utils
from daklib.regexes import re_bin_only_nmu
import debianbts as bts

################################################################################


class ReverseDependencyChecker(object):
    """A bulk tester for reverse dependency checks

    This class is similar to the check_reverse_depends method from "utils".  However,
    it is primarily focused on facilitating bulk testing of reverse dependencies.
    It caches the state of the suite and then uses that as basis for answering queries.
    This saves a significant amount of time if multiple reverse dependency checks are
    required.
    """

    def __init__(self, session, suite):
        """Creates a new ReverseDependencyChecker instance

        This will spend a significant amount of time caching data.

        @type session: SQLA Session
        @param session: The database session in use

        @type suite: str
        @param suite: The name of the suite that is used as basis for removal tests.
        """
        self._session = session
        dbsuite = get_suite(suite, session)
        suite_archs2id = dict((x.arch_string, x.arch_id) for x in get_suite_architectures(suite))
        package_dependencies, arch_providers_of, arch_provided_by = self._load_package_information(session,
                                                                                                   dbsuite.suite_id,
                                                                                                   suite_archs2id)
        self._package_dependencies = package_dependencies
        self._arch_providers_of = arch_providers_of
        self._arch_provided_by = arch_provided_by
        self._archs_in_suite = set(suite_archs2id)

    @staticmethod
    def _load_package_information(session, suite_id, suite_archs2id):
        package_dependencies = defaultdict(lambda: defaultdict(set))
        arch_providers_of = defaultdict(lambda: defaultdict(set))
        arch_provided_by = defaultdict(lambda: defaultdict(set))
        source_deps = defaultdict(set)
        metakey_d = get_or_set_metadatakey("Depends", session)
        metakey_p = get_or_set_metadatakey("Provides", session)
        params = {
            'suite_id':     suite_id,
            'arch_all_id':  suite_archs2id['all'],
            'metakey_d_id': metakey_d.key_id,
            'metakey_p_id': metakey_p.key_id,
        }
        all_arches = set(suite_archs2id)
        all_arches.discard('source')

        package_dependencies['source'] = source_deps

        for architecture in all_arches:
            deps = defaultdict(set)
            providers_of = defaultdict(set)
            provided_by = defaultdict(set)
            arch_providers_of[architecture] = providers_of
            arch_provided_by[architecture] = provided_by
            package_dependencies[architecture] = deps

            params['arch_id'] = suite_archs2id[architecture]

            statement = sql.text('''
                    SELECT b.package,
                        (SELECT bmd.value FROM binaries_metadata bmd WHERE bmd.bin_id = b.id AND bmd.key_id = :metakey_d_id) AS depends,
                        (SELECT bmp.value FROM binaries_metadata bmp WHERE bmp.bin_id = b.id AND bmp.key_id = :metakey_p_id) AS provides
                        FROM binaries b
                        JOIN bin_associations ba ON b.id = ba.bin AND ba.suite = :suite_id
                        WHERE b.architecture = :arch_id OR b.architecture = :arch_all_id''')
            query = session.query('package', 'depends', 'provides'). \
                from_statement(statement).params(params)
            for package, depends, provides in query:

                if depends is not None:
                    try:
                        parsed_dep = []
                        for dep in apt_pkg.parse_depends(depends):
                            parsed_dep.append(frozenset(d[0] for d in dep))
                        deps[package].update(parsed_dep)
                    except ValueError as e:
                        print("Error for package %s: %s" % (package, e))
                # Maintain a counter for each virtual package.  If a
                # Provides: exists, set the counter to 0 and count all
                # provides by a package not in the list for removal.
                # If the counter stays 0 at the end, we know that only
                # the to-be-removed packages provided this virtual
                # package.
                if provides is not None:
                    for virtual_pkg in provides.split(","):
                        virtual_pkg = virtual_pkg.strip()
                        if virtual_pkg == package:
                            continue
                        provided_by[virtual_pkg].add(package)
                        providers_of[package].add(virtual_pkg)

        # Check source dependencies (Build-Depends and Build-Depends-Indep)
        metakey_bd = get_or_set_metadatakey("Build-Depends", session)
        metakey_bdi = get_or_set_metadatakey("Build-Depends-Indep", session)
        params = {
            'suite_id':    suite_id,
            'metakey_ids': (metakey_bd.key_id, metakey_bdi.key_id),
        }
        statement = sql.text('''
            SELECT s.source, string_agg(sm.value, ', ') as build_dep
               FROM source s
               JOIN source_metadata sm ON s.id = sm.src_id
               WHERE s.id in
                   (SELECT src FROM newest_src_association
                       WHERE suite = :suite_id)
                   AND sm.key_id in :metakey_ids
               GROUP BY s.id, s.source''')
        query = session.query('source', 'build_dep').from_statement(statement). \
            params(params)
        for source, build_dep in query:
            if build_dep is not None:
                # Remove [arch] information since we want to see breakage on all arches
                build_dep = re_build_dep_arch.sub("", build_dep)
                try:
                    parsed_dep = []
                    for dep in apt_pkg.parse_src_depends(build_dep):
                        parsed_dep.append(frozenset(d[0] for d in dep))
                    source_deps[source].update(parsed_dep)
                except ValueError as e:
                    print("Error for package %s: %s" % (source, e))

        return package_dependencies, arch_providers_of, arch_provided_by

    def check_reverse_depends(self, removal_requests):
        """Bulk check reverse dependencies

        Example:
          removal_request = {
            "eclipse-rcp": None, # means ALL architectures (incl. source)
            "eclipse": None, # means ALL architectures (incl. source)
            "lintian": ["source", "all"], # Only these two "architectures".
          }
          obj.check_reverse_depends(removal_request)

        @type removal_requests: dict (or a list of tuples)
        @param removal_requests: A dictionary mapping a package name to a list of architectures.  The list of
          architectures decides from which the package will be removed - if the list is empty the package will
          be removed on ALL architectures in the suite (including "source").

        @rtype: dict
        @return: A mapping of "removed package" (as a "(pkg, arch)"-tuple) to a set of broken
          broken packages (also as "(pkg, arch)"-tuple).  Note that the architecture values
          in these tuples /can/ be "source" to reflect a breakage in build-dependencies.
        """

        archs_in_suite = self._archs_in_suite
        removals_by_arch = defaultdict(set)
        affected_virtual_by_arch = defaultdict(set)
        package_dependencies = self._package_dependencies
        arch_providers_of = self._arch_providers_of
        arch_provided_by = self._arch_provided_by
        arch_provides2removal = defaultdict(lambda: defaultdict(set))
        dep_problems = defaultdict(set)
        src_deps = package_dependencies['source']
        src_removals = set()
        arch_all_removals = set()

        if isinstance(removal_requests, dict):
            removal_requests = removal_requests.items()

        for pkg, arch_list in removal_requests:
            if not arch_list:
                arch_list = archs_in_suite
            for arch in arch_list:
                if arch == 'source':
                    src_removals.add(pkg)
                    continue
                if arch == 'all':
                    arch_all_removals.add(pkg)
                    continue
                removals_by_arch[arch].add(pkg)
                if pkg in arch_providers_of[arch]:
                    affected_virtual_by_arch[arch].add(pkg)

        if arch_all_removals:
            for arch in archs_in_suite:
                if arch in ('all', 'source'):
                    continue
                removals_by_arch[arch].update(arch_all_removals)
                for pkg in arch_all_removals:
                    if pkg in arch_providers_of[arch]:
                        affected_virtual_by_arch[arch].add(pkg)

        if not removals_by_arch:
            # Nothing to remove => no problems
            return dep_problems

        for arch, removed_providers in affected_virtual_by_arch.items():
            provides2removal = arch_provides2removal[arch]
            removals = removals_by_arch[arch]
            for virtual_pkg, virtual_providers in arch_provided_by[arch].items():
                v = virtual_providers & removed_providers
                if len(v) == len(virtual_providers):
                    # We removed all the providers of virtual_pkg
                    removals.add(virtual_pkg)
                    # Pick one to take the blame for the removal
                    # - we sort for determinism, optimally we would prefer to blame the same package
                    #   to minimise the number of blamed packages.
                    provides2removal[virtual_pkg] = sorted(v)[0]

        for arch, removals in removals_by_arch.items():
            deps = package_dependencies[arch]
            provides2removal = arch_provides2removal[arch]

            # Check binary dependencies (Depends)
            for package, dependencies in deps.items():
                if package in removals:
                    continue
                for clause in dependencies:
                    if not (clause <= removals):
                        # Something probably still satisfies this relation
                        continue
                    # whoops, we seemed to have removed all packages that could possibly satisfy
                    # this relation.  Lets blame something for it
                    for dep_package in clause:
                        removal = dep_package
                        if dep_package in provides2removal:
                            removal = provides2removal[dep_package]
                        dep_problems[(removal, arch)].add((package, arch))

            for source, build_dependencies in src_deps.items():
                if source in src_removals:
                    continue
                for clause in build_dependencies:
                    if not (clause <= removals):
                        # Something probably still satisfies this relation
                        continue
                    # whoops, we seemed to have removed all packages that could possibly satisfy
                    # this relation.  Lets blame something for it
                    for dep_package in clause:
                        removal = dep_package
                        if dep_package in provides2removal:
                            removal = provides2removal[dep_package]
                        dep_problems[(removal, arch)].add((source, 'source'))

        return dep_problems


def remove(session, reason, suites, removals,
           whoami=None, partial=False, components=None, done_bugs=None, date=None,
           carbon_copy=None, close_related_bugs=False):
    """Batch remove a number of packages
    Verify that the files listed in the Files field of the .dsc are
    those expected given the announced Format.

    @type session: SQLA Session
    @param session: The database session in use

    @type reason: string
    @param reason: The reason for the removal (e.g. "[auto-cruft] NBS (no longer built by <source>)")

    @type suites: list
    @param suites: A list of the suite names in which the removal should occur

    @type removals: list
    @param removals: A list of the removals.  Each element should be a tuple (or list) of at least the following
        for 4 items from the database (in order): package, version, architecture, (database) id.
        For source packages, the "architecture" should be set to "source".

    @type partial: bool
    @param partial: Whether the removal is "partial" (e.g. architecture specific).

    @type components: list
    @param components: List of components involved in a partial removal.  Can be an empty list to not restrict the
        removal to any components.

    @type whoami: string
    @param whoami: The person (or entity) doing the removal.  Defaults to utils.whoami()

    @type date: string
    @param date: The date of the removal. Defaults to `date -R`

    @type done_bugs: list
    @param done_bugs: A list of bugs to be closed when doing this removal.

    @type close_related_bugs: bool
    @param done_bugs: Whether bugs related to the package being removed should be closed as well.  NB: Not implemented
      for more than one suite.

    @type carbon_copy: list
    @param carbon_copy: A list of mail addresses to CC when doing removals.  NB: all items are taken "as-is" unlike
        "dak rm".

    @rtype: None
    @return: Nothing
    """
    # Generate the summary of what's to be removed
    d = {}
    summary = ""
    sources = []
    binaries = []
    whitelists = []
    versions = []
    newest_source = ''
    suite_ids_list = []
    suites_list = utils.join_with_commas_and(suites)
    cnf = utils.get_conf()
    con_components = ''

    #######################################################################################################

    if not reason:
        raise ValueError("Empty removal reason not permitted")
    reason = reason.strip()

    if not removals:
        raise ValueError("Nothing to remove!?")

    if not suites:
        raise ValueError("Removals without a suite!?")

    if whoami is None:
        whoami = utils.whoami()

    if date is None:
        date = email.utils.formatdate()

    if partial and components:

        component_ids_list = []
        for componentname in components:
            component = get_component(componentname, session=session)
            if component is None:
                raise ValueError("component '%s' not recognised." % componentname)
            else:
                component_ids_list.append(component.component_id)
        if component_ids_list:
            con_components = "AND component IN (%s)" % ", ".join([str(i) for i in component_ids_list])

    for i in removals:
        package = i[0]
        version = i[1]
        architecture = i[2]
        if package not in d:
            d[package] = {}
        if version not in d[package]:
            d[package][version] = []
        if architecture not in d[package][version]:
            d[package][version].append(architecture)

    for package in sorted(d):
        versions = sorted(d[package], key=functools.cmp_to_key(apt_pkg.version_compare))
        for version in versions:
            d[package][version].sort(key=utils.ArchKey)
            summary += "%10s | %10s | %s\n" % (package, version, ", ".join(d[package][version]))
            if apt_pkg.version_compare(version, newest_source) > 0:
                newest_source = version

    for package in summary.split("\n"):
        for row in package.split("\n"):
            element = row.split("|")
            if len(element) == 3:
                if element[2].find("source") > 0:
                    sources.append("%s_%s" % tuple(elem.strip(" ") for elem in element[:2]))
                    element[2] = sub(r"source\s?,?", "", element[2]).strip(" ")
                if element[2]:
                    binaries.append("%s_%s [%s]" % tuple(elem.strip(" ") for elem in element))

    dsc_type_id = get_override_type('dsc', session).overridetype_id
    deb_type_id = get_override_type('deb', session).overridetype_id

    for suite in suites:
        s = get_suite(suite, session=session)
        if s is not None:
            suite_ids_list.append(s.suite_id)
            whitelists.append(s.mail_whitelist)

    #######################################################################################################
    log_filename = cnf["Rm::LogFile"]
    log822_filename = cnf["Rm::LogFile822"]
    with open(log_filename, "a") as logfile, open(log822_filename, "a") as logfile822:
        fcntl.lockf(logfile, fcntl.LOCK_EX)
        fcntl.lockf(logfile822, fcntl.LOCK_EX)

        logfile.write("=========================================================================\n")
        logfile.write("[Date: %s] [ftpmaster: %s]\n" % (date, whoami))
        logfile.write("Removed the following packages from %s:\n\n%s" % (suites_list, summary))
        if done_bugs:
            logfile.write("Closed bugs: %s\n" % (", ".join(done_bugs)))
        logfile.write("\n------------------- Reason -------------------\n%s\n" % reason)
        logfile.write("----------------------------------------------\n")

        logfile822.write("Date: %s\n" % date)
        logfile822.write("Ftpmaster: %s\n" % whoami)
        logfile822.write("Suite: %s\n" % suites_list)

        if sources:
            logfile822.write("Sources:\n")
            for source in sources:
                logfile822.write(" %s\n" % source)

        if binaries:
            logfile822.write("Binaries:\n")
            for binary in binaries:
                logfile822.write(" %s\n" % binary)

        logfile822.write("Reason: %s\n" % reason.replace('\n', '\n '))
        if done_bugs:
            logfile822.write("Bug: %s\n" % (", ".join(done_bugs)))

        for i in removals:
            package = i[0]
            architecture = i[2]
            package_id = i[3]
            for suite_id in suite_ids_list:
                if architecture == "source":
                    session.execute("DELETE FROM src_associations WHERE source = :packageid AND suite = :suiteid",
                                    {'packageid': package_id, 'suiteid': suite_id})
                else:
                    session.execute("DELETE FROM bin_associations WHERE bin = :packageid AND suite = :suiteid",
                                    {'packageid': package_id, 'suiteid': suite_id})
                # Delete from the override file
                if not partial:
                    if architecture == "source":
                        type_id = dsc_type_id
                    else:
                        type_id = deb_type_id
                    # TODO: Fix this properly to remove the remaining non-bind argument
                    session.execute("DELETE FROM override WHERE package = :package AND type = :typeid AND suite = :suiteid %s" % (con_components), {'package': package, 'typeid': type_id, 'suiteid': suite_id})

        session.commit()
        # ### REMOVAL COMPLETE - send mail time ### #

        # If we don't have a Bug server configured, we're done
        if "Dinstall::BugServer" not in cnf:
            if done_bugs or close_related_bugs:
                utils.warn("Cannot send mail to BugServer as Dinstall::BugServer is not configured")

            logfile.write("=========================================================================\n")
            logfile822.write("\n")
            return

        # read common subst variables for all bug closure mails
        Subst_common = {}
        Subst_common["__RM_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]
        Subst_common["__BUG_SERVER__"] = cnf["Dinstall::BugServer"]
        Subst_common["__CC__"] = "X-DAK: dak rm"
        if carbon_copy:
            Subst_common["__CC__"] += "\nCc: " + ", ".join(carbon_copy)
        Subst_common["__SUITE_LIST__"] = suites_list
        Subst_common["__SUBJECT__"] = "Removed package(s) from %s" % (suites_list)
        Subst_common["__ADMIN_ADDRESS__"] = cnf["Dinstall::MyAdminAddress"]
        Subst_common["__DISTRO__"] = cnf["Dinstall::MyDistribution"]
        Subst_common["__WHOAMI__"] = whoami

        # Send the bug closing messages
        if done_bugs:
            Subst_close_rm = Subst_common
            bcc = []
            if cnf.find("Dinstall::Bcc") != "":
                bcc.append(cnf["Dinstall::Bcc"])
            if cnf.find("Rm::Bcc") != "":
                bcc.append(cnf["Rm::Bcc"])
            if bcc:
                Subst_close_rm["__BCC__"] = "Bcc: " + ", ".join(bcc)
            else:
                Subst_close_rm["__BCC__"] = "X-Filler: 42"
            summarymail = "%s\n------------------- Reason -------------------\n%s\n" % (summary, reason)
            summarymail += "----------------------------------------------\n"
            Subst_close_rm["__SUMMARY__"] = summarymail

            for bug in done_bugs:
                Subst_close_rm["__BUG_NUMBER__"] = bug
                if close_related_bugs:
                    mail_message = utils.TemplateSubst(Subst_close_rm, cnf["Dir::Templates"] + "/rm.bug-close-with-related")
                else:
                    mail_message = utils.TemplateSubst(Subst_close_rm, cnf["Dir::Templates"] + "/rm.bug-close")
                utils.send_mail(mail_message, whitelists=whitelists)

        # close associated bug reports
        if close_related_bugs:
            Subst_close_other = Subst_common
            bcc = []
            wnpp = utils.parse_wnpp_bug_file()
            newest_source = re_bin_only_nmu.sub('', newest_source)
            if len(set(s.split("_", 1)[0] for s in sources)) == 1:
                source_pkg = source.split("_", 1)[0]
            else:
                logfile.write("=========================================================================\n")
                logfile822.write("\n")
                raise ValueError("Closing bugs for multiple source packages is not supported.  Please do it yourself.")
            if newest_source != '':
                Subst_close_other["__VERSION__"] = newest_source
            else:
                logfile.write("=========================================================================\n")
                logfile822.write("\n")
                raise ValueError("No versions can be found. Close bugs yourself.")
            if bcc:
                Subst_close_other["__BCC__"] = "Bcc: " + ", ".join(bcc)
            else:
                Subst_close_other["__BCC__"] = "X-Filler: 42"
            # at this point, I just assume, that the first closed bug gives
            # some useful information on why the package got removed
            Subst_close_other["__BUG_NUMBER__"] = done_bugs[0]
            Subst_close_other["__BUG_NUMBER_ALSO__"] = ""
            Subst_close_other["__SOURCE__"] = source_pkg
            merged_bugs = set()
            other_bugs = bts.get_bugs('src', source_pkg, 'status', 'open', 'status', 'forwarded')
            if other_bugs:
                for bugno in other_bugs:
                    if bugno not in merged_bugs:
                        for bug in bts.get_status(bugno):
                            for merged in bug.mergedwith:
                                other_bugs.remove(merged)
                                merged_bugs.add(merged)
                logfile.write("Also closing bug(s):")
                logfile822.write("Also-Bugs:")
                for bug in other_bugs:
                    Subst_close_other["__BUG_NUMBER_ALSO__"] += str(bug) + "-done@" + cnf["Dinstall::BugServer"] + ","
                    logfile.write(" " + str(bug))
                    logfile822.write(" " + str(bug))
                logfile.write("\n")
                logfile822.write("\n")
            if source_pkg in wnpp:
                logfile.write("Also closing WNPP bug(s):")
                logfile822.write("Also-WNPP:")
                for bug in wnpp[source_pkg]:
                    # the wnpp-rm file we parse also contains our removal
                    # bugs, filtering that out
                    if bug != Subst_close_other["__BUG_NUMBER__"]:
                        Subst_close_other["__BUG_NUMBER_ALSO__"] += str(bug) + "-done@" + cnf["Dinstall::BugServer"] + ","
                        logfile.write(" " + str(bug))
                        logfile822.write(" " + str(bug))
                logfile.write("\n")
                logfile822.write("\n")

            mail_message = utils.TemplateSubst(Subst_close_other, cnf["Dir::Templates"] + "/rm.bug-close-related")
            if Subst_close_other["__BUG_NUMBER_ALSO__"]:
                utils.send_mail(mail_message)

        logfile.write("=========================================================================\n")
        logfile822.write("\n")
