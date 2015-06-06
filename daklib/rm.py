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

# TODO: Insert "random dak quote" here

################################################################################

import commands
import apt_pkg
from re import sub

from daklib.dbconn import *
from daklib import utils
from daklib.regexes import re_bin_only_nmu
import debianbts as bts

################################################################################


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
    @param date: The date of the removal. Defaults to commands.getoutput("date -R")

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
    suite_ids_list = []
    suites_list = utils.join_with_commas_and(suites)
    cnf = utils.get_conf()
    con_components = None

    #######################################################################################################

    if not reason:
        raise ValueError("Empty removal reason not permitted")

    if not removals:
        raise ValueError("Nothing to remove!?")

    if not suites:
        raise ValueError("Removals without a suite!?")

    if whoami is None:
        whoami = utils.whoami()

    if date is None:
        date = commands.getoutput("date -R")

    if partial:

        component_ids_list = []
        for componentname in components:
            component = get_component(componentname, session=session)
            if component is None:
                raise ValueError("component '%s' not recognised." % componentname)
            else:
                component_ids_list.append(component.component_id)
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

    for package in sorted(removals):
        versions = sorted(d[package], cmp=apt_pkg.version_compare)
        for version in versions:
            d[package][version].sort(utils.arch_compare_sw)
            summary += "%10s | %10s | %s\n" % (package, version, ", ".join(d[package][version]))

    for package in summary.split("\n"):
        for row in package.split("\n"):
            element = row.split("|")
            if len(element) == 3:
                if element[2].find("source") > 0:
                    sources.append("%s_%s" % tuple(elem.strip(" ") for elem in element[:2]))
                    element[2] = sub("source\s?,?", "", element[2]).strip(" ")
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
    with utils.open_file(log_filename, "a") as logfile, utils.open_file(log822_filename, "a") as logfile822:
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
                if partial:
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
                    mail_message = utils.TemplateSubst(Subst_close_rm,cnf["Dir::Templates"]+"/rm.bug-close-with-related")
                else:
                    mail_message = utils.TemplateSubst(Subst_close_rm,cnf["Dir::Templates"]+"/rm.bug-close")
                utils.send_mail(mail_message, whitelists=whitelists)

        # close associated bug reports
        if close_related_bugs:
            Subst_close_other = Subst_common
            bcc = []
            wnpp = utils.parse_wnpp_bug_file()
            versions = list(set([re_bin_only_nmu.sub('', v) for v in versions]))
            if len(versions) == 1:
                Subst_close_other["__VERSION__"] = versions[0]
            else:
                logfile.write("=========================================================================\n")
                logfile822.write("\n")
                raise ValueError("Closing bugs with multiple package versions is not supported.  Do it yourself.")
            if bcc:
                Subst_close_other["__BCC__"] = "Bcc: " + ", ".join(bcc)
            else:
                Subst_close_other["__BCC__"] = "X-Filler: 42"
            # at this point, I just assume, that the first closed bug gives
            # some useful information on why the package got removed
            Subst_close_other["__BUG_NUMBER__"] = done_bugs[0]
            if len(sources) == 1:
                source_pkg = source.split("_", 1)[0]
            else:
                logfile.write("=========================================================================\n")
                logfile822.write("\n")
                raise ValueError("Closing bugs for multiple source packages is not supported.  Please do it yourself.")
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

            mail_message = utils.TemplateSubst(Subst_close_other, cnf["Dir::Templates"]+"/rm.bug-close-related")
            if Subst_close_other["__BUG_NUMBER_ALSO__"]:
                utils.send_mail(mail_message)

        logfile.write("=========================================================================\n")
        logfile822.write("\n")
