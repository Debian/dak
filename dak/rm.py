#!/usr/bin/env python

""" General purpose package removal tool for ftpmaster """
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

# o OpenBSD team wants to get changes incorporated into IPF. Darren no
#    respond.
# o Ask again -> No respond. Darren coder supreme.
# o OpenBSD decide to make changes, but only in OpenBSD source
#    tree. Darren hears, gets angry! Decides: "LICENSE NO ALLOW!"
# o Insert Flame War.
# o OpenBSD team decide to switch to different packet filter under BSD
#    license. Because Project Goal: Every user should be able to make
#    changes to source tree. IPF license bad!!
# o Darren try get back: says, NetBSD, FreeBSD allowed! MUAHAHAHAH!!!
# o Theo say: no care, pf much better than ipf!
# o Darren changes mind: changes license. But OpenBSD will not change
#    back to ipf. Darren even much more bitter.
# o Darren so bitterbitter. Decides: I'LL GET BACK BY FORKING OPENBSD AND
#    RELEASING MY OWN VERSION. HEHEHEHEHE.

#                        http://slashdot.org/comments.pl?sid=26697&cid=2883271

################################################################################

import commands
import os
import sys
import apt_pkg
import apt_inst
from re import sub

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils
from daklib.dak_exceptions import *
from daklib.regexes import re_strip_source_version, re_bin_only_nmu
import debianbts as bts

################################################################################

Options = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak rm [OPTIONS] PACKAGE[...]
Remove PACKAGE(s) from suite(s).

  -a, --architecture=ARCH    only act on this architecture
  -b, --binary               PACKAGE are binary packages to remove
  -B, --binary-only          remove binaries only
  -c, --component=COMPONENT  act on this component
  -C, --carbon-copy=EMAIL    send a CC of removal message to EMAIL
  -d, --done=BUG#            send removal message as closure to bug#
  -D, --do-close             also close all bugs associated to that package
  -h, --help                 show this help and exit
  -m, --reason=MSG           reason for removal
  -n, --no-action            don't do anything
  -p, --partial              don't affect override files
  -R, --rdep-check           check reverse dependencies
  -s, --suite=SUITE          act on this suite
  -S, --source-only          remove source only

ARCH, BUG#, COMPONENT and SUITE can be comma (or space) separated lists, e.g.
    --architecture=amd64,i386"""

    sys.exit(exit_code)

################################################################################

# "Hudson: What that's great, that's just fucking great man, now what
#  the fuck are we supposed to do? We're in some real pretty shit now
#  man...That's it man, game over man, game over, man! Game over! What
#  the fuck are we gonna do now? What are we gonna do?"

def game_over():
    answer = utils.our_raw_input("Continue (y/N)? ").lower()
    if answer != "y":
        print "Aborted."
        sys.exit(1)

################################################################################

def reverse_depends_check(removals, suite, arches=None, session=None):
    print "Checking reverse dependencies..."
    if utils.check_reverse_depends(removals, suite, arches, session):
        print "Dependency problem found."
        if not Options["No-Action"]:
            game_over()
    else:
        print "No dependency problem found."
    print

################################################################################

def main ():
    global Options

    cnf = Config()

    Arguments = [('h',"help","Rm::Options::Help"),
                 ('a',"architecture","Rm::Options::Architecture", "HasArg"),
                 ('b',"binary", "Rm::Options::Binary"),
                 ('B',"binary-only", "Rm::Options::Binary-Only"),
                 ('c',"component", "Rm::Options::Component", "HasArg"),
                 ('C',"carbon-copy", "Rm::Options::Carbon-Copy", "HasArg"), # Bugs to Cc
                 ('d',"done","Rm::Options::Done", "HasArg"), # Bugs fixed
                 ('D',"do-close","Rm::Options::Do-Close"),
                 ('R',"rdep-check", "Rm::Options::Rdep-Check"),
                 ('m',"reason", "Rm::Options::Reason", "HasArg"), # Hysterical raisins; -m is old-dinstall option for rejection reason
                 ('n',"no-action","Rm::Options::No-Action"),
                 ('p',"partial", "Rm::Options::Partial"),
                 ('s',"suite","Rm::Options::Suite", "HasArg"),
                 ('S',"source-only", "Rm::Options::Source-Only"),
                 ]

    for i in [ "architecture", "binary", "binary-only", "carbon-copy", "component",
               "done", "help", "no-action", "partial", "rdep-check", "reason",
               "source-only", "Do-Close" ]:
        if not cnf.has_key("Rm::Options::%s" % (i)):
            cnf["Rm::Options::%s" % (i)] = ""
    if not cnf.has_key("Rm::Options::Suite"):
        cnf["Rm::Options::Suite"] = "unstable"

    arguments = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Rm::Options")

    if Options["Help"]:
        usage()

    session = DBConn().session()

    # Sanity check options
    if not arguments:
        utils.fubar("need at least one package name as an argument.")
    if Options["Architecture"] and Options["Source-Only"]:
        utils.fubar("can't use -a/--architecture and -S/--source-only options simultaneously.")
    if ((Options["Binary"] and Options["Source-Only"])
            or (Options["Binary"] and Options["Binary-Only"])
            or (Options["Binary-Only"] and Options["Source-Only"])):
        utils.fubar("Only one of -b/--binary, -B/--binary-only and -S/--source-only can be used.")
    if Options.has_key("Carbon-Copy") and not Options.has_key("Done"):
        utils.fubar("can't use -C/--carbon-copy without also using -d/--done option.")
    if Options["Architecture"] and not Options["Partial"]:
        utils.warn("-a/--architecture implies -p/--partial.")
        Options["Partial"] = "true"
    if Options["Do-Close"] and not Options["Done"]:
        utils.fubar("No.")
    if (Options["Do-Close"]
           and (Options["Binary"] or Options["Binary-Only"] or Options["Source-Only"])):
        utils.fubar("No.")

    # Force the admin to tell someone if we're not doing a 'dak
    # cruft-report' inspired removal (or closing a bug, which counts
    # as telling someone).
    if not Options["No-Action"] and not Options["Carbon-Copy"] \
           and not Options["Done"] and Options["Reason"].find("[auto-cruft]") == -1:
        utils.fubar("Need a -C/--carbon-copy if not closing a bug and not doing a cruft removal.")

    # Process -C/--carbon-copy
    #
    # Accept 3 types of arguments (space separated):
    #  1) a number - assumed to be a bug number, i.e. nnnnn@bugs.debian.org
    #  2) the keyword 'package' - cc's $package@packages.debian.org for every argument
    #  3) contains a '@' - assumed to be an email address, used unmofidied
    #
    carbon_copy = []
    for copy_to in utils.split_args(Options.get("Carbon-Copy")):
        if copy_to.isdigit():
            if cnf.has_key("Dinstall::BugServer"):
                carbon_copy.append(copy_to + "@" + cnf["Dinstall::BugServer"])
            else:
                utils.fubar("Asked to send mail to #%s in BTS but Dinstall::BugServer is not configured" % copy_to)
        elif copy_to == 'package':
            for package in arguments:
                if cnf.has_key("Dinstall::PackagesServer"):
                    carbon_copy.append(package + "@" + cnf["Dinstall::PackagesServer"])
                if cnf.has_key("Dinstall::TrackingServer"):
                    carbon_copy.append(package + "@" + cnf["Dinstall::TrackingServer"])
        elif '@' in copy_to:
            carbon_copy.append(copy_to)
        else:
            utils.fubar("Invalid -C/--carbon-copy argument '%s'; not a bug number, 'package' or email address." % (copy_to))

    if Options["Binary"]:
        field = "b.package"
    else:
        field = "s.source"
    con_packages = "AND %s IN (%s)" % (field, ", ".join([ repr(i) for i in arguments ]))

    (con_suites, con_architectures, con_components, check_source) = \
                 utils.parse_args(Options)

    # Additional suite checks
    suite_ids_list = []
    whitelists = []
    suites = utils.split_args(Options["Suite"])
    suites_list = utils.join_with_commas_and(suites)
    if not Options["No-Action"]:
        for suite in suites:
            s = get_suite(suite, session=session)
            if s is not None:
                suite_ids_list.append(s.suite_id)
                whitelists.append(s.mail_whitelist)
            if suite in ("oldstable", "stable"):
                print "**WARNING** About to remove from the (old)stable suite!"
                print "This should only be done just prior to a (point) release and not at"
                print "any other time."
                game_over()
            elif suite == "testing":
                print "**WARNING About to remove from the testing suite!"
                print "There's no need to do this normally as removals from unstable will"
                print "propogate to testing automagically."
                game_over()

    # Additional architecture checks
    if Options["Architecture"] and check_source:
        utils.warn("'source' in -a/--argument makes no sense and is ignored.")

    # Additional component processing
    over_con_components = con_components.replace("c.id", "component")

    # Don't do dependency checks on multiple suites
    if Options["Rdep-Check"] and len(suites) > 1:
        utils.fubar("Reverse dependency check on multiple suites is not implemented.")

    to_remove = []
    maintainers = {}

    # We have 3 modes of package selection: binary, source-only, binary-only
    # and source+binary.

    # XXX: TODO: This all needs converting to use placeholders or the object
    #            API. It's an SQL injection dream at the moment

    if Options["Binary"]:
        # Removal by binary package name
        q = session.execute("SELECT b.package, b.version, a.arch_string, b.id, b.maintainer FROM binaries b, bin_associations ba, architecture a, suite su, files f, files_archive_map af, component c WHERE ba.bin = b.id AND ba.suite = su.id AND b.architecture = a.id AND b.file = f.id AND af.file_id = f.id AND af.archive_id = su.archive_id AND af.component_id = c.id %s %s %s %s" % (con_packages, con_suites, con_components, con_architectures))
        to_remove.extend(q)
    else:
        # Source-only
        if not Options["Binary-Only"]:
            q = session.execute("SELECT s.source, s.version, 'source', s.id, s.maintainer FROM source s, src_associations sa, suite su, archive, files f, files_archive_map af, component c WHERE sa.source = s.id AND sa.suite = su.id AND archive.id = su.archive_id AND s.file = f.id AND af.file_id = f.id AND af.archive_id = su.archive_id AND af.component_id = c.id %s %s %s" % (con_packages, con_suites, con_components))
            to_remove.extend(q)
        if not Options["Source-Only"]:
            # Source + Binary
            q = session.execute("""
                    SELECT b.package, b.version, a.arch_string, b.id, b.maintainer
                    FROM binaries b
                         JOIN bin_associations ba ON b.id = ba.bin
                         JOIN architecture a ON b.architecture = a.id
                         JOIN suite su ON ba.suite = su.id
                         JOIN archive ON archive.id = su.archive_id
                         JOIN files_archive_map af ON b.file = af.file_id AND af.archive_id = archive.id
                         JOIN component c ON af.component_id = c.id
                         JOIN source s ON b.source = s.id
                         JOIN src_associations sa ON s.id = sa.source AND sa.suite = su.id
                    WHERE TRUE %s %s %s %s""" % (con_packages, con_suites, con_components, con_architectures))
            to_remove.extend(q)

    if not to_remove:
        print "Nothing to do."
        sys.exit(0)

    # If we don't have a reason; spawn an editor so the user can add one
    # Write the rejection email out as the <foo>.reason file
    if not Options["Reason"] and not Options["No-Action"]:
        (fd, temp_filename) = utils.temp_filename()
        editor = os.environ.get("EDITOR","vi")
        result = os.system("%s %s" % (editor, temp_filename))
        if result != 0:
            utils.fubar ("vi invocation failed for `%s'!" % (temp_filename), result)
        temp_file = utils.open_file(temp_filename)
        for line in temp_file.readlines():
            Options["Reason"] += line
        temp_file.close()
        os.unlink(temp_filename)

    # Generate the summary of what's to be removed
    d = {}
    for i in to_remove:
        package = i[0]
        version = i[1]
        architecture = i[2]
        maintainer = i[4]
        maintainers[maintainer] = ""
        if not d.has_key(package):
            d[package] = {}
        if not d[package].has_key(version):
            d[package][version] = []
        if architecture not in d[package][version]:
            d[package][version].append(architecture)

    maintainer_list = []
    for maintainer_id in maintainers.keys():
        maintainer_list.append(get_maintainer(maintainer_id).name)
    summary = ""
    removals = d.keys()
    removals.sort()
    versions = []
    for package in removals:
        versions = d[package].keys()
        versions.sort(apt_pkg.version_compare)
        for version in versions:
            d[package][version].sort(utils.arch_compare_sw)
            summary += "%10s | %10s | %s\n" % (package, version, ", ".join(d[package][version]))
    print "Will remove the following packages from %s:" % (suites_list)
    print
    print summary
    print "Maintainer: %s" % ", ".join(maintainer_list)
    if Options["Done"]:
        print "Will also close bugs: "+Options["Done"]
    if carbon_copy:
        print "Will also send CCs to: " + ", ".join(carbon_copy)
    if Options["Do-Close"]:
        print "Will also close associated bug reports."
    print
    print "------------------- Reason -------------------"
    print Options["Reason"]
    print "----------------------------------------------"
    print

    if Options["Rdep-Check"]:
        arches = utils.split_args(Options["Architecture"])
        reverse_depends_check(removals, suites[0], arches, session)

    # If -n/--no-action, drop out here
    if Options["No-Action"]:
        sys.exit(0)

    print "Going to remove the packages now."
    game_over()

    whoami = utils.whoami()
    date = commands.getoutput('date -R')

    # Log first; if it all falls apart I want a record that we at least tried.
    logfile = utils.open_file(cnf["Rm::LogFile"], 'a')
    logfile.write("=========================================================================\n")
    logfile.write("[Date: %s] [ftpmaster: %s]\n" % (date, whoami))
    logfile.write("Removed the following packages from %s:\n\n%s" % (suites_list, summary))
    if Options["Done"]:
        logfile.write("Closed bugs: %s\n" % (Options["Done"]))
    logfile.write("\n------------------- Reason -------------------\n%s\n" % (Options["Reason"]))
    logfile.write("----------------------------------------------\n")

    # Do the same in rfc822 format
    logfile822 = utils.open_file(cnf["Rm::LogFile822"], 'a')
    logfile822.write("Date: %s\n" % date)
    logfile822.write("Ftpmaster: %s\n" % whoami)
    logfile822.write("Suite: %s\n" % suites_list)
    sources = []
    binaries = []
    for package in summary.split("\n"):
        for row in package.split("\n"):
            element = row.split("|")
            if len(element) == 3:
                if element[2].find("source") > 0:
                    sources.append("%s_%s" % tuple(elem.strip(" ") for elem in element[:2]))
                    element[2] = sub("source\s?,?", "", element[2]).strip(" ")
                if element[2]:
                    binaries.append("%s_%s [%s]" % tuple(elem.strip(" ") for elem in element))
    if sources:
        logfile822.write("Sources:\n")
        for source in sources:
            logfile822.write(" %s\n" % source)
    if binaries:
        logfile822.write("Binaries:\n")
        for binary in binaries:
            logfile822.write(" %s\n" % binary)
    logfile822.write("Reason: %s\n" % Options["Reason"].replace('\n', '\n '))
    if Options["Done"]:
        logfile822.write("Bug: %s\n" % Options["Done"])

    dsc_type_id = get_override_type('dsc', session).overridetype_id
    deb_type_id = get_override_type('deb', session).overridetype_id

    # Do the actual deletion
    print "Deleting...",
    sys.stdout.flush()

    for i in to_remove:
        package = i[0]
        architecture = i[2]
        package_id = i[3]
        for suite_id in suite_ids_list:
            if architecture == "source":
                session.execute("DELETE FROM src_associations WHERE source = :packageid AND suite = :suiteid",
                                {'packageid': package_id, 'suiteid': suite_id})
                #print "DELETE FROM src_associations WHERE source = %s AND suite = %s" % (package_id, suite_id)
            else:
                session.execute("DELETE FROM bin_associations WHERE bin = :packageid AND suite = :suiteid",
                                {'packageid': package_id, 'suiteid': suite_id})
                #print "DELETE FROM bin_associations WHERE bin = %s AND suite = %s" % (package_id, suite_id)
            # Delete from the override file
            if not Options["Partial"]:
                if architecture == "source":
                    type_id = dsc_type_id
                else:
                    type_id = deb_type_id
                # TODO: Again, fix this properly to remove the remaining non-bind argument
                session.execute("DELETE FROM override WHERE package = :package AND type = :typeid AND suite = :suiteid %s" % (over_con_components), {'package': package, 'typeid': type_id, 'suiteid': suite_id})
    session.commit()
    print "done."

    # If we don't have a Bug server configured, we're done
    if not cnf.has_key("Dinstall::BugServer"):
        if Options["Done"] or Options["Do-Close"]:
            print "Cannot send mail to BugServer as Dinstall::BugServer is not configured"

        logfile.write("=========================================================================\n")
        logfile.close()

        logfile822.write("\n")
        logfile822.close()

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
    if Options["Done"]:
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
        summarymail = "%s\n------------------- Reason -------------------\n%s\n" % (summary, Options["Reason"])
        summarymail += "----------------------------------------------\n"
        Subst_close_rm["__SUMMARY__"] = summarymail

        for bug in utils.split_args(Options["Done"]):
            Subst_close_rm["__BUG_NUMBER__"] = bug
            if Options["Do-Close"]:
                mail_message = utils.TemplateSubst(Subst_close_rm,cnf["Dir::Templates"]+"/rm.bug-close-with-related")
            else:
                mail_message = utils.TemplateSubst(Subst_close_rm,cnf["Dir::Templates"]+"/rm.bug-close")
            utils.send_mail(mail_message, whitelists=whitelists)

    # close associated bug reports
    if Options["Do-Close"]:
        Subst_close_other = Subst_common
        bcc = []
        wnpp = utils.parse_wnpp_bug_file()
        versions = list(set([re_bin_only_nmu.sub('', v) for v in versions]))
        if len(versions) == 1:
            Subst_close_other["__VERSION__"] = versions[0]
        else:
            utils.fubar("Closing bugs with multiple package versions is not supported.  Do it yourself.")
        if bcc:
            Subst_close_other["__BCC__"] = "Bcc: " + ", ".join(bcc)
        else:
            Subst_close_other["__BCC__"] = "X-Filler: 42"
        # at this point, I just assume, that the first closed bug gives
        # some useful information on why the package got removed
        Subst_close_other["__BUG_NUMBER__"] = utils.split_args(Options["Done"])[0]
        if len(sources) == 1:
            source_pkg = source.split("_", 1)[0]
        else:
            utils.fubar("Closing bugs for multiple source packages is not supported.  Do it yourself.")
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
        if source_pkg in wnpp.keys():
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

        mail_message = utils.TemplateSubst(Subst_close_other,cnf["Dir::Templates"]+"/rm.bug-close-related")
        if Subst_close_other["__BUG_NUMBER_ALSO__"]:
            utils.send_mail(mail_message)


    logfile.write("=========================================================================\n")
    logfile.close()

    logfile822.write("\n")
    logfile822.close()

#######################################################################################

if __name__ == '__main__':
    main()
