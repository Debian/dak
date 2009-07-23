#!/usr/bin/env python
# vim:set et sw=4:

"""
Queue utility functions for dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001 - 2006 James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
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

###############################################################################

import cPickle
import errno
import os
import pg
import stat
import sys
import time
import apt_inst
import apt_pkg
import utils
import database

from dak_exceptions import *
from changes import *
from regexes import re_default_answer, re_fdnic, re_bin_only_nmu
from config import Config
from summarystats import SummaryStats

from types import *

###############################################################################

# Determine what parts in a .changes are NEW

def determine_new(changes, files, projectB, warn=1):
    """
    Determine what parts in a C{changes} file are NEW.

    @type changes: Upload.Pkg.changes dict
    @param changes: Changes dictionary

    @type files: Upload.Pkg.files dict
    @param files: Files dictionary

    @type projectB: pgobject
    @param projectB: DB handle

    @type warn: bool
    @param warn: Warn if overrides are added for (old)stable

    @rtype: dict
    @return: dictionary of NEW components.

    """
    new = {}

    # Build up a list of potentially new things
    for file_entry in files.keys():
        f = files[file_entry]
        # Skip byhand elements
        if f["type"] == "byhand":
            continue
        pkg = f["package"]
        priority = f["priority"]
        section = f["section"]
        file_type = get_type(f)
        component = f["component"]

        if file_type == "dsc":
            priority = "source"
        if not new.has_key(pkg):
            new[pkg] = {}
            new[pkg]["priority"] = priority
            new[pkg]["section"] = section
            new[pkg]["type"] = file_type
            new[pkg]["component"] = component
            new[pkg]["files"] = []
        else:
            old_type = new[pkg]["type"]
            if old_type != file_type:
                # source gets trumped by deb or udeb
                if old_type == "dsc":
                    new[pkg]["priority"] = priority
                    new[pkg]["section"] = section
                    new[pkg]["type"] = file_type
                    new[pkg]["component"] = component
        new[pkg]["files"].append(file_entry)
        if f.has_key("othercomponents"):
            new[pkg]["othercomponents"] = f["othercomponents"]

    for suite in changes["suite"].keys():
        suite_id = database.get_suite_id(suite)
        for pkg in new.keys():
            component_id = database.get_component_id(new[pkg]["component"])
            type_id = database.get_override_type_id(new[pkg]["type"])
            q = projectB.query("SELECT package FROM override WHERE package = '%s' AND suite = %s AND component = %s AND type = %s" % (pkg, suite_id, component_id, type_id))
            ql = q.getresult()
            if ql:
                for file_entry in new[pkg]["files"]:
                    if files[file_entry].has_key("new"):
                        del files[file_entry]["new"]
                del new[pkg]

    if warn:
        if changes["suite"].has_key("stable"):
            print "WARNING: overrides will be added for stable!"
            if changes["suite"].has_key("oldstable"):
                print "WARNING: overrides will be added for OLDstable!"
        for pkg in new.keys():
            if new[pkg].has_key("othercomponents"):
                print "WARNING: %s already present in %s distribution." % (pkg, new[pkg]["othercomponents"])

    return new

################################################################################

def get_type(file):
    """
    Get the file type of C{file}

    @type file: dict
    @param file: file entry

    @rtype: string
    @return: filetype

    """
    # Determine the type
    if file.has_key("dbtype"):
        file_type = file["dbtype"]
    elif file["type"] in [ "orig.tar.gz", "orig.tar.bz2", "tar.gz", "tar.bz2", "diff.gz", "diff.bz2", "dsc" ]:
        file_type = "dsc"
    else:
        utils.fubar("invalid type (%s) for new.  Dazed, confused and sure as heck not continuing." % (file_type))

    # Validate the override type
    type_id = database.get_override_type_id(file_type)
    if type_id == -1:
        utils.fubar("invalid type (%s) for new.  Say wha?" % (file_type))

    return file_type

################################################################################



def check_valid(new):
    """
    Check if section and priority for NEW packages exist in database.
    Additionally does sanity checks:
      - debian-installer packages have to be udeb (or source)
      - non debian-installer packages can not be udeb
      - source priority can only be assigned to dsc file types

    @type new: dict
    @param new: Dict of new packages with their section, priority and type.

    """
    for pkg in new.keys():
        section = new[pkg]["section"]
        priority = new[pkg]["priority"]
        file_type = new[pkg]["type"]
        new[pkg]["section id"] = database.get_section_id(section)
        new[pkg]["priority id"] = database.get_priority_id(new[pkg]["priority"])
        # Sanity checks
        di = section.find("debian-installer") != -1
        if (di and file_type not in ("udeb", "dsc")) or (not di and file_type == "udeb"):
            new[pkg]["section id"] = -1
        if (priority == "source" and file_type != "dsc") or \
           (priority != "source" and file_type == "dsc"):
            new[pkg]["priority id"] = -1


###############################################################################

class Upload(object):
    """
    Everything that has to do with an upload processed.

    """
    def __init__(self):
        """
        Initialize various variables and the global substitution template mappings.
        Also connect to the DB and initialize the Database module.

        """

        self.pkg = Changes()
        self.reset()

    ###########################################################################

    def reset (self):
        """ Reset a number of internal variables."""

       # Initialize the substitution template map
        cnf = Config()
        self.Subst = {}
        self.Subst["__ADMIN_ADDRESS__"] = cnf["Dinstall::MyAdminAddress"]
        self.Subst["__BUG_SERVER__"] = cnf["Dinstall::BugServer"]
        self.Subst["__DISTRO__"] = cnf["Dinstall::MyDistribution"]
        self.Subst["__DAK_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]

        self.reject_message = ""
        self.changes.reset()

    ###########################################################################
    def update_subst(self, reject_message = ""):
        """ Set up the per-package template substitution mappings """

        cnf = Config()

        # If 'dak process-unchecked' crashed out in the right place, architecture may still be a string.
        if not self.pkg.changes.has_key("architecture") or not \
           isinstance(changes["architecture"], DictType):
            self.pkg.changes["architecture"] = { "Unknown" : "" }

        # and maintainer2047 may not exist.
        if not self.pkg.changes.has_key("maintainer2047"):
            self.pkg.changes["maintainer2047"] = cnf["Dinstall::MyEmailAddress"]

        self.Subst["__ARCHITECTURE__"] = " ".join(self.pkg.changes["architecture"].keys())
        self.Subst["__CHANGES_FILENAME__"] = os.path.basename(self.pkg.changes_file)
        self.Subst["__FILE_CONTENTS__"] = self.pkg.changes.get("filecontents", "")

        # For source uploads the Changed-By field wins; otherwise Maintainer wins.
        if self.pkg.changes["architecture"].has_key("source") and \
           self.pkg.changes["changedby822"] != "" and \
           (self.pkg.changes["changedby822"] != self.pkg.changes["maintainer822"]):

            self.Subst["__MAINTAINER_FROM__"] = self.pkg.changes["changedby2047"]
            self.Subst["__MAINTAINER_TO__"] = "%s, %s" % (self.pkg.changes["changedby2047"], changes["maintainer2047"])
            self.Subst["__MAINTAINER__"] = self.pkg.changes.get("changed-by", "Unknown")
        else:
            self.Subst["__MAINTAINER_FROM__"] = self.pkg.changes["maintainer2047"]
            self.Subst["__MAINTAINER_TO__"] = self.pkg.changes["maintainer2047"]
            self.Subst["__MAINTAINER__"] = self.pkg.changes.get("maintainer", "Unknown")

        if "sponsoremail" in self.pkg.changes:
            self.Subst["__MAINTAINER_TO__"] += ", %s" % self.pkg.changes["sponsoremail"]

        if cnf.has_key("Dinstall::TrackingServer") and self.pkg.changes.has_key("source"):
            self.Subst["__MAINTAINER_TO__"] += "\nBcc: %s@%s" % (self.pkg.changes["source"], cnf["Dinstall::TrackingServer"])

        # Apply any global override of the Maintainer field
        if cnf.get("Dinstall::OverrideMaintainer"):
            self.Subst["__MAINTAINER_TO__"] = cnf["Dinstall::OverrideMaintainer"]
            self.Subst["__MAINTAINER_FROM__"] = cnf["Dinstall::OverrideMaintainer"]

        self.Subst["__REJECT_MESSAGE__"] = self.reject_message
        self.Subst["__SOURCE__"] = self.pkg.changes.get("source", "Unknown")
        self.Subst["__VERSION__"] = self.pkg.changes.get("version", "Unknown")

    ###########################################################################

    def build_summaries(self):
        """ Build a summary of changes the upload introduces. """

        (byhand, new, summary, override_summary) = self.pkg.file_summary()

        short_summary = summary

        # This is for direport's benefit...
        f = re_fdnic.sub("\n .\n", self.pkg.changes.get("changes", ""))

        if byhand or new:
            summary += "Changes: " + f

        summary += "\n\nOverride entries for your package:\n" + override_summary + "\n"

        summary += self.announce(short_summary, 0)

        return (summary, short_summary)

    ###########################################################################

    def close_bugs(self, summary, action):
        """
        Send mail to close bugs as instructed by the closes field in the changes file.
        Also add a line to summary if any work was done.

        @type summary: string
        @param summary: summary text, as given by L{build_summaries}

        @type action: bool
        @param action: Set to false no real action will be done.

        @rtype: string
        @return: summary. If action was taken, extended by the list of closed bugs.

        """

        template = os.path.join(Config()["Dir::Templates"], 'process-unchecked.bug-close')

        bugs = self.pkg.changes["closes"].keys()

        if not bugs:
            return summary

        bugs.sort()
        summary += "Closing bugs: "
        for bug in bugs:
            summary += "%s " % (bug)
            if action:
                self.Subst["__BUG_NUMBER__"] = bug
                if self.pkg.changes["distribution"].has_key("stable"):
                    self.Subst["__STABLE_WARNING__"] = """
Note that this package is not part of the released stable Debian
distribution.  It may have dependencies on other unreleased software,
or other instabilities.  Please take care if you wish to install it.
The update will eventually make its way into the next released Debian
distribution."""
                else:
                    self.Subst["__STABLE_WARNING__"] = ""
                    mail_message = utils.TemplateSubst(self.Subst, template)
                    utils.send_mail(mail_message)

                # Clear up after ourselves
                del self.Subst["__BUG_NUMBER__"]
                del self.Subst["__STABLE_WARNING__"]

        if action:
            self.Logger.log(["closing bugs"] + bugs)

        summary += "\n"

        return summary

    ###########################################################################

    def announce(self, short_summary, action):
        """
        Send an announce mail about a new upload.

        @type short_summary: string
        @param short_summary: Short summary text to include in the mail

        @type action: bool
        @param action: Set to false no real action will be done.

        @rtype: string
        @return: Textstring about action taken.

        """

        cnf = Config()
        announcetemplate = os.path.join(cnf["Dir::Templates"], 'process-unchecked.announce')

        # Only do announcements for source uploads with a recent dpkg-dev installed
        if float(self.pkg.changes.get("format", 0)) < 1.6 or not \
           self.pkg.changes["architecture"].has_key("source"):
            return ""

        lists_done = {}
        summary = ""

        self.Subst["__SHORT_SUMMARY__"] = short_summary

        for dist in self.pkg.changes["distribution"].keys():
            announce_list = Cnf.Find("Suite::%s::Announce" % (dist))
            if announce_list == "" or lists_done.has_key(announce_list):
                continue

            lists_done[announce_list] = 1
            summary += "Announcing to %s\n" % (announce_list)

            if action:
                self.Subst["__ANNOUNCE_LIST_ADDRESS__"] = announce_list
                if cnf.get("Dinstall::TrackingServer") and \
                   self.pkg.changes["architecture"].has_key("source"):
                    trackingsendto = "Bcc: %s@%s" % (self.pkg.changes["source"], cnf["Dinstall::TrackingServer"])
                    self.Subst["__ANNOUNCE_LIST_ADDRESS__"] += "\n" + trackingsendto

                mail_message = utils.TemplateSubst(self.Subst, announcetemplate)
                utils.send_mail(mail_message)

                del self.Subst["__ANNOUNCE_LIST_ADDRESS__"]

        if cnf.FindB("Dinstall::CloseBugs"):
            summary = self.close_bugs(summary, action)

        del self.Subst["__SHORT_SUMMARY__"]

        return summary

    ###########################################################################

    def accept (self, summary, short_summary, targetdir=None):
        """
        Accept an upload.

        This moves all files referenced from the .changes into the I{accepted}
        queue, sends the accepted mail, announces to lists, closes bugs and
        also checks for override disparities. If enabled it will write out
        the version history for the BTS Version Tracking and will finally call
        L{queue_build}.

        @type summary: string
        @param summary: Summary text

        @type short_summary: string
        @param short_summary: Short summary

        """

        cnf = Config()
        stats = SummaryStats()

        accepttemplate = os.path.join(cnf["Dir::Templates"], 'process-unchecked.accepted')

        if targetdir is None:
            targetdir = cnf["Dir::Queue::Accepted"]

        print "Accepting."
        self.Logger.log(["Accepting changes", self.pkg.changes_file])

        self.write_dot_dak(targetdir)

        # Move all the files into the accepted directory
        utils.move(self.pkg.changes_file, targetdir)

        for name, entry in sorted(self.pkg.files.items()):
            utils.move(name, targetdir)
            stats.accept_bytes += float(entry["size"])

        stats.accept_count += 1

        # Send accept mail, announce to lists, close bugs and check for
        # override disparities
        if not cnf["Dinstall::Options::No-Mail"]:
            self.Subst["__SUITE__"] = ""
            self.Subst["__SUMMARY__"] = summary
            mail_message = utils.TemplateSubst(self.Subst, accepttemplate)
            utils.send_mail(mail_message)
            self.announce(short_summary, 1)

        ## Helper stuff for DebBugs Version Tracking
        if cnf.Find("Dir::Queue::BTSVersionTrack"):
            # ??? once queue/* is cleared on *.d.o and/or reprocessed
            # the conditionalization on dsc["bts changelog"] should be
            # dropped.

            # Write out the version history from the changelog
            if self.pkg.changes["architecture"].has_key("source") and \
               self.pkg.dsc.has_key("bts changelog"):

                (fd, temp_filename) = utils.temp_filename(cnf["Dir::Queue::BTSVersionTrack"], prefix=".")
                version_history = os.fdopen(fd, 'w')
                version_history.write(self.pkg.dsc["bts changelog"])
                version_history.close()
                filename = "%s/%s" % (cnf["Dir::Queue::BTSVersionTrack"],
                                      self.pkg.changes_file[:-8]+".versions")
                os.rename(temp_filename, filename)
                os.chmod(filename, 0644)

            # Write out the binary -> source mapping.
            (fd, temp_filename) = utils.temp_filename(cnf["Dir::Queue::BTSVersionTrack"], prefix=".")
            debinfo = os.fdopen(fd, 'w')
            for name, entry in sorted(self.pkg.files.items()):
                if entry["type"] == "deb":
                    line = " ".join([entry["package"], entry["version"],
                                     entry["architecture"], entry["source package"],
                                     entry["source version"]])
                    debinfo.write(line+"\n")
            debinfo.close()
            filename = "%s/%s" % (cnf["Dir::Queue::BTSVersionTrack"],
                                  self.pkg.changes_file[:-8]+".debinfo")
            os.rename(temp_filename, filename)
            os.chmod(filename, 0644)

        # Its is Cnf["Dir::Queue::Accepted"] here, not targetdir!
        # <Ganneff> we do call queue_build too
        # <mhy> well yes, we'd have had to if we were inserting into accepted
        # <Ganneff> now. thats database only.
        # <mhy> urgh, that's going to get messy
        # <Ganneff> so i make the p-n call to it *also* using accepted/
        # <mhy> but then the packages will be in the queue_build table without the files being there
        # <Ganneff> as the buildd queue is only regenerated whenever unchecked runs
        # <mhy> ah, good point
        # <Ganneff> so it will work out, as unchecked move it over
        # <mhy> that's all completely sick
        # <Ganneff> yes

        # This routine returns None on success or an error on failure
        res = get_queue('accepted').autobuild_upload(self.pkg, cnf["Dir::Queue::Accepted"])
        if res:
            utils.fubar(res)


    def check_override (self):
        """
        Checks override entries for validity. Mails "Override disparity" warnings,
        if that feature is enabled.

        Abandons the check if
          - override disparity checks are disabled
          - mail sending is disabled
        """

        cnf = Config()

        # Abandon the check if:
        #  a) override disparity checks have been disabled
        #  b) we're not sending mail
        if not cnf.FindB("Dinstall::OverrideDisparityCheck") or \
           cnf["Dinstall::Options::No-Mail"]:
            return

        summary = self.pkg.check_override()

        if summary == "":
            return

        overridetemplate = os.path.join(cnf["Dir::Templates"], 'process-unchecked.override-disparity')

        self.Subst["__SUMMARY__"] = summary
        mail_message = utils.TemplateSubst(self.Subst, overridetemplate)
        utils.send_mail(mail_message)
        del self.Subst["__SUMMARY__"]

    ###########################################################################
    def force_reject(self, reject_files):
        """
        Forcefully move files from the current directory to the
        reject directory.  If any file already exists in the reject
        directory it will be moved to the morgue to make way for
        the new file.

        @type files: dict
        @param files: file dictionary

        """

        cnf = Config()

        for file_entry in reject_files:
            # Skip any files which don't exist or which we don't have permission to copy.
            if os.access(file_entry, os.R_OK) == 0:
                continue

            dest_file = os.path.join(cnf["Dir::Queue::Reject"], file_entry)

            try:
                dest_fd = os.open(dest_file, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0644)
            except OSError, e:
                # File exists?  Let's try and move it to the morgue
                if e.errno == errno.EEXIST:
                    morgue_file = os.path.join(cnf["Dir::Morgue"], cnf["Dir::MorgueReject"], file_entry)
                    try:
                        morgue_file = utils.find_next_free(morgue_file)
                    except NoFreeFilenameError:
                        # Something's either gone badly Pete Tong, or
                        # someone is trying to exploit us.
                        utils.warn("**WARNING** failed to move %s from the reject directory to the morgue." % (file_entry))
                        return
                    utils.move(dest_file, morgue_file, perms=0660)
                    try:
                        dest_fd = os.open(dest_file, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0644)
                    except OSError, e:
                        # Likewise
                        utils.warn("**WARNING** failed to claim %s in the reject directory." % (file_entry))
                        return
                else:
                    raise
            # If we got here, we own the destination file, so we can
            # safely overwrite it.
            utils.move(file_entry, dest_file, 1, perms=0660)
            os.close(dest_fd)

    ###########################################################################
    def do_reject (self, manual=0, reject_message="", note=""):
        """
        Reject an upload. If called without a reject message or C{manual} is
        true, spawn an editor so the user can write one.

        @type manual: bool
        @param manual: manual or automated rejection

        @type reject_message: string
        @param reject_message: A reject message

        @return: 0

        """
        # If we weren't given a manual rejection message, spawn an
        # editor so the user can add one in...
        if manual and not reject_message:
            (fd, temp_filename) = utils.temp_filename()
            temp_file = os.fdopen(fd, 'w')
            if len(note) > 0:
                for line in note:
                    temp_file.write(line)
            temp_file.close()
            editor = os.environ.get("EDITOR","vi")
            answer = 'E'
            while answer == 'E':
                os.system("%s %s" % (editor, temp_filename))
                temp_fh = utils.open_file(temp_filename)
                reject_message = "".join(temp_fh.readlines())
                temp_fh.close()
                print "Reject message:"
                print utils.prefix_multi_line_string(reject_message,"  ",include_blank_lines=1)
                prompt = "[R]eject, Edit, Abandon, Quit ?"
                answer = "XXX"
                while prompt.find(answer) == -1:
                    answer = utils.our_raw_input(prompt)
                    m = re_default_answer.search(prompt)
                    if answer == "":
                        answer = m.group(1)
                    answer = answer[:1].upper()
            os.unlink(temp_filename)
            if answer == 'A':
                return 1
            elif answer == 'Q':
                sys.exit(0)

        print "Rejecting.\n"

        cnf = Config()

        reason_filename = self.pkg.changes_file[:-8] + ".reason"
        reason_filename = os.path.join(cnf["Dir::Queue::Reject"], reason_filename)

        # Move all the files into the reject directory
        reject_files = self.pkg.files.keys() + [self.pkg.changes_file]
        self.force_reject(reject_files)

        # If we fail here someone is probably trying to exploit the race
        # so let's just raise an exception ...
        if os.path.exists(reason_filename):
            os.unlink(reason_filename)
        reason_fd = os.open(reason_filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0644)

        rej_template = os.path.join(cnf["Dir::Templates"], "queue.rejected")

        if not manual:
            self.Subst["__REJECTOR_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]
            self.Subst["__MANUAL_REJECT_MESSAGE__"] = ""
            self.Subst["__CC__"] = "X-DAK-Rejection: automatic (moo)\nX-Katie-Rejection: automatic (moo)"
            os.write(reason_fd, reject_message)
            reject_mail_message = utils.TemplateSubst(self.Subst, rej_template)
        else:
            # Build up the rejection email
            user_email_address = utils.whoami() + " <%s>" % (cnf["Dinstall::MyAdminAddress"])
            self.Subst["__REJECTOR_ADDRESS__"] = user_email_address
            self.Subst["__MANUAL_REJECT_MESSAGE__"] = reject_message
            self.Subst["__CC__"] = "Cc: " + Cnf["Dinstall::MyEmailAddress"]
            reject_mail_message = utils.TemplateSubst(self.Subst, rej_template)
            # Write the rejection email out as the <foo>.reason file
            os.write(reason_fd, reject_mail_message)

        del self.Subst["__REJECTOR_ADDRESS__"]
        del self.Subst["__MANUAL_REJECT_MESSAGE__"]
        del self.Subst["__CC__"]

        os.close(reason_fd)

        # Send the rejection mail if appropriate
        if not cnf["Dinstall::Options::No-Mail"]:
            utils.send_mail(reject_mail_message)

        self.Logger.log(["rejected", pkg.changes_file])

        return 0

    ################################################################################
    def in_override_p(self, package, component, suite, binary_type, file, session=None):
        """
        Check if a package already has override entries in the DB

        @type package: string
        @param package: package name

        @type component: string
        @param component: database id of the component, as returned by L{database.get_component_id}

        @type suite: int
        @param suite: database id of the suite, as returned by L{database.get_suite_id}

        @type binary_type: string
        @param binary_type: type of the package

        @type file: string
        @param file: filename we check

        @return: the database result. But noone cares anyway.

        """

        cnf = Config()

        if session is None:
            session = DBConn().session()

        if binary_type == "": # must be source
            file_type = "dsc"
        else:
            file_type = binary_type

        # Override suite name; used for example with proposed-updates
        if cnf.Find("Suite::%s::OverrideSuite" % (suite)) != "":
            suite = cnf["Suite::%s::OverrideSuite" % (suite)]

        result = get_override(package, suite, component, file_type, session)

        # If checking for a source package fall back on the binary override type
        if file_type == "dsc" and len(result) < 1:
            result = get_override(package, suite, component, ['deb', 'udeb'], session)

        # Remember the section and priority so we can check them later if appropriate
        if len(result) > 0:
            result = result[0]
            self.pkg.files[file]["override section"] = result.section.section
            self.pkg.files[file]["override priority"] = result.priority.priority
            return result

        return None

    ################################################################################
    def reject (self, str, prefix="Rejected: "):
        """
        Add C{str} to reject_message. Adds C{prefix}, by default "Rejected: "

        @type str: string
        @param str: Reject text

        @type prefix: string
        @param prefix: Prefix text, default Rejected:

        """
        if str:
            # Unlike other rejects we add new lines first to avoid trailing
            # new lines when this message is passed back up to a caller.
            if self.reject_message:
                self.reject_message += "\n"
            self.reject_message += prefix + str

    ################################################################################
    def get_anyversion(self, sv_list, suite):
        """
        @type sv_list: list
        @param sv_list: list of (suite, version) tuples to check

        @type suite: string
        @param suite: suite name

        Description: TODO
        """
        anyversion = None
        anysuite = [suite] + self.Cnf.ValueList("Suite::%s::VersionChecks::Enhances" % (suite))
        for (s, v) in sv_list:
            if s in [ x.lower() for x in anysuite ]:
                if not anyversion or apt_pkg.VersionCompare(anyversion, v) <= 0:
                    anyversion = v

        return anyversion

    ################################################################################

    def cross_suite_version_check(self, sv_list, file, new_version, sourceful=False):
        """
        @type sv_list: list
        @param sv_list: list of (suite, version) tuples to check

        @type file: string
        @param file: XXX

        @type new_version: string
        @param new_version: XXX

        Ensure versions are newer than existing packages in target
        suites and that cross-suite version checking rules as
        set out in the conf file are satisfied.
        """

        cnf = Config()

        # Check versions for each target suite
        for target_suite in self.pkg.changes["distribution"].keys():
            must_be_newer_than = [ i.lower() for i in cnf.ValueList("Suite::%s::VersionChecks::MustBeNewerThan" % (target_suite)) ]
            must_be_older_than = [ i.lower() for i in cnf.ValueList("Suite::%s::VersionChecks::MustBeOlderThan" % (target_suite)) ]

            # Enforce "must be newer than target suite" even if conffile omits it
            if target_suite not in must_be_newer_than:
                must_be_newer_than.append(target_suite)

            for (suite, existent_version) in sv_list:
                vercmp = apt_pkg.VersionCompare(new_version, existent_version)

                if suite in must_be_newer_than and sourceful and vercmp < 1:
                    self.reject("%s: old version (%s) in %s >= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite))

                if suite in must_be_older_than and vercmp > -1:
                    cansave = 0

                    if self.pkg.changes.get('distribution-version', {}).has_key(suite):
                        # we really use the other suite, ignoring the conflicting one ...
                        addsuite = self.pkg.changes["distribution-version"][suite]

                        add_version = self.get_anyversion(sv_list, addsuite)
                        target_version = self.get_anyversion(sv_list, target_suite)

                        if not add_version:
                            # not add_version can only happen if we map to a suite
                            # that doesn't enhance the suite we're propup'ing from.
                            # so "propup-ver x a b c; map a d" is a problem only if
                            # d doesn't enhance a.
                            #
                            # i think we could always propagate in this case, rather
                            # than complaining. either way, this isn't a REJECT issue
                            #
                            # And - we really should complain to the dorks who configured dak
                            self.reject("%s is mapped to, but not enhanced by %s - adding anyways" % (suite, addsuite), "Warning: ")
                            self.pkg.changes.setdefault("propdistribution", {})
                            self.pkg.changes["propdistribution"][addsuite] = 1
                            cansave = 1
                        elif not target_version:
                            # not targets_version is true when the package is NEW
                            # we could just stick with the "...old version..." REJECT
                            # for this, I think.
                            self.reject("Won't propogate NEW packages.")
                        elif apt_pkg.VersionCompare(new_version, add_version) < 0:
                            # propogation would be redundant. no need to reject though.
                            self.reject("ignoring versionconflict: %s: old version (%s) in %s <= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite), "Warning: ")
                            cansave = 1
                        elif apt_pkg.VersionCompare(new_version, add_version) > 0 and \
                             apt_pkg.VersionCompare(add_version, target_version) >= 0:
                            # propogate!!
                            self.reject("Propogating upload to %s" % (addsuite), "Warning: ")
                            self.pkg.changes.setdefault("propdistribution", {})
                            self.pkg.changes["propdistribution"][addsuite] = 1
                            cansave = 1

                    if not cansave:
                        self.reject("%s: old version (%s) in %s <= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite))

    ################################################################################

    def check_binary_against_db(self, file, session=None):
        """

        """

        if session is None:
            session = DBConn().session()

        self.reject_message = ""

        # Ensure version is sane
        q = session.query(BinAssociation)
        q = q.join(DBBinary).filter(DBBinary.package==self.pkg.files[file]["package"])
        q = q.join(Architecture).filter(Architecture.arch_string.in_([self.pkg.files[file]["architecture"], 'all']))

        self.cross_suite_version_check([ (x.suite.suite_name, x.binary.version) for x in q.all() ],
                                       file, files[file]["version"], sourceful=False)

        # Check for any existing copies of the file
        q = session.query(DBBinary).filter_by(files[file]["package"])
        q = q.filter_by(version=files[file]["version"])
        q = q.join(Architecture).filter_by(arch_string=files[file]["architecture"])

        if q.count() > 0:
            self.reject("%s: can not overwrite existing copy already in the archive." % (file))

        return self.reject_message

    ################################################################################

    def check_source_against_db(self, file, session=None):
        """
        """
        if session is None:
            session = DBConn().session()

        self.reject_message = ""
        source = self.pkg.dsc.get("source")
        version = self.pkg.dsc.get("version")

        # Ensure version is sane
        q = session.query(SrcAssociation)
        q = q.join(DBSource).filter(DBSource.source==source)

        self.cross_suite_version_check([ (x.suite.suite_name, x.source.version) for x in q.all() ],
                                       file, version, sourceful=True)

        return self.reject_message

    ################################################################################
    def check_dsc_against_db(self, file):
        """

        @warning: NB: this function can remove entries from the 'files' index [if
         the .orig.tar.gz is a duplicate of the one in the archive]; if
         you're iterating over 'files' and call this function as part of
         the loop, be sure to add a check to the top of the loop to
         ensure you haven't just tried to dereference the deleted entry.

        """
        self.reject_message = ""
        self.pkg.orig_tar_gz = None

        # Try and find all files mentioned in the .dsc.  This has
        # to work harder to cope with the multiple possible
        # locations of an .orig.tar.gz.
        # The ordering on the select is needed to pick the newest orig
        # when it exists in multiple places.
        for dsc_name, dsc_entry in self.pkg.dsc_files.items():
            found = None
            if self.pkg.files.has_key(dsc_name):
                actual_md5 = self.pkg.files[dsc_name]["md5sum"]
                actual_size = int(self.pkg.files[dsc_name]["size"])
                found = "%s in incoming" % (dsc_name)

                # Check the file does not already exist in the archive
                ql = get_poolfile_like_name(dsc_name)

                # Strip out anything that isn't '%s' or '/%s$'
                for i in ql:
                    if not i.filename.endswith(dsc_name):
                        ql.remove(i)

                # "[dak] has not broken them.  [dak] has fixed a
                # brokenness.  Your crappy hack exploited a bug in
                # the old dinstall.
                #
                # "(Come on!  I thought it was always obvious that
                # one just doesn't release different files with
                # the same name and version.)"
                #                        -- ajk@ on d-devel@l.d.o

                if len(ql) > 0:
                    # Ignore exact matches for .orig.tar.gz
                    match = 0
                    if dsc_name.endswith(".orig.tar.gz"):
                        for i in ql:
                            if self.pkg.files.has_key(dsc_name) and \
                               int(self.pkg.files[dsc_name]["size"]) == int(i.filesize) and \
                               self.pkg.files[dsc_name]["md5sum"] == i.md5sum:
                                self.reject("ignoring %s, since it's already in the archive." % (dsc_name), "Warning: ")
                                # TODO: Don't delete the entry, just mark it as not needed
                                # This would fix the stupidity of changing something we often iterate over
                                # whilst we're doing it
                                del files[dsc_name]
                                self.pkg.orig_tar_gz = os.path.join(i.location.path, i.filename)
                                match = 1

                    if not match:
                        self.reject("can not overwrite existing copy of '%s' already in the archive." % (dsc_name))

            elif dsc_name.endswith(".orig.tar.gz"):
                # Check in the pool
                ql = get_poolfile_like_name(dsc_name)

                # Strip out anything that isn't '%s' or '/%s$'
                # TODO: Shouldn't we just search for things which end with our string explicitly in the SQL?
                for i in ql:
                    if not i.filename.endswith(dsc_name):
                        ql.remove(i)

                if len(ql) > 0:
                    # Unfortunately, we may get more than one match here if,
                    # for example, the package was in potato but had an -sa
                    # upload in woody.  So we need to choose the right one.

                    # default to something sane in case we don't match any or have only one
                    x = ql[0]

                    if len(ql) > 1:
                        for i in ql:
                            old_file = os.path.join(i.location.path, i.filename)
                            old_file_fh = utils.open_file(old_file)
                            actual_md5 = apt_pkg.md5sum(old_file_fh)
                            old_file_fh.close()
                            actual_size = os.stat(old_file)[stat.ST_SIZE]
                            if actual_md5 == dsc_entry["md5sum"] and actual_size == int(dsc_entry["size"]):
                                x = i

                    old_file = os.path.join(i.location.path, i.filename)
                    old_file_fh = utils.open_file(old_file)
                    actual_md5 = apt_pkg.md5sum(old_file_fh)
                    old_file_fh.close()
                    actual_size = os.stat(old_file)[stat.ST_SIZE]
                    found = old_file
                    suite_type = f.location.archive_type
                    # need this for updating dsc_files in install()
                    dsc_entry["files id"] = f.file_id
                    # See install() in process-accepted...
                    self.pkg.orig_tar_id = f.file_id
                    self.pkg.orig_tar_gz = old_file
                    self.pkg.orig_tar_location = f.location.location_id
                else:
                    # TODO: Record the queues and info in the DB so we don't hardcode all this crap
                    # Not there? Check the queue directories...
                    for directory in [ "Accepted", "New", "Byhand", "ProposedUpdates", "OldProposedUpdates", "Embargoed", "Unembargoed" ]:
                        in_otherdir = os.path.join(self.Cnf["Dir::Queue::%s" % (directory)], dsc_name)
                        if os.path.exists(in_otherdir):
                            in_otherdir_fh = utils.open_file(in_otherdir)
                            actual_md5 = apt_pkg.md5sum(in_otherdir_fh)
                            in_otherdir_fh.close()
                            actual_size = os.stat(in_otherdir)[stat.ST_SIZE]
                            found = in_otherdir
                            self.pkg.orig_tar_gz = in_otherdir

                    if not found:
                        self.reject("%s refers to %s, but I can't find it in the queue or in the pool." % (file, dsc_name))
                        self.pkg.orig_tar_gz = -1
                        continue
            else:
                self.reject("%s refers to %s, but I can't find it in the queue." % (file, dsc_name))
                continue
            if actual_md5 != dsc_entry["md5sum"]:
                self.reject("md5sum for %s doesn't match %s." % (found, file))
            if actual_size != int(dsc_entry["size"]):
                self.reject("size for %s doesn't match %s." % (found, file))

        return (self.reject_message, None)
