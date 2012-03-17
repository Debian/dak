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

import yaml

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

###############################################################################

def get_type(f, session):
    """
    Get the file type of C{f}

    @type f: dict
    @param f: file entry from Changes object

    @type session: SQLA Session
    @param session: SQL Alchemy session object

    @rtype: string
    @return: filetype

    """
    # Determine the type
    if f.has_key("dbtype"):
        file_type = f["dbtype"]
    elif re_source_ext.match(f["type"]):
        file_type = "dsc"
    elif f['architecture'] == 'source' and f["type"] == 'unreadable':
        utils.warn('unreadable source file (will continue and hope for the best)')
        return f["type"]
    else:
        file_type = f["type"]
        utils.fubar("invalid type (%s) for new.  Dazed, confused and sure as heck not continuing." % (file_type))

    # Validate the override type
    type_id = get_override_type(file_type, session)
    if type_id is None:
        utils.fubar("invalid type (%s) for new.  Say wha?" % (file_type))

    return file_type

################################################################################

# Determine what parts in a .changes are NEW

def determine_new(filename, changes, files, warn=1, session = None, dsc = None, new = None):
    """
    Determine what parts in a C{changes} file are NEW.

    @type filename: str
    @param filename: changes filename

    @type changes: Upload.Pkg.changes dict
    @param changes: Changes dictionary

    @type files: Upload.Pkg.files dict
    @param files: Files dictionary

    @type warn: bool
    @param warn: Warn if overrides are added for (old)stable

    @type dsc: Upload.Pkg.dsc dict
    @param dsc: (optional); Dsc dictionary

    @type new: dict
    @param new: new packages as returned by a previous call to this function, but override information may have changed

    @rtype: dict
    @return: dictionary of NEW components.

    """
    # TODO: This should all use the database instead of parsing the changes
    # file again
    byhand = {}
    if new is None:
        new = {}

    dbchg = get_dbchange(filename, session)
    if dbchg is None:
        print "Warning: cannot find changes file in database; won't check byhand"

    # Try to get the Package-Set field from an included .dsc file (if possible).
    if dsc:
        for package, entry in build_package_list(dsc, session).items():
            if package not in new:
                new[package] = entry

    # Build up a list of potentially new things
    for name, f in files.items():
        # Keep a record of byhand elements
        if f["section"] == "byhand":
            byhand[name] = 1
            continue

        pkg = f["package"]
        priority = f["priority"]
        section = f["section"]
        file_type = get_type(f, session)
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

        new[pkg]["files"].append(name)

        if f.has_key("othercomponents"):
            new[pkg]["othercomponents"] = f["othercomponents"]

    # Fix up the list of target suites
    cnf = Config()
    for suite in changes["suite"].keys():
        oldsuite = get_suite(suite, session)
        if not oldsuite:
            print "WARNING: Invalid suite %s found" % suite
            continue

        if oldsuite.overridesuite:
            newsuite = get_suite(oldsuite.overridesuite, session)

            if newsuite:
                print "INFORMATION: Using overrides from suite %s instead of suite %s" % (
                    oldsuite.overridesuite, suite)
                del changes["suite"][suite]
                changes["suite"][oldsuite.overridesuite] = 1
            else:
                print "WARNING: Told to use overridesuite %s for %s but it doesn't exist.  Bugger" % (
                    oldsuite.overridesuite, suite)

    # Check for unprocessed byhand files
    if dbchg is not None:
        for b in byhand.keys():
            # Find the file entry in the database
            found = False
            for f in dbchg.files:
                if f.filename == b:
                    found = True
                    # If it's processed, we can ignore it
                    if f.processed:
                        del byhand[b]
                    break

            if not found:
                print "Warning: Couldn't find BYHAND item %s in the database; assuming unprocessed"

    # Check for new stuff
    for suite in changes["suite"].keys():
        for pkg in new.keys():
            ql = get_override(pkg, suite, new[pkg]["component"], new[pkg]["type"], session)
            if len(ql) > 0:
                for file_entry in new[pkg]["files"]:
                    if files[file_entry].has_key("new"):
                        del files[file_entry]["new"]
                del new[pkg]

    if warn:
        for s in ['stable', 'oldstable']:
            if changes["suite"].has_key(s):
                print "WARNING: overrides will be added for %s!" % s
        for pkg in new.keys():
            if new[pkg].has_key("othercomponents"):
                print "WARNING: %s already present in %s distribution." % (pkg, new[pkg]["othercomponents"])

    return new, byhand

################################################################################

def check_valid(new, session = None):
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
        section_name = new[pkg]["section"]
        priority_name = new[pkg]["priority"]
        file_type = new[pkg]["type"]

        section = get_section(section_name, session)
        if section is None:
            new[pkg]["section id"] = -1
        else:
            new[pkg]["section id"] = section.section_id

        priority = get_priority(priority_name, session)
        if priority is None:
            new[pkg]["priority id"] = -1
        else:
            new[pkg]["priority id"] = priority.priority_id

        # Sanity checks
        di = section_name.find("debian-installer") != -1

        # If d-i, we must be udeb and vice-versa
        if     (di and file_type not in ("udeb", "dsc")) or \
           (not di and file_type == "udeb"):
            new[pkg]["section id"] = -1

        # If dsc we need to be source and vice-versa
        if (priority == "source" and file_type != "dsc") or \
           (priority != "source" and file_type == "dsc"):
            new[pkg]["priority id"] = -1

###############################################################################

# Used by Upload.check_timestamps
class TarTime(object):
    def __init__(self, future_cutoff, past_cutoff):
        self.reset()
        self.future_cutoff = future_cutoff
        self.past_cutoff = past_cutoff

    def reset(self):
        self.future_files = {}
        self.ancient_files = {}

    def callback(self, member, data):
        if member.mtime > self.future_cutoff:
            self.future_files[Name] = member.mtime
        if member.mtime < self.past_cutoff:
            self.ancient_files[Name] = member.mtime

###############################################################################

def prod_maintainer(notes, upload):
    cnf = Config()

    # Here we prepare an editor and get them ready to prod...
    (fd, temp_filename) = utils.temp_filename()
    temp_file = os.fdopen(fd, 'w')
    for note in notes:
        temp_file.write(note.comment)
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
        end()
        sys.exit(0)
    # Otherwise, do the proding...
    user_email_address = utils.whoami() + " <%s>" % (
        cnf["Dinstall::MyAdminAddress"])

    Subst = upload.Subst

    Subst["__FROM_ADDRESS__"] = user_email_address
    Subst["__PROD_MESSAGE__"] = prod_message
    Subst["__CC__"] = "Cc: " + cnf["Dinstall::MyEmailAddress"]

    prod_mail_message = utils.TemplateSubst(
        Subst,cnf["Dir::Templates"]+"/process-new.prod")

    # Send the prod mail
    utils.send_mail(prod_mail_message)

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
        end()
        sys.exit(0)

    comment = NewComment()
    comment.package = upload.pkg.changes["source"]
    comment.version = upload.pkg.changes["version"]
    comment.comment = newnote
    comment.author  = utils.whoami()
    comment.trainee = trainee
    session.add(comment)
    session.commit()

###############################################################################

# FIXME: Should move into the database
# suite names DMs can upload to
dm_suites = ['unstable', 'experimental', 'squeeze-backports']

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

    def reset (self):
        """ Reset a number of internal variables."""

        # Initialize the substitution template map
        cnf = Config()
        self.Subst = {}
        self.Subst["__ADMIN_ADDRESS__"] = cnf["Dinstall::MyAdminAddress"]
        if cnf.has_key("Dinstall::BugServer"):
            self.Subst["__BUG_SERVER__"] = cnf["Dinstall::BugServer"]
        self.Subst["__DISTRO__"] = cnf["Dinstall::MyDistribution"]
        self.Subst["__DAK_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]

        self.rejects = []
        self.warnings = []
        self.notes = []

        self.later_check_files = []

        self.pkg.reset()

    def package_info(self):
        """
        Format various messages from this Upload to send to the maintainer.
        """

        msgs = (
            ('Reject Reasons', self.rejects),
            ('Warnings', self.warnings),
            ('Notes', self.notes),
        )

        msg = ''
        for title, messages in msgs:
            if messages:
                msg += '\n\n%s:\n%s' % (title, '\n'.join(messages))
        msg += '\n\n'

        return msg

    ###########################################################################
    def update_subst(self):
        """ Set up the per-package template substitution mappings """

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
    def load_changes(self, filename):
        """
        Load a changes file and setup a dictionary around it. Also checks for mandantory
        fields  within.

        @type filename: string
        @param filename: Changes filename, full path.

        @rtype: boolean
        @return: whether the changes file was valid or not.  We may want to
                 reject even if this is True (see what gets put in self.rejects).
                 This is simply to prevent us even trying things later which will
                 fail because we couldn't properly parse the file.
        """
        Cnf = Config()
        self.pkg.changes_file = filename

        # Parse the .changes field into a dictionary
        try:
            self.pkg.changes.update(parse_changes(filename))
        except CantOpenError:
            self.rejects.append("%s: can't read file." % (filename))
            return False
        except ParseChangesError as line:
            self.rejects.append("%s: parse error, can't grok: %s." % (filename, line))
            return False
        except ChangesUnicodeError:
            self.rejects.append("%s: changes file not proper utf-8" % (filename))
            return False

        # Parse the Files field from the .changes into another dictionary
        try:
            self.pkg.files.update(utils.build_file_list(self.pkg.changes))
        except ParseChangesError as line:
            self.rejects.append("%s: parse error, can't grok: %s." % (filename, line))
            return False
        except UnknownFormatError as format:
            self.rejects.append("%s: unknown format '%s'." % (filename, format))
            return False

        # Check for mandatory fields
        for i in ("distribution", "source", "binary", "architecture",
                  "version", "maintainer", "files", "changes", "description"):
            if not self.pkg.changes.has_key(i):
                # Avoid undefined errors later
                self.rejects.append("%s: Missing mandatory field `%s'." % (filename, i))
                return False

        # Strip a source version in brackets from the source field
        if re_strip_srcver.search(self.pkg.changes["source"]):
            self.pkg.changes["source"] = re_strip_srcver.sub('', self.pkg.changes["source"])

        # Ensure the source field is a valid package name.
        if not re_valid_pkg_name.match(self.pkg.changes["source"]):
            self.rejects.append("%s: invalid source name '%s'." % (filename, self.pkg.changes["source"]))

        # Split multi-value fields into a lower-level dictionary
        for i in ("architecture", "distribution", "binary", "closes"):
            o = self.pkg.changes.get(i, "")
            if o != "":
                del self.pkg.changes[i]

            self.pkg.changes[i] = {}

            for j in o.split():
                self.pkg.changes[i][j] = 1

        # Fix the Maintainer: field to be RFC822/2047 compatible
        try:
            (self.pkg.changes["maintainer822"],
             self.pkg.changes["maintainer2047"],
             self.pkg.changes["maintainername"],
             self.pkg.changes["maintaineremail"]) = \
                   fix_maintainer (self.pkg.changes["maintainer"])
        except ParseMaintError as msg:
            self.rejects.append("%s: Maintainer field ('%s') failed to parse: %s" \
                   % (filename, self.pkg.changes["maintainer"], msg))

        # ...likewise for the Changed-By: field if it exists.
        try:
            (self.pkg.changes["changedby822"],
             self.pkg.changes["changedby2047"],
             self.pkg.changes["changedbyname"],
             self.pkg.changes["changedbyemail"]) = \
                   fix_maintainer (self.pkg.changes.get("changed-by", ""))
        except ParseMaintError as msg:
            self.pkg.changes["changedby822"] = ""
            self.pkg.changes["changedby2047"] = ""
            self.pkg.changes["changedbyname"] = ""
            self.pkg.changes["changedbyemail"] = ""

            self.rejects.append("%s: Changed-By field ('%s') failed to parse: %s" \
                   % (filename, self.pkg.changes["changed-by"], msg))

        # Ensure all the values in Closes: are numbers
        if self.pkg.changes.has_key("closes"):
            for i in self.pkg.changes["closes"].keys():
                if re_isanum.match (i) == None:
                    self.rejects.append(("%s: `%s' from Closes field isn't a number." % (filename, i)))

        # chopversion = no epoch; chopversion2 = no epoch and no revision (e.g. for .orig.tar.gz comparison)
        self.pkg.changes["chopversion"] = re_no_epoch.sub('', self.pkg.changes["version"])
        self.pkg.changes["chopversion2"] = re_no_revision.sub('', self.pkg.changes["chopversion"])

        # Check the .changes is non-empty
        if not self.pkg.files:
            self.rejects.append("%s: nothing to do (Files field is empty)." % (os.path.basename(self.pkg.changes_file)))
            return False

        # Changes was syntactically valid even if we'll reject
        return True

    ###########################################################################

    def check_distributions(self):
        "Check and map the Distribution field"

        Cnf = Config()

        # Handle suite mappings
        for m in Cnf.ValueList("SuiteMappings"):
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

    def binary_file_checks(self, f, session):
        cnf = Config()
        entry = self.pkg.files[f]

        # Extract package control information
        deb_file = utils.open_file(f)
        try:
            control = apt_pkg.ParseSection(apt_inst.debExtractControl(deb_file))
        except:
            self.rejects.append("%s: debExtractControl() raised %s." % (f, sys.exc_info()[0]))
            deb_file.close()
            # Can't continue, none of the checks on control would work.
            return

        # Check for mandantory "Description:"
        deb_file.seek(0)
        try:
            apt_pkg.ParseSection(apt_inst.debExtractControl(deb_file))["Description"] + '\n'
        except:
            self.rejects.append("%s: Missing Description in binary package" % (f))
            return

        deb_file.close()

        # Check for mandatory fields
        for field in [ "Package", "Architecture", "Version" ]:
            if control.Find(field) == None:
                # Can't continue
                self.rejects.append("%s: No %s field in control." % (f, field))
                return

        # Ensure the package name matches the one give in the .changes
        if not self.pkg.changes["binary"].has_key(control.Find("Package", "")):
            self.rejects.append("%s: control file lists name as `%s', which isn't in changes file." % (f, control.Find("Package", "")))

        # Validate the package field
        package = control.Find("Package")
        if not re_valid_pkg_name.match(package):
            self.rejects.append("%s: invalid package name '%s'." % (f, package))

        # Validate the version field
        version = control.Find("Version")
        if not re_valid_version.match(version):
            self.rejects.append("%s: invalid version number '%s'." % (f, version))

        # Ensure the architecture of the .deb is one we know about.
        default_suite = cnf.get("Dinstall::DefaultSuite", "unstable")
        architecture = control.Find("Architecture")
        upload_suite = self.pkg.changes["distribution"].keys()[0]

        if      architecture not in [a.arch_string for a in get_suite_architectures(default_suite, session = session)] \
            and architecture not in [a.arch_string for a in get_suite_architectures(upload_suite, session = session)]:
            self.rejects.append("Unknown architecture '%s'." % (architecture))

        # Ensure the architecture of the .deb is one of the ones
        # listed in the .changes.
        if not self.pkg.changes["architecture"].has_key(architecture):
            self.rejects.append("%s: control file lists arch as `%s', which isn't in changes file." % (f, architecture))

        # Sanity-check the Depends field
        depends = control.Find("Depends")
        if depends == '':
            self.rejects.append("%s: Depends field is empty." % (f))

        # Sanity-check the Provides field
        provides = control.Find("Provides")
        if provides:
            provide = re_spacestrip.sub('', provides)
            if provide == '':
                self.rejects.append("%s: Provides field is empty." % (f))
            prov_list = provide.split(",")
            for prov in prov_list:
                if not re_valid_pkg_name.match(prov):
                    self.rejects.append("%s: Invalid Provides field content %s." % (f, prov))

        # If there is a Built-Using field, we need to check we can find the
        # exact source version
        built_using = control.Find("Built-Using")
        if built_using:
            try:
                entry["built-using"] = []
                for dep in apt_pkg.parse_depends(built_using):
                    bu_s, bu_v, bu_e = dep[0]
                    # Check that it's an exact match dependency and we have
                    # some form of version
                    if bu_e != "=" or len(bu_v) < 1:
                        self.rejects.append("%s: Built-Using contains non strict dependency (%s %s %s)" % (f, bu_s, bu_e, bu_v))
                    else:
                        # Find the source id for this version
                        bu_so = get_sources_from_name(bu_s, version=bu_v, session = session)
                        if len(bu_so) != 1:
                            self.rejects.append("%s: Built-Using (%s = %s): Cannot find source package" % (f, bu_s, bu_v))
                        else:
                            entry["built-using"].append( (bu_so[0].source, bu_so[0].version, ) )

            except ValueError as e:
                self.rejects.append("%s: Cannot parse Built-Using field: %s" % (f, str(e)))


        # Check the section & priority match those given in the .changes (non-fatal)
        if     control.Find("Section") and entry["section"] != "" \
           and entry["section"] != control.Find("Section"):
            self.warnings.append("%s control file lists section as `%s', but changes file has `%s'." % \
                                (f, control.Find("Section", ""), entry["section"]))
        if control.Find("Priority") and entry["priority"] != "" \
           and entry["priority"] != control.Find("Priority"):
            self.warnings.append("%s control file lists priority as `%s', but changes file has `%s'." % \
                                (f, control.Find("Priority", ""), entry["priority"]))

        entry["package"] = package
        entry["architecture"] = architecture
        entry["version"] = version
        entry["maintainer"] = control.Find("Maintainer", "")

        if f.endswith(".udeb"):
            self.pkg.files[f]["dbtype"] = "udeb"
        elif f.endswith(".deb"):
            self.pkg.files[f]["dbtype"] = "deb"
        else:
            self.rejects.append("%s is neither a .deb or a .udeb." % (f))

        entry["source"] = control.Find("Source", entry["package"])

        # Get the source version
        source = entry["source"]
        source_version = ""

        if source.find("(") != -1:
            m = re_extract_src_version.match(source)
            source = m.group(1)
            source_version = m.group(2)

        if not source_version:
            source_version = self.pkg.files[f]["version"]

        entry["source package"] = source
        entry["source version"] = source_version

        # Ensure the filename matches the contents of the .deb
        m = re_isadeb.match(f)

        #  package name
        file_package = m.group(1)
        if entry["package"] != file_package:
            self.rejects.append("%s: package part of filename (%s) does not match package name in the %s (%s)." % \
                                (f, file_package, entry["dbtype"], entry["package"]))
        epochless_version = re_no_epoch.sub('', control.Find("Version"))

        #  version
        file_version = m.group(2)
        if epochless_version != file_version:
            self.rejects.append("%s: version part of filename (%s) does not match package version in the %s (%s)." % \
                                (f, file_version, entry["dbtype"], epochless_version))

        #  architecture
        file_architecture = m.group(3)
        if entry["architecture"] != file_architecture:
            self.rejects.append("%s: architecture part of filename (%s) does not match package architecture in the %s (%s)." % \
                                (f, file_architecture, entry["dbtype"], entry["architecture"]))

        # Check for existent source
        source_version = entry["source version"]
        source_package = entry["source package"]
        if self.pkg.changes["architecture"].has_key("source"):
            if source_version != self.pkg.changes["version"]:
                self.rejects.append("source version (%s) for %s doesn't match changes version %s." % \
                                    (source_version, f, self.pkg.changes["version"]))
        else:
            # Check in the SQL database
            if not source_exists(source_package, source_version, suites = \
                self.pkg.changes["distribution"].keys(), session = session):
                # Check in one of the other directories
                source_epochless_version = re_no_epoch.sub('', source_version)
                dsc_filename = "%s_%s.dsc" % (source_package, source_epochless_version)

                byhand_dir = get_policy_queue('byhand', session).path
                new_dir = get_policy_queue('new', session).path

                if os.path.exists(os.path.join(byhand_dir, dsc_filename)):
                    entry["byhand"] = 1
                elif os.path.exists(os.path.join(new_dir, dsc_filename)):
                    entry["new"] = 1
                else:
                    dsc_file_exists = False
                    # TODO: Don't hardcode this list: use all relevant queues
                    #       The question is how to determine what is relevant
                    for queue_name in ["embargoed", "unembargoed", "proposedupdates", "oldproposedupdates"]:
                        queue = get_policy_queue(queue_name, session)
                        if queue:
                            if os.path.exists(os.path.join(queue.path, dsc_filename)):
                                dsc_file_exists = True
                                break

                    if not dsc_file_exists:
                        self.rejects.append("no source found for %s %s (%s)." % (source_package, source_version, f))

        # Check the version and for file overwrites
        self.check_binary_against_db(f, session)

    def source_file_checks(self, f, session):
        entry = self.pkg.files[f]

        m = re_issource.match(f)
        if not m:
            return

        entry["package"] = m.group(1)
        entry["version"] = m.group(2)
        entry["type"] = m.group(3)

        # Ensure the source package name matches the Source filed in the .changes
        if self.pkg.changes["source"] != entry["package"]:
            self.rejects.append("%s: changes file doesn't say %s for Source" % (f, entry["package"]))

        # Ensure the source version matches the version in the .changes file
        if re_is_orig_source.match(f):
            changes_version = self.pkg.changes["chopversion2"]
        else:
            changes_version = self.pkg.changes["chopversion"]

        if changes_version != entry["version"]:
            self.rejects.append("%s: should be %s according to changes file." % (f, changes_version))

        # Ensure the .changes lists source in the Architecture field
        if not self.pkg.changes["architecture"].has_key("source"):
            self.rejects.append("%s: changes file doesn't list `source' in Architecture field." % (f))

        # Check the signature of a .dsc file
        if entry["type"] == "dsc":
            # check_signature returns either:
            #  (None, [list, of, rejects]) or (signature, [])
            (self.pkg.dsc["fingerprint"], rejects) = utils.check_signature(f)
            for j in rejects:
                self.rejects.append(j)

        entry["architecture"] = "source"

    def per_suite_file_checks(self, f, suite, session):
        cnf = Config()
        entry = self.pkg.files[f]

        # Skip byhand
        if entry.has_key("byhand"):
            return

        # Check we have fields we need to do these checks
        oktogo = True
        for m in ['component', 'package', 'priority', 'size', 'md5sum']:
            if not entry.has_key(m):
                self.rejects.append("file '%s' does not have field %s set" % (f, m))
                oktogo = False

        if not oktogo:
            return

        # Handle component mappings
        for m in cnf.ValueList("ComponentMappings"):
            (source, dest) = m.split()
            if entry["component"] == source:
                entry["original component"] = source
                entry["component"] = dest

        # Ensure the component is valid for the target suite
        if entry["component"] not in get_component_names(session):
            self.rejects.append("unknown component `%s' for suite `%s'." % (entry["component"], suite))
            return

        # Validate the component
        if not get_component(entry["component"], session):
            self.rejects.append("file '%s' has unknown component '%s'." % (f, entry["component"]))
            return

        # See if the package is NEW
        if not self.in_override_p(entry["package"], entry["component"], suite, entry.get("dbtype",""), f, session):
            entry["new"] = 1

        # Validate the priority
        if entry["priority"].find('/') != -1:
            self.rejects.append("file '%s' has invalid priority '%s' [contains '/']." % (f, entry["priority"]))

        # Determine the location
        location = cnf["Dir::Pool"]
        l = get_location(location, entry["component"], session=session)
        if l is None:
            self.rejects.append("[INTERNAL ERROR] couldn't determine location (Component: %s)" % entry["component"])
            entry["location id"] = -1
        else:
            entry["location id"] = l.location_id

        # Check the md5sum & size against existing files (if any)
        entry["pool name"] = utils.poolify(self.pkg.changes["source"], entry["component"])

        found, poolfile = check_poolfile(os.path.join(entry["pool name"], f),
                                         entry["size"], entry["md5sum"], entry["location id"])

        if found is None:
            self.rejects.append("INTERNAL ERROR, get_files_id() returned multiple matches for %s." % (f))
        elif found is False and poolfile is not None:
            self.rejects.append("md5sum and/or size mismatch on existing copy of %s." % (f))
        else:
            if poolfile is None:
                entry["files id"] = None
            else:
                entry["files id"] = poolfile.file_id

        # Check for packages that have moved from one component to another
        entry['suite'] = suite
        arch_list = [entry["architecture"], 'all']
        component = get_component_by_package_suite(self.pkg.files[f]['package'], \
            [suite], arch_list = arch_list, session = session)
        if component is not None:
            entry["othercomponents"] = component

    def check_files(self, action=True):
        file_keys = self.pkg.files.keys()
        holding = Holding()
        cnf = Config()

        if action:
            cwd = os.getcwd()
            os.chdir(self.pkg.directory)
            for f in file_keys:
                ret = holding.copy_to_holding(f)
                if ret is not None:
                    self.warnings.append('Could not copy %s to holding; will attempt to find in DB later' % f)

            os.chdir(cwd)

        # check we already know the changes file
        # [NB: this check must be done post-suite mapping]
        base_filename = os.path.basename(self.pkg.changes_file)

        session = DBConn().session()

        try:
            dbc = session.query(DBChange).filter_by(changesname=base_filename).one()
            # if in the pool or in a queue other than unchecked, reject
            if (dbc.in_queue is None) \
                   or (dbc.in_queue is not None
                       and dbc.in_queue.queue_name not in ["unchecked", "newstage"]):
                self.rejects.append("%s file already known to dak" % base_filename)
        except NoResultFound as e:
            # not known, good
            pass

        has_binaries = False
        has_source = False

        for f, entry in self.pkg.files.items():
            # Ensure the file does not already exist in one of the accepted directories
            # TODO: Dynamically generate this list
            for queue_name in [ "byhand", "new", "proposedupdates", "oldproposedupdates", "embargoed", "unembargoed" ]:
                queue = get_policy_queue(queue_name, session)
                if queue and os.path.exists(os.path.join(queue.path, f)):
                    self.rejects.append("%s file already exists in the %s queue." % (f, queue_name))

            if not re_taint_free.match(f):
                self.rejects.append("!!WARNING!! tainted filename: '%s'." % (f))

            # Check the file is readable
            if os.access(f, os.R_OK) == 0:
                # When running in -n, copy_to_holding() won't have
                # generated the reject_message, so we need to.
                if action:
                    if os.path.exists(f):
                        self.rejects.append("Can't read `%s'. [permission denied]" % (f))
                    else:
                        # Don't directly reject, mark to check later to deal with orig's
                        # we can find in the pool
                        self.later_check_files.append(f)
                entry["type"] = "unreadable"
                continue

            # If it's byhand skip remaining checks
            if entry["section"] == "byhand" or entry["section"][:4] == "raw-":
                entry["byhand"] = 1
                entry["type"] = "byhand"

            # Checks for a binary package...
            elif re_isadeb.match(f):
                has_binaries = True
                entry["type"] = "deb"

                # This routine appends to self.rejects/warnings as appropriate
                self.binary_file_checks(f, session)

            # Checks for a source package...
            elif re_issource.match(f):
                has_source = True

                # This routine appends to self.rejects/warnings as appropriate
                self.source_file_checks(f, session)

            # Not a binary or source package?  Assume byhand...
            else:
                entry["byhand"] = 1
                entry["type"] = "byhand"

            # Per-suite file checks
            entry["oldfiles"] = {}
            for suite in self.pkg.changes["distribution"].keys():
                self.per_suite_file_checks(f, suite, session)

        session.close()

        # If the .changes file says it has source, it must have source.
        if self.pkg.changes["architecture"].has_key("source"):
            if not has_source:
                self.rejects.append("no source found and Architecture line in changes mention source.")

            if (not has_binaries) and (not cnf.FindB("Dinstall::AllowSourceOnlyUploads")):
                self.rejects.append("source only uploads are not supported.")

    ###########################################################################

    def __dsc_filename(self):
        """
        Returns: (Status, Dsc_Filename)
        where
          Status: Boolean; True when there was no error, False otherwise
          Dsc_Filename: String; name of the dsc file if Status is True, reason for the error otherwise
        """
        dsc_filename = None

        # find the dsc
        for name, entry in self.pkg.files.items():
            if entry.has_key("type") and entry["type"] == "dsc":
                if dsc_filename:
                    return False, "cannot process a .changes file with multiple .dsc's."
                else:
                    dsc_filename = name

        if not dsc_filename:
            return False, "source uploads must contain a dsc file"

        return True, dsc_filename

    def load_dsc(self, action=True, signing_rules=1):
        """
        Find and load the dsc from self.pkg.files into self.dsc

        Returns: (Status, Reason)
        where
          Status: Boolean; True when there was no error, False otherwise
          Reason: String; When Status is False this describes the error
        """

        # find the dsc
        (status, dsc_filename) = self.__dsc_filename()
        if not status:
            # If status is false, dsc_filename has the reason
            return False, dsc_filename

        try:
            self.pkg.dsc.update(utils.parse_changes(dsc_filename, signing_rules=signing_rules, dsc_file=1))
        except CantOpenError:
            if not action:
                return False, "%s: can't read file." % (dsc_filename)
        except ParseChangesError as line:
            return False, "%s: parse error, can't grok: %s." % (dsc_filename, line)
        except InvalidDscError as line:
            return False, "%s: syntax error on line %s." % (dsc_filename, line)
        except ChangesUnicodeError:
            return False, "%s: dsc file not proper utf-8." % (dsc_filename)

        return True, None

    ###########################################################################

    def check_dsc(self, action=True, session=None):
        """Returns bool indicating whether or not the source changes are valid"""
        # Ensure there is source to check
        if not self.pkg.changes["architecture"].has_key("source"):
            return True

        if session is None:
            session = DBConn().session()

        (status, reason) = self.load_dsc(action=action)
        if not status:
            self.rejects.append(reason)
            return False
        (status, dsc_filename) = self.__dsc_filename()
        if not status:
            # If status is false, dsc_filename has the reason
            self.rejects.append(dsc_filename)
            return False

        # Build up the file list of files mentioned by the .dsc
        try:
            self.pkg.dsc_files.update(utils.build_file_list(self.pkg.dsc, is_a_dsc=1))
        except NoFilesFieldError:
            self.rejects.append("%s: no Files: field." % (dsc_filename))
            return False
        except UnknownFormatError as format:
            self.rejects.append("%s: unknown format '%s'." % (dsc_filename, format))
            return False
        except ParseChangesError as line:
            self.rejects.append("%s: parse error, can't grok: %s." % (dsc_filename, line))
            return False

        # Enforce mandatory fields
        for i in ("format", "source", "version", "binary", "maintainer", "architecture", "files"):
            if not self.pkg.dsc.has_key(i):
                self.rejects.append("%s: missing mandatory field `%s'." % (dsc_filename, i))
                return False

        # Validate the source and version fields
        if not re_valid_pkg_name.match(self.pkg.dsc["source"]):
            self.rejects.append("%s: invalid source name '%s'." % (dsc_filename, self.pkg.dsc["source"]))
        if not re_valid_version.match(self.pkg.dsc["version"]):
            self.rejects.append("%s: invalid version number '%s'." % (dsc_filename, self.pkg.dsc["version"]))

        # Only a limited list of source formats are allowed in each suite
        for dist in self.pkg.changes["distribution"].keys():
            suite = get_suite(dist, session=session)
            if not suite:
                self.rejects.append("%s: cannot find suite %s when checking source formats" % (dsc_filename, dist))
                continue
            allowed = [ x.format_name for x in suite.srcformats ]
            if self.pkg.dsc["format"] not in allowed:
                self.rejects.append("%s: source format '%s' not allowed in %s (accepted: %s) " % (dsc_filename, self.pkg.dsc["format"], dist, ", ".join(allowed)))

        # Validate the Maintainer field
        try:
            # We ignore the return value
            fix_maintainer(self.pkg.dsc["maintainer"])
        except ParseMaintError as msg:
            self.rejects.append("%s: Maintainer field ('%s') failed to parse: %s" \
                                 % (dsc_filename, self.pkg.dsc["maintainer"], msg))

        # Validate the build-depends field(s)
        for field_name in [ "build-depends", "build-depends-indep" ]:
            field = self.pkg.dsc.get(field_name)
            if field:
                # Have apt try to parse them...
                try:
                    apt_pkg.ParseSrcDepends(field)
                except:
                    self.rejects.append("%s: invalid %s field (can not be parsed by apt)." % (dsc_filename, field_name.title()))

        # Ensure the version number in the .dsc matches the version number in the .changes
        epochless_dsc_version = re_no_epoch.sub('', self.pkg.dsc["version"])
        changes_version = self.pkg.files[dsc_filename]["version"]

        if epochless_dsc_version != self.pkg.files[dsc_filename]["version"]:
            self.rejects.append("version ('%s') in .dsc does not match version ('%s') in .changes." % (epochless_dsc_version, changes_version))

        # Ensure the Files field contain only what's expected
        self.rejects.extend(check_dsc_files(dsc_filename, self.pkg.dsc, self.pkg.dsc_files))

        # Ensure source is newer than existing source in target suites
        session = DBConn().session()
        self.check_source_against_db(dsc_filename, session)
        self.check_dsc_against_db(dsc_filename, session)

        dbchg = get_dbchange(self.pkg.changes_file, session)

        # Finally, check if we're missing any files
        for f in self.later_check_files:
            print 'XXX: %s' % f
            # Check if we've already processed this file if we have a dbchg object
            ok = False
            if dbchg:
                for pf in dbchg.files:
                    if pf.filename == f and pf.processed:
                        self.notes.append('%s was already processed so we can go ahead' % f)
                        ok = True
                        del self.pkg.files[f]
            if not ok:
                self.rejects.append("Could not find file %s references in changes" % f)

        session.close()

        return (len(self.rejects) == 0)

    ###########################################################################

    def get_changelog_versions(self, source_dir):
        """Extracts a the source package and (optionally) grabs the
        version history out of debian/changelog for the BTS."""

        cnf = Config()

        # Find the .dsc (again)
        dsc_filename = None
        for f in self.pkg.files.keys():
            if self.pkg.files[f]["type"] == "dsc":
                dsc_filename = f

        # If there isn't one, we have nothing to do. (We have reject()ed the upload already)
        if not dsc_filename:
            return

        # Create a symlink mirror of the source files in our temporary directory
        for f in self.pkg.files.keys():
            m = re_issource.match(f)
            if m:
                src = os.path.join(source_dir, f)
                # If a file is missing for whatever reason, give up.
                if not os.path.exists(src):
                    return
                ftype = m.group(3)
                if re_is_orig_source.match(f) and self.pkg.orig_files.has_key(f) and \
                   self.pkg.orig_files[f].has_key("path"):
                    continue
                dest = os.path.join(os.getcwd(), f)
                os.symlink(src, dest)

        # If the orig files are not a part of the upload, create symlinks to the
        # existing copies.
        for orig_file in self.pkg.orig_files.keys():
            if not self.pkg.orig_files[orig_file].has_key("path"):
                continue
            dest = os.path.join(os.getcwd(), os.path.basename(orig_file))
            os.symlink(self.pkg.orig_files[orig_file]["path"], dest)

        # Extract the source
        try:
            unpacked = UnpackedSource(dsc_filename)
        except Exception as e:
            self.rejects.append("'dpkg-source -x' failed for %s. (%s)" % (dsc_filename, str(e)))
            return

        if not cnf.Find("Dir::BTSVersionTrack"):
            return

        # Get the upstream version
        upstr_version = re_no_epoch.sub('', self.pkg.dsc["version"])
        if re_strip_revision.search(upstr_version):
            upstr_version = re_strip_revision.sub('', upstr_version)

        # Ensure the changelog file exists
        changelog_file = unpacked.get_changelog_file()
        if changelog_file is None:
            self.rejects.append("%s: debian/changelog not found in extracted source." % (dsc_filename))
            return

        # Parse the changelog
        self.pkg.dsc["bts changelog"] = ""
        for line in changelog_file.readlines():
            m = re_changelog_versions.match(line)
            if m:
                self.pkg.dsc["bts changelog"] += line
        changelog_file.close()
        unpacked.cleanup()

        # Check we found at least one revision in the changelog
        if not self.pkg.dsc["bts changelog"]:
            self.rejects.append("%s: changelog format not recognised (empty version tree)." % (dsc_filename))

    def check_source(self):
        # Bail out if:
        #    a) there's no source
        if not self.pkg.changes["architecture"].has_key("source"):
            return

        tmpdir = utils.temp_dirname()

        # Move into the temporary directory
        cwd = os.getcwd()
        os.chdir(tmpdir)

        # Get the changelog version history
        self.get_changelog_versions(cwd)

        # Move back and cleanup the temporary tree
        os.chdir(cwd)

        try:
            shutil.rmtree(tmpdir)
        except OSError as e:
            if e.errno != errno.EACCES:
                print "foobar"
                utils.fubar("%s: couldn't remove tmp dir for source tree." % (self.pkg.dsc["source"]))

            self.rejects.append("%s: source tree could not be cleanly removed." % (self.pkg.dsc["source"]))
            # We probably have u-r or u-w directories so chmod everything
            # and try again.
            cmd = "chmod -R u+rwx %s" % (tmpdir)
            result = os.system(cmd)
            if result != 0:
                utils.fubar("'%s' failed with result %s." % (cmd, result))
            shutil.rmtree(tmpdir)
        except Exception as e:
            print "foobar2 (%s)" % e
            utils.fubar("%s: couldn't remove tmp dir for source tree." % (self.pkg.dsc["source"]))

    ###########################################################################
    def ensure_hashes(self):
        # Make sure we recognise the format of the Files: field in the .changes
        format = self.pkg.changes.get("format", "0.0").split(".", 1)
        if len(format) == 2:
            format = int(format[0]), int(format[1])
        else:
            format = int(float(format[0])), 0

        # We need to deal with the original changes blob, as the fields we need
        # might not be in the changes dict serialised into the .dak anymore.
        orig_changes = utils.parse_deb822(self.pkg.changes['filecontents'])

        # Copy the checksums over to the current changes dict.  This will keep
        # the existing modifications to it intact.
        for field in orig_changes:
            if field.startswith('checksums-'):
                self.pkg.changes[field] = orig_changes[field]

        # Check for unsupported hashes
        for j in utils.check_hash_fields(".changes", self.pkg.changes):
            self.rejects.append(j)

        for j in utils.check_hash_fields(".dsc", self.pkg.dsc):
            self.rejects.append(j)

        # We have to calculate the hash if we have an earlier changes version than
        # the hash appears in rather than require it exist in the changes file
        for hashname, hashfunc, version in utils.known_hashes:
            # TODO: Move _ensure_changes_hash into this class
            for j in utils._ensure_changes_hash(self.pkg.changes, format, version, self.pkg.files, hashname, hashfunc):
                self.rejects.append(j)
            if "source" in self.pkg.changes["architecture"]:
                # TODO: Move _ensure_dsc_hash into this class
                for j in utils._ensure_dsc_hash(self.pkg.dsc, self.pkg.dsc_files, hashname, hashfunc):
                    self.rejects.append(j)

    def check_hashes(self):
        for m in utils.check_hash(".changes", self.pkg.files, "md5", apt_pkg.md5sum):
            self.rejects.append(m)

        for m in utils.check_size(".changes", self.pkg.files):
            self.rejects.append(m)

        for m in utils.check_hash(".dsc", self.pkg.dsc_files, "md5", apt_pkg.md5sum):
            self.rejects.append(m)

        for m in utils.check_size(".dsc", self.pkg.dsc_files):
            self.rejects.append(m)

        self.ensure_hashes()

    ###########################################################################

    def ensure_orig(self, target_dir='.', session=None):
        """
        Ensures that all orig files mentioned in the changes file are present
        in target_dir. If they do not exist, they are symlinked into place.

        An list containing the symlinks that were created are returned (so they
        can be removed).
        """

        symlinked = []
        cnf = Config()

        for filename, entry in self.pkg.dsc_files.iteritems():
            if not re_is_orig_source.match(filename):
                # File is not an orig; ignore
                continue

            if os.path.exists(filename):
                # File exists, no need to continue
                continue

            def symlink_if_valid(path):
                f = utils.open_file(path)
                md5sum = apt_pkg.md5sum(f)
                f.close()

                fingerprint = (os.stat(path)[stat.ST_SIZE], md5sum)
                expected = (int(entry['size']), entry['md5sum'])

                if fingerprint != expected:
                    return False

                dest = os.path.join(target_dir, filename)

                os.symlink(path, dest)
                symlinked.append(dest)

                return True

            session_ = session
            if session is None:
                session_ = DBConn().session()

            found = False

            # Look in the pool
            for poolfile in get_poolfile_like_name('%s' % filename, session_):
                poolfile_path = os.path.join(
                    poolfile.location.path, poolfile.filename
                )

                if symlink_if_valid(poolfile_path):
                    found = True
                    break

            if session is None:
                session_.close()

            if found:
                continue

            # Look in some other queues for the file
            queue_names = ['new', 'byhand',
                           'proposedupdates', 'oldproposedupdates',
                           'embargoed', 'unembargoed']

            for queue_name in queue_names:
                queue = get_policy_queue(queue_name, session)
                if not queue:
                    continue

                queuefile_path = os.path.join(queue.path, filename)

                if not os.path.exists(queuefile_path):
                    # Does not exist in this queue
                    continue

                if symlink_if_valid(queuefile_path):
                    break

        return symlinked

    ###########################################################################

    def check_lintian(self):
        """
        Extends self.rejects by checking the output of lintian against tags
        specified in Dinstall::LintianTags.
        """

        cnf = Config()

        # Don't reject binary uploads
        if not self.pkg.changes['architecture'].has_key('source'):
            return

        # Only check some distributions
        for dist in ('unstable', 'experimental'):
            if dist in self.pkg.changes['distribution']:
                break
        else:
            return

        # If we do not have a tagfile, don't do anything
        tagfile = cnf.get("Dinstall::LintianTags")
        if not tagfile:
            return

        # Parse the yaml file
        sourcefile = file(tagfile, 'r')
        sourcecontent = sourcefile.read()
        sourcefile.close()

        try:
            lintiantags = yaml.load(sourcecontent)['lintian']
        except yaml.YAMLError as msg:
            utils.fubar("Can not read the lintian tags file %s, YAML error: %s." % (tagfile, msg))
            return

        # Try and find all orig mentioned in the .dsc
        symlinked = self.ensure_orig()

        # Setup the input file for lintian
        fd, temp_filename = utils.temp_filename()
        temptagfile = os.fdopen(fd, 'w')
        for tags in lintiantags.values():
            temptagfile.writelines(['%s\n' % x for x in tags])
        temptagfile.close()

        try:
            cmd = "lintian --show-overrides --tags-from-file %s %s" % \
                (temp_filename, self.pkg.changes_file)

            result, output = commands.getstatusoutput(cmd)
        finally:
            # Remove our tempfile and any symlinks we created
            os.unlink(temp_filename)

            for symlink in symlinked:
                os.unlink(symlink)

        if result == 2:
            utils.warn("lintian failed for %s [return code: %s]." % \
                (self.pkg.changes_file, result))
            utils.warn(utils.prefix_multi_line_string(output, \
                " [possible output:] "))

        def log(*txt):
            if self.logger:
                self.logger.log(
                    [self.pkg.changes_file, "check_lintian"] + list(txt)
                )

        # Generate messages
        parsed_tags = parse_lintian_output(output)
        self.rejects.extend(
            generate_reject_messages(parsed_tags, lintiantags, log=log)
        )

    ###########################################################################
    def check_urgency(self):
        cnf = Config()
        if self.pkg.changes["architecture"].has_key("source"):
            if not self.pkg.changes.has_key("urgency"):
                self.pkg.changes["urgency"] = cnf["Urgency::Default"]
            self.pkg.changes["urgency"] = self.pkg.changes["urgency"].lower()
            if self.pkg.changes["urgency"] not in cnf.ValueList("Urgency::Valid"):
                self.warnings.append("%s is not a valid urgency; it will be treated as %s by testing." % \
                                     (self.pkg.changes["urgency"], cnf["Urgency::Default"]))
                self.pkg.changes["urgency"] = cnf["Urgency::Default"]

    ###########################################################################

    # Sanity check the time stamps of files inside debs.
    # [Files in the near future cause ugly warnings and extreme time
    #  travel can cause errors on extraction]

    def check_timestamps(self):
        Cnf = Config()

        future_cutoff = time.time() + int(Cnf["Dinstall::FutureTimeTravelGrace"])
        past_cutoff = time.mktime(time.strptime(Cnf["Dinstall::PastCutoffYear"],"%Y"))
        tar = TarTime(future_cutoff, past_cutoff)

        for filename, entry in self.pkg.files.items():
            if entry["type"] == "deb":
                tar.reset()
                try:
                    deb = apt_inst.DebFile(filename)
                    deb.control.go(tar.callback)

                    future_files = tar.future_files.keys()
                    if future_files:
                        num_future_files = len(future_files)
                        future_file = future_files[0]
                        future_date = tar.future_files[future_file]
                        self.rejects.append("%s: has %s file(s) with a time stamp too far into the future (e.g. %s [%s])."
                               % (filename, num_future_files, future_file, time.ctime(future_date)))

                    ancient_files = tar.ancient_files.keys()
                    if ancient_files:
                        num_ancient_files = len(ancient_files)
                        ancient_file = ancient_files[0]
                        ancient_date = tar.ancient_files[ancient_file]
                        self.rejects.append("%s: has %s file(s) with a time stamp too ancient (e.g. %s [%s])."
                               % (filename, num_ancient_files, ancient_file, time.ctime(ancient_date)))
                except:
                    self.rejects.append("%s: deb contents timestamp check failed [%s: %s]" % (filename, sys.exc_info()[0], sys.exc_info()[1]))

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


    ###########################################################################
    # check_signed_by_key checks
    ###########################################################################

    def check_signed_by_key(self):
        """Ensure the .changes is signed by an authorized uploader."""
        session = DBConn().session()

        # First of all we check that the person has proper upload permissions
        # and that this upload isn't blocked
        fpr = get_fingerprint(self.pkg.changes['fingerprint'], session=session)

        if fpr is None:
            self.rejects.append("Cannot find fingerprint %s" % self.pkg.changes["fingerprint"])
            return

        # TODO: Check that import-keyring adds UIDs properly
        if not fpr.uid:
            self.rejects.append("Cannot find uid for fingerprint %s.  Please contact ftpmaster@debian.org" % fpr.fingerprint)
            return

        # Check that the fingerprint which uploaded has permission to do so
        self.check_upload_permissions(fpr, session)

        # Check that this package is not in a transition
        self.check_transition(session)

        session.close()


    def check_upload_permissions(self, fpr, session):
        # Check any one-off upload blocks
        self.check_upload_blocks(fpr, session)

        # If the source_acl is None, source is never allowed
        if fpr.source_acl is None:
            if self.pkg.changes["architecture"].has_key("source"):
                rej = 'Fingerprint %s may not upload source' % fpr.fingerprint
                rej += '\nPlease contact ftpmaster if you think this is incorrect'
                self.rejects.append(rej)
                return
        # Do DM as a special case
        # DM is a special case unfortunately, so we check it first
        # (keys with no source access get more access than DMs in one
        #  way; DMs can only upload for their packages whether source
        #  or binary, whereas keys with no access might be able to
        #  upload some binaries)
        elif fpr.source_acl.access_level == 'dm':
            self.check_dm_upload(fpr, session)
        else:
            # If not a DM, we allow full upload rights
            uid_email = "%s@debian.org" % (fpr.uid.uid)
            self.check_if_upload_is_sponsored(uid_email, fpr.uid.name)


        # Check binary upload permissions
        # By this point we know that DMs can't have got here unless they
        # are allowed to deal with the package concerned so just apply
        # normal checks
        if fpr.binary_acl.access_level == 'full':
            return

        # Otherwise we're in the map case
        tmparches = self.pkg.changes["architecture"].copy()
        tmparches.pop('source', None)

        for bam in fpr.binary_acl_map:
            tmparches.pop(bam.architecture.arch_string, None)

        if len(tmparches.keys()) > 0:
            if fpr.binary_reject:
                rej = "changes file contains files of architectures not permitted for fingerprint %s" % fpr.fingerprint
                if len(tmparches.keys()) == 1:
                    rej += "\n\narchitecture involved is: %s" % ",".join(tmparches.keys())
                else:
                    rej += "\n\narchitectures involved are: %s" % ",".join(tmparches.keys())
                self.rejects.append(rej)
            else:
                # TODO: This is where we'll implement reject vs throw away binaries later
                rej = "Uhm.  I'm meant to throw away the binaries now but that's not implemented yet"
                rej += "\nPlease complain to ftpmaster@debian.org as this shouldn't have been turned on"
                rej += "\nFingerprint: %s", (fpr.fingerprint)
                self.rejects.append(rej)


    def check_upload_blocks(self, fpr, session):
        """Check whether any upload blocks apply to this source, source
           version, uid / fpr combination"""

        def block_rej_template(fb):
            rej = 'Manual upload block in place for package %s' % fb.source
            if fb.version is not None:
                rej += ', version %s' % fb.version
            return rej

        for fb in session.query(UploadBlock).filter_by(source = self.pkg.changes['source']).all():
            # version is None if the block applies to all versions
            if fb.version is None or fb.version == self.pkg.changes['version']:
                # Check both fpr and uid - either is enough to cause a reject
                if fb.fpr is not None:
                    if fb.fpr.fingerprint == fpr.fingerprint:
                        self.rejects.append(block_rej_template(fb) + ' for fingerprint %s\nReason: %s' % (fpr.fingerprint, fb.reason))
                if fb.uid is not None:
                    if fb.uid == fpr.uid:
                        self.rejects.append(block_rej_template(fb) + ' for uid %s\nReason: %s' % (fb.uid.uid, fb.reason))


    def check_dm_upload(self, fpr, session):
        # Quoth the GR (http://www.debian.org/vote/2007/vote_003):
        ## none of the uploaded packages are NEW
        rej = False
        for f in self.pkg.files.keys():
            if self.pkg.files[f].has_key("byhand"):
                self.rejects.append("%s may not upload BYHAND file %s" % (fpr.uid.uid, f))
                rej = True
            if self.pkg.files[f].has_key("new"):
                self.rejects.append("%s may not upload NEW file %s" % (fpr.uid.uid, f))
                rej = True

        if rej:
            return

        r = get_newest_source(self.pkg.changes["source"], session)

        if r is None:
            rej = "Could not find existing source package %s in the DM allowed suites and this is a DM upload" % self.pkg.changes["source"]
            self.rejects.append(rej)
            return

        if not r.dm_upload_allowed:
            rej = "Source package %s does not have 'DM-Upload-Allowed: yes' in its most recent version (%s)" % (self.pkg.changes["source"], r.version)
            self.rejects.append(rej)
            return

        ## the Maintainer: field of the uploaded .changes file corresponds with
        ## the owner of the key used (ie, non-developer maintainers may not sponsor
        ## uploads)
        if self.check_if_upload_is_sponsored(fpr.uid.uid, fpr.uid.name):
            self.rejects.append("%s (%s) is not authorised to sponsor uploads" % (fpr.uid.uid, fpr.fingerprint))

        ## the most recent version of the package uploaded to unstable or
        ## experimental lists the uploader in the Maintainer: or Uploaders: fields (ie,
        ## non-developer maintainers cannot NMU or hijack packages)

        # uploader includes the maintainer
        accept = False
        for uploader in r.uploaders:
            (rfc822, rfc2047, name, email) = uploader.get_split_maintainer()
            # Eww - I hope we never have two people with the same name in Debian
            if email == fpr.uid.uid or name == fpr.uid.name:
                accept = True
                break

        if not accept:
            self.rejects.append("%s is not in Maintainer or Uploaders of source package %s" % (fpr.uid.uid, self.pkg.changes["source"]))
            return

        ## none of the packages are being taken over from other source packages
        for b in self.pkg.changes["binary"].keys():
            for suite in self.pkg.changes["distribution"].keys():
                for s in get_source_by_package_and_suite(b, suite, session):
                    if s.source != self.pkg.changes["source"]:
                        self.rejects.append("%s may not hijack %s from source package %s in suite %s" % (fpr.uid.uid, b, s, suite))



    def check_transition(self, session):
        cnf = Config()

        sourcepkg = self.pkg.changes["source"]

        # No sourceful upload -> no need to do anything else, direct return
        # We also work with unstable uploads, not experimental or those going to some
        # proposed-updates queue
        if "source" not in self.pkg.changes["architecture"] or \
           "unstable" not in self.pkg.changes["distribution"]:
            return

        # Also only check if there is a file defined (and existant) with
        # checks.
        transpath = cnf.get("Dinstall::ReleaseTransitions", "")
        if transpath == "" or not os.path.exists(transpath):
            return

        # Parse the yaml file
        sourcefile = file(transpath, 'r')
        sourcecontent = sourcefile.read()
        try:
            transitions = yaml.load(sourcecontent)
        except yaml.YAMLError as msg:
            # This shouldn't happen, there is a wrapper to edit the file which
            # checks it, but we prefer to be safe than ending up rejecting
            # everything.
            utils.warn("Not checking transitions, the transitions file is broken: %s." % (msg))
            return

        # Now look through all defined transitions
        for trans in transitions:
            t = transitions[trans]
            source = t["source"]
            expected = t["new"]

            # Will be None if nothing is in testing.
            current = get_source_in_suite(source, "testing", session)
            if current is not None:
                compare = apt_pkg.VersionCompare(current.version, expected)

            if current is None or compare < 0:
                # This is still valid, the current version in testing is older than
                # the new version we wait for, or there is none in testing yet

                # Check if the source we look at is affected by this.
                if sourcepkg in t['packages']:
                    # The source is affected, lets reject it.

                    rejectmsg = "%s: part of the %s transition.\n\n" % (
                        sourcepkg, trans)

                    if current is not None:
                        currentlymsg = "at version %s" % (current.version)
                    else:
                        currentlymsg = "not present in testing"

                    rejectmsg += "Transition description: %s\n\n" % (t["reason"])

                    rejectmsg += "\n".join(textwrap.wrap("""Your package
is part of a testing transition designed to get %s migrated (it is
currently %s, we need version %s).  This transition is managed by the
Release Team, and %s is the Release-Team member responsible for it.
Please mail debian-release@lists.debian.org or contact %s directly if you
need further assistance.  You might want to upload to experimental until this
transition is done."""
                            % (source, currentlymsg, expected,t["rm"], t["rm"])))

                    self.rejects.append(rejectmsg)
                    return

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
                self.update_subst()
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

        if action and self.logger:
            self.logger.log(["closing bugs"] + bugs)

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

        if cnf.FindB("Dinstall::CloseBugs") and cnf.has_key("Dinstall::BugServer"):
            summary = self.close_bugs(summary, action)

        del self.Subst["__SHORT_SUMMARY__"]

        return summary

    ###########################################################################
    @session_wrapper
    def accept (self, summary, short_summary, session=None):
        """
        Accept an upload.

        This moves all files referenced from the .changes into the pool,
        sends the accepted mail, announces to lists, closes bugs and
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

        print "Installing."
        self.logger.log(["installing changes", self.pkg.changes_file])

        binaries = []
        poolfiles = []

        # Add the .dsc file to the DB first
        for newfile, entry in self.pkg.files.items():
            if entry["type"] == "dsc":
                source, dsc_component, dsc_location_id, pfs = add_dsc_to_db(self, newfile, session)
                for j in pfs:
                    poolfiles.append(j)

        # Add .deb / .udeb files to the DB (type is always deb, dbtype is udeb/deb)
        for newfile, entry in self.pkg.files.items():
            if entry["type"] == "deb":
                b, pf = add_deb_to_db(self, newfile, session)
                binaries.append(b)
                poolfiles.append(pf)

        # If this is a sourceful diff only upload that is moving
        # cross-component we need to copy the .orig files into the new
        # component too for the same reasons as above.
        # XXX: mhy: I think this should be in add_dsc_to_db
        if self.pkg.changes["architecture"].has_key("source"):
            for orig_file in self.pkg.orig_files.keys():
                if not self.pkg.orig_files[orig_file].has_key("id"):
                    continue # Skip if it's not in the pool
                orig_file_id = self.pkg.orig_files[orig_file]["id"]
                if self.pkg.orig_files[orig_file]["location"] == dsc_location_id:
                    continue # Skip if the location didn't change

                # Do the move
                oldf = get_poolfile_by_id(orig_file_id, session)
                old_filename = os.path.join(oldf.location.path, oldf.filename)
                old_dat = {'size': oldf.filesize,   'md5sum': oldf.md5sum,
                           'sha1sum': oldf.sha1sum, 'sha256sum': oldf.sha256sum}

                new_filename = os.path.join(utils.poolify(self.pkg.changes["source"], dsc_component), os.path.basename(old_filename))

                # TODO: Care about size/md5sum collisions etc
                (found, newf) = check_poolfile(new_filename, old_dat['size'], old_dat['md5sum'], dsc_location_id, session)

                # TODO: Uhm, what happens if newf isn't None - something has gone badly and we should cope
                if newf is None:
                    utils.copy(old_filename, os.path.join(cnf["Dir::Pool"], new_filename))
                    newf = add_poolfile(new_filename, old_dat, dsc_location_id, session)

                    session.flush()

                    # Don't reference the old file from this changes
                    for p in poolfiles:
                        if p.file_id == oldf.file_id:
                            poolfiles.remove(p)

                    poolfiles.append(newf)

                    # Fix up the DSC references
                    toremove = []

                    for df in source.srcfiles:
                        if df.poolfile.file_id == oldf.file_id:
                            # Add a new DSC entry and mark the old one for deletion
                            # Don't do it in the loop so we don't change the thing we're iterating over
                            newdscf = DSCFile()
                            newdscf.source_id = source.source_id
                            newdscf.poolfile_id = newf.file_id
                            session.add(newdscf)

                            toremove.append(df)

                    for df in toremove:
                        session.delete(df)

                    # Flush our changes
                    session.flush()

                    # Make sure that our source object is up-to-date
                    session.expire(source)

        # Add changelog information to the database
        self.store_changelog()

        # Install the files into the pool
        for newfile, entry in self.pkg.files.items():
            destination = os.path.join(cnf["Dir::Pool"], entry["pool name"], newfile)
            utils.move(newfile, destination)
            self.logger.log(["installed", newfile, entry["type"], entry["size"], entry["architecture"]])
            stats.accept_bytes += float(entry["size"])

        # Copy the .changes file across for suite which need it.
        copy_changes = dict([(x.copychanges, '')
                             for x in session.query(Suite).filter(Suite.suite_name.in_(self.pkg.changes["distribution"].keys())).all()
                             if x.copychanges is not None])

        for dest in copy_changes.keys():
            utils.copy(self.pkg.changes_file, os.path.join(cnf["Dir::Root"], dest))

        # We're done - commit the database changes
        session.commit()
        # Our SQL session will automatically start a new transaction after
        # the last commit

        # Now ensure that the metadata has been added
        # This has to be done after we copy the files into the pool
        # For source if we have it:
        if self.pkg.changes["architecture"].has_key("source"):
            import_metadata_into_db(source, session)

        # Now for any of our binaries
        for b in binaries:
            import_metadata_into_db(b, session)

        session.commit()

        # Move the .changes into the 'done' directory
        ye, mo, da = time.gmtime()[0:3]
        donedir = os.path.join(cnf["Dir::Done"], str(ye), "%0.2d" % mo, "%0.2d" % da)
        if not os.path.isdir(donedir):
            os.makedirs(donedir)

        utils.move(self.pkg.changes_file,
                   os.path.join(donedir, os.path.basename(self.pkg.changes_file)))

        if self.pkg.changes["architecture"].has_key("source"):
            UrgencyLog().log(self.pkg.dsc["source"], self.pkg.dsc["version"], self.pkg.changes["urgency"])

        self.update_subst()
        self.Subst["__SUMMARY__"] = summary
        mail_message = utils.TemplateSubst(self.Subst,
                                           os.path.join(cnf["Dir::Templates"], 'process-unchecked.accepted'))
        utils.send_mail(mail_message)
        self.announce(short_summary, 1)

        ## Helper stuff for DebBugs Version Tracking
        if cnf.Find("Dir::BTSVersionTrack"):
            if self.pkg.changes["architecture"].has_key("source"):
                (fd, temp_filename) = utils.temp_filename(cnf["Dir::BTSVersionTrack"], prefix=".")
                version_history = os.fdopen(fd, 'w')
                version_history.write(self.pkg.dsc["bts changelog"])
                version_history.close()
                filename = "%s/%s" % (cnf["Dir::BTSVersionTrack"],
                                      self.pkg.changes_file[:-8]+".versions")
                os.rename(temp_filename, filename)
                os.chmod(filename, 0o644)

            # Write out the binary -> source mapping.
            (fd, temp_filename) = utils.temp_filename(cnf["Dir::BTSVersionTrack"], prefix=".")
            debinfo = os.fdopen(fd, 'w')
            for name, entry in sorted(self.pkg.files.items()):
                if entry["type"] == "deb":
                    line = " ".join([entry["package"], entry["version"],
                                     entry["architecture"], entry["source package"],
                                     entry["source version"]])
                    debinfo.write(line+"\n")
            debinfo.close()
            filename = "%s/%s" % (cnf["Dir::BTSVersionTrack"],
                                  self.pkg.changes_file[:-8]+".debinfo")
            os.rename(temp_filename, filename)
            os.chmod(filename, 0o644)

        session.commit()

        # Set up our copy queues (e.g. buildd queues)
        for suite_name in self.pkg.changes["distribution"].keys():
            suite = get_suite(suite_name, session)
            for q in suite.copy_queues:
                for f in poolfiles:
                    q.add_file_from_pool(f)

        session.commit()

        # Finally...
        stats.accept_count += 1

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
        if not cnf.FindB("Dinstall::OverrideDisparityCheck"):
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

    ###########################################################################

    def remove(self, from_dir=None):
        """
        Used (for instance) in p-u to remove the package from unchecked

        Also removes the package from holding area.
        """
        if from_dir is None:
            from_dir = self.pkg.directory
        h = Holding()

        for f in self.pkg.files.keys():
            os.unlink(os.path.join(from_dir, f))
            if os.path.exists(os.path.join(h.holding_dir, f)):
                os.unlink(os.path.join(h.holding_dir, f))

        os.unlink(os.path.join(from_dir, self.pkg.changes_file))
        if os.path.exists(os.path.join(h.holding_dir, self.pkg.changes_file)):
            os.unlink(os.path.join(h.holding_dir, self.pkg.changes_file))

    ###########################################################################

    def move_to_queue (self, queue):
        """
        Move files to a destination queue using the permissions in the table
        """
        h = Holding()
        utils.move(os.path.join(h.holding_dir, self.pkg.changes_file),
                   queue.path, perms=int(queue.change_perms, 8))
        for f in self.pkg.files.keys():
            utils.move(os.path.join(h.holding_dir, f), queue.path, perms=int(queue.perms, 8))

    ###########################################################################

    def force_reject(self, reject_files):
        """
        Forcefully move files from the current directory to the
        reject directory.  If any file already exists in the reject
        directory it will be moved to the morgue to make way for
        the new file.

        @type reject_files: dict
        @param reject_files: file dictionary

        """

        cnf = Config()

        for file_entry in reject_files:
            # Skip any files which don't exist or which we don't have permission to copy.
            if os.access(file_entry, os.R_OK) == 0:
                continue

            dest_file = os.path.join(cnf["Dir::Reject"], file_entry)

            try:
                dest_fd = os.open(dest_file, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o644)
            except OSError as e:
                # File exists?  Let's find a new name by adding a number
                if e.errno == errno.EEXIST:
                    try:
                        dest_file = utils.find_next_free(dest_file, 255)
                    except NoFreeFilenameError:
                        # Something's either gone badly Pete Tong, or
                        # someone is trying to exploit us.
                        utils.warn("**WARNING** failed to find a free filename for %s in %s." % (file_entry, cnf["Dir::Reject"]))
                        return

                    # Make sure we really got it
                    try:
                        dest_fd = os.open(dest_file, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0o644)
                    except OSError as e:
                        # Likewise
                        utils.warn("**WARNING** failed to claim %s in the reject directory." % (file_entry))
                        return
                else:
                    raise
            # If we got here, we own the destination file, so we can
            # safely overwrite it.
            utils.move(file_entry, dest_file, 1, perms=0o660)
            os.close(dest_fd)

    ###########################################################################
    def do_reject (self, manual=0, reject_message="", notes=""):
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
            if len(notes) > 0:
                for note in notes:
                    temp_file.write("\nAuthor: %s\nVersion: %s\nTimestamp: %s\n\n%s" \
                                    % (note.author, note.version, note.notedate, note.comment))
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
        reason_filename = os.path.join(cnf["Dir::Reject"], reason_filename)
        changesfile = os.path.join(cnf["Dir::Reject"], self.pkg.changes_file)

        # Move all the files into the reject directory
        reject_files = self.pkg.files.keys() + [self.pkg.changes_file]
        self.force_reject(reject_files)

        # Change permissions of the .changes file to be world readable
        os.chmod(changesfile, os.stat(changesfile).st_mode | stat.S_IROTH)

        # If we fail here someone is probably trying to exploit the race
        # so let's just raise an exception ...
        if os.path.exists(reason_filename):
            os.unlink(reason_filename)
        reason_fd = os.open(reason_filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0o644)

        rej_template = os.path.join(cnf["Dir::Templates"], "queue.rejected")

        self.update_subst()
        if not manual:
            self.Subst["__REJECTOR_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]
            self.Subst["__MANUAL_REJECT_MESSAGE__"] = ""
            self.Subst["__CC__"] = "X-DAK-Rejection: automatic (moo)"
            os.write(reason_fd, reject_message)
            reject_mail_message = utils.TemplateSubst(self.Subst, rej_template)
        else:
            # Build up the rejection email
            user_email_address = utils.whoami() + " <%s>" % (cnf["Dinstall::MyAdminAddress"])
            self.Subst["__REJECTOR_ADDRESS__"] = user_email_address
            self.Subst["__MANUAL_REJECT_MESSAGE__"] = reject_message
            self.Subst["__REJECT_MESSAGE__"] = ""
            self.Subst["__CC__"] = "Cc: " + cnf["Dinstall::MyEmailAddress"]
            reject_mail_message = utils.TemplateSubst(self.Subst, rej_template)
            # Write the rejection email out as the <foo>.reason file
            os.write(reason_fd, reject_mail_message)

        del self.Subst["__REJECTOR_ADDRESS__"]
        del self.Subst["__MANUAL_REJECT_MESSAGE__"]
        del self.Subst["__CC__"]

        os.close(reason_fd)

        # Send the rejection mail
        utils.send_mail(reject_mail_message)

        if self.logger:
            self.logger.log(["rejected", self.pkg.changes_file])

        stats = SummaryStats()
        stats.reject_count += 1
        return 0

    ################################################################################
    def in_override_p(self, package, component, suite, binary_type, filename, session):
        """
        Check if a package already has override entries in the DB

        @type package: string
        @param package: package name

        @type component: string
        @param component: database id of the component

        @type suite: int
        @param suite: database id of the suite

        @type binary_type: string
        @param binary_type: type of the package

        @type filename: string
        @param filename: filename we check

        @return: the database result. But noone cares anyway.

        """

        cnf = Config()

        if binary_type == "": # must be source
            file_type = "dsc"
        else:
            file_type = binary_type

        # Override suite name; used for example with proposed-updates
        oldsuite = get_suite(suite, session)
        if (not oldsuite is None) and oldsuite.overridesuite:
            suite = oldsuite.overridesuite

        result = get_override(package, suite, component, file_type, session)

        # If checking for a source package fall back on the binary override type
        if file_type == "dsc" and len(result) < 1:
            result = get_override(package, suite, component, ['deb', 'udeb'], session)

        # Remember the section and priority so we can check them later if appropriate
        if len(result) > 0:
            result = result[0]
            self.pkg.files[filename]["override section"] = result.section.section
            self.pkg.files[filename]["override priority"] = result.priority.priority
            return result

        return None

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
                if not anyversion or apt_pkg.VersionCompare(anyversion, v) <= 0:
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
                vercmp = apt_pkg.VersionCompare(new_version, existent_version)

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
                        elif apt_pkg.VersionCompare(new_version, add_version) < 0:
                            # propogation would be redundant. no need to reject though.
                            self.warnings.append("ignoring versionconflict: %s: old version (%s) in %s <= new version (%s) targeted at %s." % (filename, existent_version, suite, new_version, target_suite))
                            cansave = 1
                        elif apt_pkg.VersionCompare(new_version, add_version) > 0 and \
                             apt_pkg.VersionCompare(add_version, target_version) >= 0:
                            # propogate!!
                            self.warnings.append("Propogating upload to %s" % (addsuite))
                            self.pkg.changes.setdefault("propdistribution", {})
                            self.pkg.changes["propdistribution"][addsuite] = 1
                            cansave = 1

                    if not cansave:
                        self.rejects.append("%s: old version (%s) in %s <= new version (%s) targeted at %s." % (filename, existent_version, suite, new_version, target_suite))

    ################################################################################
    def check_binary_against_db(self, filename, session):
        # Ensure version is sane
        self.cross_suite_version_check( \
            get_suite_version_by_package(self.pkg.files[filename]["package"], \
                self.pkg.files[filename]["architecture"], session),
            filename, self.pkg.files[filename]["version"], sourceful=False)

        # Check for any existing copies of the file
        q = session.query(DBBinary).filter_by(package=self.pkg.files[filename]["package"])
        q = q.filter_by(version=self.pkg.files[filename]["version"])
        q = q.join(Architecture).filter_by(arch_string=self.pkg.files[filename]["architecture"])

        if q.count() > 0:
            self.rejects.append("%s: can not overwrite existing copy already in the archive." % filename)

    ################################################################################

    def check_source_against_db(self, filename, session):
        source = self.pkg.dsc.get("source")
        version = self.pkg.dsc.get("version")

        # Ensure version is sane
        self.cross_suite_version_check( \
            get_suite_version_by_source(source, session), filename, version,
            sourceful=True)

    ################################################################################
    def check_dsc_against_db(self, filename, session):
        """

        @warning: NB: this function can remove entries from the 'files' index [if
         the orig tarball is a duplicate of the one in the archive]; if
         you're iterating over 'files' and call this function as part of
         the loop, be sure to add a check to the top of the loop to
         ensure you haven't just tried to dereference the deleted entry.

        """

        Cnf = Config()
        self.pkg.orig_files = {} # XXX: do we need to clear it?
        orig_files = self.pkg.orig_files

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
                ql = get_poolfile_like_name(dsc_name, session)

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
                    if re_is_orig_source.match(dsc_name):
                        for i in ql:
                            if self.pkg.files.has_key(dsc_name) and \
                               int(self.pkg.files[dsc_name]["size"]) == int(i.filesize) and \
                               self.pkg.files[dsc_name]["md5sum"] == i.md5sum:
                                self.warnings.append("ignoring %s, since it's already in the archive." % (dsc_name))
                                # TODO: Don't delete the entry, just mark it as not needed
                                # This would fix the stupidity of changing something we often iterate over
                                # whilst we're doing it
                                del self.pkg.files[dsc_name]
                                dsc_entry["files id"] = i.file_id
                                if not orig_files.has_key(dsc_name):
                                    orig_files[dsc_name] = {}
                                orig_files[dsc_name]["path"] = os.path.join(i.location.path, i.filename)
                                match = 1

                                # Don't bitch that we couldn't find this file later
                                try:
                                    self.later_check_files.remove(dsc_name)
                                except ValueError:
                                    pass


                    if not match:
                        self.rejects.append("can not overwrite existing copy of '%s' already in the archive." % (dsc_name))

            elif re_is_orig_source.match(dsc_name):
                # Check in the pool
                ql = get_poolfile_like_name(dsc_name, session)

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
                    suite_type = x.location.archive_type
                    # need this for updating dsc_files in install()
                    dsc_entry["files id"] = x.file_id
                    # See install() in process-accepted...
                    if not orig_files.has_key(dsc_name):
                        orig_files[dsc_name] = {}
                    orig_files[dsc_name]["id"] = x.file_id
                    orig_files[dsc_name]["path"] = old_file
                    orig_files[dsc_name]["location"] = x.location.location_id
                else:
                    # TODO: Determine queue list dynamically
                    # Not there? Check the queue directories...
                    for queue_name in [ "byhand", "new", "proposedupdates", "oldproposedupdates", "embargoed", "unembargoed" ]:
                        queue = get_policy_queue(queue_name, session)
                        if not queue:
                            continue

                        in_otherdir = os.path.join(queue.path, dsc_name)

                        if os.path.exists(in_otherdir):
                            in_otherdir_fh = utils.open_file(in_otherdir)
                            actual_md5 = apt_pkg.md5sum(in_otherdir_fh)
                            in_otherdir_fh.close()
                            actual_size = os.stat(in_otherdir)[stat.ST_SIZE]
                            found = in_otherdir
                            if not orig_files.has_key(dsc_name):
                                orig_files[dsc_name] = {}
                            orig_files[dsc_name]["path"] = in_otherdir

                    if not found:
                        self.rejects.append("%s refers to %s, but I can't find it in the queue or in the pool." % (filename, dsc_name))
                        continue
            else:
                self.rejects.append("%s refers to %s, but I can't find it in the queue." % (filename, dsc_name))
                continue
            if actual_md5 != dsc_entry["md5sum"]:
                self.rejects.append("md5sum for %s doesn't match %s." % (found, filename))
            if actual_size != int(dsc_entry["size"]):
                self.rejects.append("size for %s doesn't match %s." % (found, filename))

    ################################################################################
    # This is used by process-new and process-holding to recheck a changes file
    # at the time we're running.  It mainly wraps various other internal functions
    # and is similar to accepted_checks - these should probably be tidied up
    # and combined
    def recheck(self, session):
        cnf = Config()
        for f in self.pkg.files.keys():
            # The .orig.tar.gz can disappear out from under us is it's a
            # duplicate of one in the archive.
            if not self.pkg.files.has_key(f):
                continue

            entry = self.pkg.files[f]

            # Check that the source still exists
            if entry["type"] == "deb":
                source_version = entry["source version"]
                source_package = entry["source package"]
                if not self.pkg.changes["architecture"].has_key("source") \
                   and not source_exists(source_package, source_version, \
                    suites = self.pkg.changes["distribution"].keys(), session = session):
                    source_epochless_version = re_no_epoch.sub('', source_version)
                    dsc_filename = "%s_%s.dsc" % (source_package, source_epochless_version)
                    found = False
                    for queue_name in ["embargoed", "unembargoed", "newstage"]:
                        queue = get_policy_queue(queue_name, session)
                        if queue and os.path.exists(os.path.join(queue.path, dsc_filename)):
                            found = True
                    if not found:
                        self.rejects.append("no source found for %s %s (%s)." % (source_package, source_version, f))

            # Version and file overwrite checks
            if entry["type"] == "deb":
                self.check_binary_against_db(f, session)
            elif entry["type"] == "dsc":
                self.check_source_against_db(f, session)
                self.check_dsc_against_db(f, session)

    ################################################################################
    def accepted_checks(self, overwrite_checks, session):
        # Recheck anything that relies on the database; since that's not
        # frozen between accept and our run time when called from p-a.

        # overwrite_checks is set to False when installing to stable/oldstable

        propogate={}
        nopropogate={}

        # Find the .dsc (again)
        dsc_filename = None
        for f in self.pkg.files.keys():
            if self.pkg.files[f]["type"] == "dsc":
                dsc_filename = f

        for checkfile in self.pkg.files.keys():
            # The .orig.tar.gz can disappear out from under us is it's a
            # duplicate of one in the archive.
            if not self.pkg.files.has_key(checkfile):
                continue

            entry = self.pkg.files[checkfile]

            # Check that the source still exists
            if entry["type"] == "deb":
                source_version = entry["source version"]
                source_package = entry["source package"]
                if not self.pkg.changes["architecture"].has_key("source") \
                   and not source_exists(source_package, source_version, \
                    suites = self.pkg.changes["distribution"].keys(), \
                    session = session):
                    self.rejects.append("no source found for %s %s (%s)." % (source_package, source_version, checkfile))

            # Version and file overwrite checks
            if overwrite_checks:
                if entry["type"] == "deb":
                    self.check_binary_against_db(checkfile, session)
                elif entry["type"] == "dsc":
                    self.check_source_against_db(checkfile, session)
                    self.check_dsc_against_db(dsc_filename, session)

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

    ################################################################################
    # If any file of an upload has a recent mtime then chances are good
    # the file is still being uploaded.

    def upload_too_new(self):
        cnf = Config()
        too_new = False
        # Move back to the original directory to get accurate time stamps
        cwd = os.getcwd()
        os.chdir(self.pkg.directory)
        file_list = self.pkg.files.keys()
        file_list.extend(self.pkg.dsc_files.keys())
        file_list.append(self.pkg.changes_file)
        for f in file_list:
            try:
                last_modified = time.time()-os.path.getmtime(f)
                if last_modified < int(cnf["Dinstall::SkipTime"]):
                    too_new = True
                    break
            except:
                pass

        os.chdir(cwd)
        return too_new

    def store_changelog(self):

        # Skip binary-only upload if it is not a bin-NMU
        if not self.pkg.changes['architecture'].has_key('source'):
            from daklib.regexes import re_bin_only_nmu
            if not re_bin_only_nmu.search(self.pkg.changes['version']):
                return

        session = DBConn().session()

        # Check if upload already has a changelog entry
        query = """SELECT changelog_id FROM changes WHERE source = :source
                   AND version = :version AND architecture = :architecture AND changelog_id != 0"""
        if session.execute(query, {'source': self.pkg.changes['source'], \
                                   'version': self.pkg.changes['version'], \
                                   'architecture': " ".join(self.pkg.changes['architecture'].keys())}).rowcount:
            session.commit()
            return

        # Add current changelog text into changelogs_text table, return created ID
        query = "INSERT INTO changelogs_text (changelog) VALUES (:changelog) RETURNING id"
        ID = session.execute(query, {'changelog': self.pkg.changes['changes']}).fetchone()[0]

        # Link ID to the upload available in changes table
        query = """UPDATE changes SET changelog_id = :id WHERE source = :source
                   AND version = :version AND architecture = :architecture"""
        session.execute(query, {'id': ID, 'source': self.pkg.changes['source'], \
                                'version': self.pkg.changes['version'], \
                                'architecture': " ".join(self.pkg.changes['architecture'].keys())})

        session.commit()
