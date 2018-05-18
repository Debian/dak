#!/usr/bin/env python
# vim:set et sw=4:

"""
Queue utility functions for dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001 - 2006 James Troup <james@nocrew.org>
@copyright: 2009, 2010  Joerg Jaspert <joerg@debian.org>
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

import os
import utils
from types import *

from dak_exceptions import *
from changes import *
from regexes import *
from config import Config
from dbconn import *

################################################################################

def check_valid(overrides, session):
    """Check if section and priority for new overrides exist in database.

    Additionally does sanity checks:
      - debian-installer packages have to be udeb (or source)
      - non debian-installer packages cannot be udeb

    @type  overrides: list of dict
    @param overrides: list of overrides to check. The overrides need
                      to be given in form of a dict with the following keys:

                      - package: package name
                      - priority
                      - section
                      - component
                      - type: type of requested override ('dsc', 'deb' or 'udeb')

                      All values are strings.

    @rtype:  bool
    @return: C{True} if all overrides are valid, C{False} if there is any
             invalid override.
    """
    all_valid = True
    for o in overrides:
        o['valid'] = True
        if session.query(Priority).filter_by(priority=o['priority']).first() is None:
            o['valid'] = False
        if session.query(Section).filter_by(section=o['section']).first() is None:
            o['valid'] = False
        if get_mapped_component(o['component'], session) is None:
            o['valid'] = False
        if o['type'] not in ('dsc', 'deb', 'udeb'):
            raise Exception('Unknown override type {0}'.format(o['type']))
        if o['type'] == 'udeb' and o['section'] != 'debian-installer':
            o['valid'] = False
        if o['section'] == 'debian-installer' and o['type'] not in ('dsc', 'udeb'):
            o['valid'] = False
        all_valid = all_valid and o['valid']
    return all_valid

###############################################################################

def prod_maintainer(notes, upload):
    cnf = Config()
    changes = upload.changes
    whitelists = [ upload.target_suite.mail_whitelist ]

    # Here we prepare an editor and get them ready to prod...
    (fd, temp_filename) = utils.temp_filename()
    temp_file = os.fdopen(fd, 'w')
    temp_file.write("\n\n=====\n\n".join([note.comment for note in notes]))
    temp_file.close()
    editor = os.environ.get("EDITOR","vi")
    answer = 'E'
    while answer == 'E':
        os.system("%s %s" % (editor, temp_filename))
        temp_fh = utils.open_file(temp_filename)
        prod_message = "".join(temp_fh.readlines())
        temp_fh.close()
        print "Prod message:"
        print utils.prefix_multi_line_string(prod_message,"  ",include_blank_lines=1)
        prompt = "[P]rod, Edit, Abandon, Quit ?"
        answer = "XXX"
        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()
    os.unlink(temp_filename)
    if answer == 'A':
        return
    elif answer == 'Q':
        return 0
    # Otherwise, do the proding...
    user_email_address = utils.whoami() + " <%s>" % (
        cnf["Dinstall::MyAdminAddress"])

    changed_by = changes.changedby or changes.maintainer
    maintainer = changes.maintainer
    maintainer_to = utils.mail_addresses_for_upload(maintainer, changed_by, changes.fingerprint)

    Subst = {
        '__SOURCE__': upload.changes.source,
        '__CHANGES_FILENAME__': upload.changes.changesname,
        '__MAINTAINER_TO__': ", ".join(maintainer_to),
        }

    Subst["__FROM_ADDRESS__"] = user_email_address
    Subst["__PROD_MESSAGE__"] = prod_message
    Subst["__CC__"] = "Cc: " + cnf["Dinstall::MyEmailAddress"]

    prod_mail_message = utils.TemplateSubst(
        Subst,cnf["Dir::Templates"]+"/process-new.prod")

    # Send the prod mail
    utils.send_mail(prod_mail_message, whitelists=whitelists)

    print "Sent prodding message"

################################################################################

def edit_note(note, upload, session, trainee=False):
    # Write the current data to a temporary file
    (fd, temp_filename) = utils.temp_filename()
    editor = os.environ.get("EDITOR","vi")
    answer = 'E'
    while answer == 'E':
        os.system("%s %s" % (editor, temp_filename))
        temp_file = utils.open_file(temp_filename)
        newnote = temp_file.read().rstrip()
        temp_file.close()
        print "New Note:"
        print utils.prefix_multi_line_string(newnote,"  ")
        prompt = "[D]one, Edit, Abandon, Quit ?"
        answer = "XXX"
        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()
    os.unlink(temp_filename)
    if answer == 'A':
        return
    elif answer == 'Q':
        return 0

    comment = NewComment()
    comment.policy_queue = upload.policy_queue
    comment.package = upload.changes.source
    comment.version = upload.changes.version
    comment.comment = newnote
    comment.author  = utils.whoami()
    comment.trainee = trainee
    session.add(comment)
    session.commit()

###############################################################################

def get_suite_version_by_source(source, session):
    'returns a list of tuples (suite_name, version) for source package'
    q = session.query(Suite.suite_name, DBSource.version). \
        join(Suite.sources).filter_by(source = source)
    return q.all()

def get_suite_version_by_package(package, arch_string, session):
    '''
    returns a list of tuples (suite_name, version) for binary package and
    arch_string
    '''
    return session.query(Suite.suite_name, DBBinary.version). \
        join(Suite.binaries).filter_by(package = package). \
        join(DBBinary.architecture). \
        filter(Architecture.arch_string.in_([arch_string, 'all'])).all()

class Upload(object):
    """
    Everything that has to do with an upload processed.

    """
    def __init__(self):
        self.logger = None
        self.pkg = Changes()
        self.reset()

    ###########################################################################

    def update_subst(self):
        """ Set up the per-package template substitution mappings """
        raise Exception('to be removed')

        cnf = Config()

        # If 'dak process-unchecked' crashed out in the right place, architecture may still be a string.
        if "architecture" not in self.pkg.changes or not \
           isinstance(self.pkg.changes["architecture"], dict):
            self.pkg.changes["architecture"] = { "Unknown" : "" }

        # and maintainer2047 may not exist.
        if "maintainer2047" not in self.pkg.changes:
            self.pkg.changes["maintainer2047"] = cnf["Dinstall::MyEmailAddress"]

        self.Subst["__ARCHITECTURE__"] = " ".join(self.pkg.changes["architecture"].keys())
        self.Subst["__CHANGES_FILENAME__"] = os.path.basename(self.pkg.changes_file)
        self.Subst["__FILE_CONTENTS__"] = self.pkg.changes.get("filecontents", "")

        # For source uploads the Changed-By field wins; otherwise Maintainer wins.
        if "source" in self.pkg.changes["architecture"] and \
           self.pkg.changes["changedby822"] != "" and \
           (self.pkg.changes["changedby822"] != self.pkg.changes["maintainer822"]):

            self.Subst["__MAINTAINER_FROM__"] = self.pkg.changes["changedby2047"]
            self.Subst["__MAINTAINER_TO__"] = "%s, %s" % (self.pkg.changes["changedby2047"], self.pkg.changes["maintainer2047"])
            self.Subst["__MAINTAINER__"] = self.pkg.changes.get("changed-by", "Unknown")
        else:
            self.Subst["__MAINTAINER_FROM__"] = self.pkg.changes["maintainer2047"]
            self.Subst["__MAINTAINER_TO__"] = self.pkg.changes["maintainer2047"]
            self.Subst["__MAINTAINER__"] = self.pkg.changes.get("maintainer", "Unknown")

        # Process policy doesn't set the fingerprint field and I don't want to make it
        # do it for now as I don't want to have to deal with the case where we accepted
        # the package into PU-NEW, but the fingerprint has gone away from the keyring in
        # the meantime so the package will be remarked as rejectable.  Urgh.
        # TODO: Fix this properly
        if 'fingerprint' in self.pkg.changes:
            session = DBConn().session()
            fpr = get_fingerprint(self.pkg.changes['fingerprint'], session)
            if fpr and self.check_if_upload_is_sponsored("%s@debian.org" % fpr.uid.uid, fpr.uid.name):
                if "sponsoremail" in self.pkg.changes:
                    self.Subst["__MAINTAINER_TO__"] += ", %s" % self.pkg.changes["sponsoremail"]
            session.close()

        if "Dinstall::PackagesServer" in cnf and "source" in self.pkg.changes:
            self.Subst["__MAINTAINER_TO__"] += "\nBcc: %s@%s" % (self.pkg.changes["source"], cnf["Dinstall::PackagesServer"])

        # Apply any global override of the Maintainer field
        if cnf.get("Dinstall::OverrideMaintainer"):
            self.Subst["__MAINTAINER_TO__"] = cnf["Dinstall::OverrideMaintainer"]
            self.Subst["__MAINTAINER_FROM__"] = cnf["Dinstall::OverrideMaintainer"]

        self.Subst["__REJECT_MESSAGE__"] = self.package_info()
        self.Subst["__SOURCE__"] = self.pkg.changes.get("source", "Unknown")
        self.Subst["__VERSION__"] = self.pkg.changes.get("version", "Unknown")
        self.Subst["__SUITE__"] = ", ".join(self.pkg.changes["distribution"])

    ###########################################################################

    def check_if_upload_is_sponsored(self, uid_email, uid_name):
        for key in "maintaineremail", "changedbyemail", "maintainername", "changedbyname":
            if key not in self.pkg.changes:
                return False
        uid_email = '@'.join(uid_email.split('@')[:2])
        if uid_email in [self.pkg.changes["maintaineremail"], self.pkg.changes["changedbyemail"]]:
            sponsored = False
        elif uid_name in [self.pkg.changes["maintainername"], self.pkg.changes["changedbyname"]]:
            sponsored = False
            if uid_name == "":
                sponsored = True
        else:
            sponsored = True
            sponsor_addresses = utils.gpg_get_key_addresses(self.pkg.changes["fingerprint"])
            debian_emails = filter(lambda addr: addr.endswith('@debian.org'), sponsor_addresses)
            if uid_email not in debian_emails:
                if debian_emails:
                    uid_email = debian_emails[0]
            if ("source" in self.pkg.changes["architecture"] and uid_email and utils.is_email_alias(uid_email)):
                if (self.pkg.changes["maintaineremail"] not in sponsor_addresses and
                    self.pkg.changes["changedbyemail"] not in sponsor_addresses):
                        self.pkg.changes["sponsoremail"] = uid_email

        return sponsored

    ###########################################################################
    # End check_signed_by_key checks
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

        # Skip all of this if not sending mail to avoid confusing people
        if "Dinstall::Options::No-Mail" in cnf and cnf["Dinstall::Options::No-Mail"]:
            return ""

        # Only do announcements for source uploads with a recent dpkg-dev installed
        if float(self.pkg.changes.get("format", 0)) < 1.6 or \
           "source" not in self.pkg.changes["architecture"]:
            return ""

        announcetemplate = os.path.join(cnf["Dir::Templates"], 'process-unchecked.announce')

        lists_todo = {}
        summary = ""

        # Get a unique list of target lists
        for dist in self.pkg.changes["distribution"].keys():
            suite = get_suite(dist)
            if suite is None: continue
            for tgt in suite.announce:
                lists_todo[tgt] = 1

        self.Subst["__SHORT_SUMMARY__"] = short_summary

        for announce_list in lists_todo.keys():
            summary += "Announcing to %s\n" % (announce_list)

            if action:
                self.update_subst()
                self.Subst["__ANNOUNCE_LIST_ADDRESS__"] = announce_list
                if cnf.get("Dinstall::PackagesServer") and \
                   "source" in self.pkg.changes["architecture"]:
                    trackingsendto = "Bcc: %s@%s" % (self.pkg.changes["source"], cnf["Dinstall::PackagesServer"])
                    self.Subst["__ANNOUNCE_LIST_ADDRESS__"] += "\n" + trackingsendto

                mail_message = utils.TemplateSubst(self.Subst, announcetemplate)
                utils.send_mail(mail_message)

                del self.Subst["__ANNOUNCE_LIST_ADDRESS__"]

        if cnf.find_b("Dinstall::CloseBugs") and "Dinstall::BugServer" in cnf:
            summary = self.close_bugs(summary, action)

        del self.Subst["__SHORT_SUMMARY__"]

        return summary

    ###########################################################################

    def check_override(self):
        """
        Checks override entries for validity. Mails "Override disparity" warnings,
        if that feature is enabled.

        Abandons the check if
          - override disparity checks are disabled
          - mail sending is disabled
        """

        cnf = Config()

        # Abandon the check if override disparity checks have been disabled
        if not cnf.find_b("Dinstall::OverrideDisparityCheck"):
            return

        summary = self.pkg.check_override()

        if summary == "":
            return

        overridetemplate = os.path.join(cnf["Dir::Templates"], 'process-unchecked.override-disparity')

        self.update_subst()
        self.Subst["__SUMMARY__"] = summary
        mail_message = utils.TemplateSubst(self.Subst, overridetemplate)
        utils.send_mail(mail_message)
        del self.Subst["__SUMMARY__"]
