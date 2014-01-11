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

import errno
import os
import stat
import sys
import time
import apt_inst
import apt_pkg
import utils
import commands
import shutil
import textwrap
from types import *
from sqlalchemy.sql.expression import desc
from sqlalchemy.orm.exc import NoResultFound

from dak_exceptions import *
from changes import *
from regexes import *
from config import Config
from holding import Holding
from urgencylog import UrgencyLog
from dbconn import *
from summarystats import SummaryStats
from utils import parse_changes, check_dsc_files, build_package_list
from textutils import fix_maintainer
from lintian import parse_lintian_output, generate_reject_messages
from contents import UnpackedSource

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

# FIXME: Should move into the database
# suite names DMs can upload to
dm_suites = ['unstable', 'experimental', 'squeeze-backports','squeeze-backports-sloppy', 'wheezy-backports']

def get_newest_source(source, session):
    'returns the newest DBSource object in dm_suites'
    ## the most recent version of the package uploaded to unstable or
    ## experimental includes the field "DM-Upload-Allowed: yes" in the source
    ## section of its control file
    q = session.query(DBSource).filter_by(source = source). \
        filter(DBSource.suites.any(Suite.suite_name.in_(dm_suites))). \
        order_by(desc('source.version'))
    return q.first()

def get_suite_version_by_source(source, session):
    'returns a list of tuples (suite_name, version) for source package'
    q = session.query(Suite.suite_name, DBSource.version). \
        join(Suite.sources).filter_by(source = source)
    return q.all()

def get_source_by_package_and_suite(package, suite_name, session):
    '''
    returns a DBSource query filtered by DBBinary.package and this package's
    suite_name
    '''
    return session.query(DBSource). \
        join(DBSource.binaries).filter_by(package = package). \
        join(DBBinary.suites).filter_by(suite_name = suite_name)

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
        if not self.pkg.changes.has_key("architecture") or not \
           isinstance(self.pkg.changes["architecture"], dict):
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
        if self.pkg.changes.has_key('fingerprint'):
            session = DBConn().session()
            fpr = get_fingerprint(self.pkg.changes['fingerprint'], session)
            if fpr and self.check_if_upload_is_sponsored("%s@debian.org" % fpr.uid.uid, fpr.uid.name):
                if self.pkg.changes.has_key("sponsoremail"):
                    self.Subst["__MAINTAINER_TO__"] += ", %s" % self.pkg.changes["sponsoremail"]
            session.close()

        if cnf.has_key("Dinstall::TrackingServer") and self.pkg.changes.has_key("source"):
            self.Subst["__MAINTAINER_TO__"] += "\nBcc: %s@%s" % (self.pkg.changes["source"], cnf["Dinstall::TrackingServer"])

        # Apply any global override of the Maintainer field
        if cnf.get("Dinstall::OverrideMaintainer"):
            self.Subst["__MAINTAINER_TO__"] = cnf["Dinstall::OverrideMaintainer"]
            self.Subst["__MAINTAINER_FROM__"] = cnf["Dinstall::OverrideMaintainer"]

        self.Subst["__REJECT_MESSAGE__"] = self.package_info()
        self.Subst["__SOURCE__"] = self.pkg.changes.get("source", "Unknown")
        self.Subst["__VERSION__"] = self.pkg.changes.get("version", "Unknown")
        self.Subst["__SUITE__"] = ", ".join(self.pkg.changes["distribution"])

    ###########################################################################

    def check_distributions(self):
        "Check and map the Distribution field"

        Cnf = Config()

        # Handle suite mappings
        for m in Cnf.value_list("SuiteMappings"):
            args = m.split()
            mtype = args[0]
            if mtype == "map" or mtype == "silent-map":
                (source, dest) = args[1:3]
                if self.pkg.changes["distribution"].has_key(source):
                    del self.pkg.changes["distribution"][source]
                    self.pkg.changes["distribution"][dest] = 1
                    if mtype != "silent-map":
                        self.notes.append("Mapping %s to %s." % (source, dest))
                if self.pkg.changes.has_key("distribution-version"):
                    if self.pkg.changes["distribution-version"].has_key(source):
                        self.pkg.changes["distribution-version"][source]=dest
            elif mtype == "map-unreleased":
                (source, dest) = args[1:3]
                if self.pkg.changes["distribution"].has_key(source):
                    for arch in self.pkg.changes["architecture"].keys():
                        if arch not in [ a.arch_string for a in get_suite_architectures(source) ]:
                            self.notes.append("Mapping %s to %s for unreleased architecture %s." % (source, dest, arch))
                            del self.pkg.changes["distribution"][source]
                            self.pkg.changes["distribution"][dest] = 1
                            break
            elif mtype == "ignore":
                suite = args[1]
                if self.pkg.changes["distribution"].has_key(suite):
                    del self.pkg.changes["distribution"][suite]
                    self.warnings.append("Ignoring %s as a target suite." % (suite))
            elif mtype == "reject":
                suite = args[1]
                if self.pkg.changes["distribution"].has_key(suite):
                    self.rejects.append("Uploads to %s are not accepted." % (suite))
            elif mtype == "propup-version":
                # give these as "uploaded-to(non-mapped) suites-to-add-when-upload-obsoletes"
                #
                # changes["distribution-version"] looks like: {'testing': 'testing-proposed-updates'}
                if self.pkg.changes["distribution"].has_key(args[1]):
                    self.pkg.changes.setdefault("distribution-version", {})
                    for suite in args[2:]:
                        self.pkg.changes["distribution-version"][suite] = suite

        # Ensure there is (still) a target distribution
        if len(self.pkg.changes["distribution"].keys()) < 1:
            self.rejects.append("No valid distribution remaining.")

        # Ensure target distributions exist
        for suite in self.pkg.changes["distribution"].keys():
            if not get_suite(suite.lower()):
                self.rejects.append("Unknown distribution `%s'." % (suite))

    ###########################################################################

    def per_suite_file_checks(self, f, suite, session):
        raise Exception('removed')

        # Handle component mappings
        for m in cnf.value_list("ComponentMappings"):
            (source, dest) = m.split()
            if entry["component"] == source:
                entry["original component"] = source
                entry["component"] = dest

    ###########################################################################

    # Sanity check the time stamps of files inside debs.
    # [Files in the near future cause ugly warnings and extreme time
    #  travel can cause errors on extraction]

    def check_if_upload_is_sponsored(self, uid_email, uid_name):
        for key in "maintaineremail", "changedbyemail", "maintainername", "changedbyname":
            if not self.pkg.changes.has_key(key):
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

    def check_dm_upload(self, fpr, session):
        # Quoth the GR (http://www.debian.org/vote/2007/vote_003):
        ## none of the uploaded packages are NEW
        ## none of the packages are being taken over from other source packages
        for b in self.pkg.changes["binary"].keys():
            for suite in self.pkg.changes["distribution"].keys():
                for s in get_source_by_package_and_suite(b, suite, session):
                    if s.source != self.pkg.changes["source"]:
                        self.rejects.append("%s may not hijack %s from source package %s in suite %s" % (fpr.uid.uid, b, s, suite))

    ###########################################################################
    # End check_signed_by_key checks
    ###########################################################################

    def build_summaries(self):
        """ Build a summary of changes the upload introduces. """

        (byhand, new, summary, override_summary) = self.pkg.file_summary()

        short_summary = summary

        # This is for direport's benefit...
        f = re_fdnic.sub("\n .\n", self.pkg.changes.get("changes", ""))

        summary += "\n\nChanges:\n" + f

        summary += "\n\nOverride entries for your package:\n" + override_summary + "\n"

        summary += self.announce(short_summary, 0)

        return (summary, short_summary)

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
        if cnf.has_key("Dinstall::Options::No-Mail") and cnf["Dinstall::Options::No-Mail"]:
            return ""

        # Only do announcements for source uploads with a recent dpkg-dev installed
        if float(self.pkg.changes.get("format", 0)) < 1.6 or not \
           self.pkg.changes["architecture"].has_key("source"):
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
                if cnf.get("Dinstall::TrackingServer") and \
                   self.pkg.changes["architecture"].has_key("source"):
                    trackingsendto = "Bcc: %s@%s" % (self.pkg.changes["source"], cnf["Dinstall::TrackingServer"])
                    self.Subst["__ANNOUNCE_LIST_ADDRESS__"] += "\n" + trackingsendto

                mail_message = utils.TemplateSubst(self.Subst, announcetemplate)
                utils.send_mail(mail_message)

                del self.Subst["__ANNOUNCE_LIST_ADDRESS__"]

        if cnf.find_b("Dinstall::CloseBugs") and cnf.has_key("Dinstall::BugServer"):
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

    ################################################################################
    def get_anyversion(self, sv_list, suite):
        """
        @type sv_list: list
        @param sv_list: list of (suite, version) tuples to check

        @type suite: string
        @param suite: suite name

        Description: TODO
        """
        Cnf = Config()
        anyversion = None
        anysuite = [suite] + [ vc.reference.suite_name for vc in get_version_checks(suite, "Enhances") ]
        for (s, v) in sv_list:
            if s in [ x.lower() for x in anysuite ]:
                if not anyversion or apt_pkg.version_compare(anyversion, v) <= 0:
                    anyversion = v

        return anyversion

    ################################################################################

    def cross_suite_version_check(self, sv_list, filename, new_version, sourceful=False):
        """
        @type sv_list: list
        @param sv_list: list of (suite, version) tuples to check

        @type filename: string
        @param filename: XXX

        @type new_version: string
        @param new_version: XXX

        Ensure versions are newer than existing packages in target
        suites and that cross-suite version checking rules as
        set out in the conf file are satisfied.
        """

        cnf = Config()

        # Check versions for each target suite
        for target_suite in self.pkg.changes["distribution"].keys():
            # Check we can find the target suite
            ts = get_suite(target_suite)
            if ts is None:
                self.rejects.append("Cannot find target suite %s to perform version checks" % target_suite)
                continue

            must_be_newer_than = [ vc.reference.suite_name for vc in get_version_checks(target_suite, "MustBeNewerThan") ]
            must_be_older_than = [ vc.reference.suite_name for vc in get_version_checks(target_suite, "MustBeOlderThan") ]

            # Enforce "must be newer than target suite" even if conffile omits it
            if target_suite not in must_be_newer_than:
                must_be_newer_than.append(target_suite)

            for (suite, existent_version) in sv_list:
                vercmp = apt_pkg.version_compare(new_version, existent_version)

                if suite in must_be_newer_than and sourceful and vercmp < 1:
                    self.rejects.append("%s: old version (%s) in %s >= new version (%s) targeted at %s." % (filename, existent_version, suite, new_version, target_suite))

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
                            self.warnings.append("%s is mapped to, but not enhanced by %s - adding anyways" % (suite, addsuite))
                            self.pkg.changes.setdefault("propdistribution", {})
                            self.pkg.changes["propdistribution"][addsuite] = 1
                            cansave = 1
                        elif not target_version:
                            # not targets_version is true when the package is NEW
                            # we could just stick with the "...old version..." REJECT
                            # for this, I think.
                            self.rejects.append("Won't propogate NEW packages.")
                        elif apt_pkg.version_compare(new_version, add_version) < 0:
                            # propogation would be redundant. no need to reject though.
                            self.warnings.append("ignoring versionconflict: %s: old version (%s) in %s <= new version (%s) targeted at %s." % (filename, existent_version, suite, new_version, target_suite))
                            cansave = 1
                        elif apt_pkg.version_compare(new_version, add_version) > 0 and \
                             apt_pkg.version_compare(add_version, target_version) >= 0:
                            # propogate!!
                            self.warnings.append("Propogating upload to %s" % (addsuite))
                            self.pkg.changes.setdefault("propdistribution", {})
                            self.pkg.changes["propdistribution"][addsuite] = 1
                            cansave = 1

                    if not cansave:
                        self.rejects.append("%s: old version (%s) in %s <= new version (%s) targeted at %s." % (filename, existent_version, suite, new_version, target_suite))

    ################################################################################

    def accepted_checks(self, overwrite_checks, session):
        # Recheck anything that relies on the database; since that's not
        # frozen between accept and our run time when called from p-a.

        # overwrite_checks is set to False when installing to stable/oldstable

        propogate={}
        nopropogate={}

        for checkfile in self.pkg.files.keys():
            # The .orig.tar.gz can disappear out from under us is it's a
            # duplicate of one in the archive.
            if not self.pkg.files.has_key(checkfile):
                continue

            entry = self.pkg.files[checkfile]

            # propogate in the case it is in the override tables:
            for suite in self.pkg.changes.get("propdistribution", {}).keys():
                if self.in_override_p(entry["package"], entry["component"], suite, entry.get("dbtype",""), checkfile, session):
                    propogate[suite] = 1
                else:
                    nopropogate[suite] = 1

        for suite in propogate.keys():
            if suite in nopropogate:
                continue
            self.pkg.changes["distribution"][suite] = 1

        for checkfile in self.pkg.files.keys():
            # Check the package is still in the override tables
            for suite in self.pkg.changes["distribution"].keys():
                if not self.in_override_p(entry["package"], entry["component"], suite, entry.get("dbtype",""), checkfile, session):
                    self.rejects.append("%s is NEW for %s." % (checkfile, suite))
