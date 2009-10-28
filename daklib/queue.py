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

import errno
import os
import pg
import stat
import sys
import time
import apt_inst
import apt_pkg
import utils
import commands
import shutil
import textwrap
import tempfile
from types import *

import yaml

from dak_exceptions import *
from changes import *
from regexes import *
from config import Config
from holding import Holding
from dbconn import *
from summarystats import SummaryStats
from utils import parse_changes, check_dsc_files
from textutils import fix_maintainer
from binary import Binary

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
    else:
        utils.fubar("invalid type (%s) for new.  Dazed, confused and sure as heck not continuing." % (file_type))

    # Validate the override type
    type_id = get_override_type(file_type, session)
    if type_id is None:
        utils.fubar("invalid type (%s) for new.  Say wha?" % (file_type))

    return file_type

################################################################################

# Determine what parts in a .changes are NEW

def determine_new(changes, files, warn=1):
    """
    Determine what parts in a C{changes} file are NEW.

    @type changes: Upload.Pkg.changes dict
    @param changes: Changes dictionary

    @type files: Upload.Pkg.files dict
    @param files: Files dictionary

    @type warn: bool
    @param warn: Warn if overrides are added for (old)stable

    @rtype: dict
    @return: dictionary of NEW components.

    """
    new = {}

    session = DBConn().session()

    # Build up a list of potentially new things
    for name, f in files.items():
        # Skip byhand elements
        if f["type"] == "byhand":
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

    session.close()

    return new

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
        section_name = new[pkg]["section"]
        priority_name = new[pkg]["priority"]
        file_type = new[pkg]["type"]

        section = get_section(section_name)
        if section is None:
            new[pkg]["section id"] = -1
        else:
            new[pkg]["section id"] = section.section_id

        priority = get_priority(priority_name)
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

def lookup_uid_from_fingerprint(fpr, session):
    uid = None
    uid_name = ""
    # This is a stupid default, but see the comments below
    is_dm = False

    user = get_uid_from_fingerprint(fpr, session)

    if user is not None:
        uid = user.uid
        if user.name is None:
            uid_name = ''
        else:
            uid_name = user.name

        # Check the relevant fingerprint (which we have to have)
        for f in user.fingerprint:
            if f.fingerprint == fpr:
                is_dm = f.keyring.debian_maintainer
                break

    return (uid, uid_name, is_dm)

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

    def callback(self, Kind, Name, Link, Mode, UID, GID, Size, MTime, Major, Minor):
        if MTime > self.future_cutoff:
            self.future_files[Name] = MTime
        if MTime < self.past_cutoff:
            self.ancient_files[Name] = MTime

###############################################################################

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
        self.Subst["__BUG_SERVER__"] = cnf["Dinstall::BugServer"]
        self.Subst["__DISTRO__"] = cnf["Dinstall::MyDistribution"]
        self.Subst["__DAK_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]

        self.rejects = []
        self.warnings = []
        self.notes = []

        self.pkg.reset()

    def package_info(self):
        msg = ''

        if len(self.rejects) > 0:
            msg += "Reject Reasons:\n"
            msg += "\n".join(self.rejects)

        if len(self.warnings) > 0:
            msg += "Warnings:\n"
            msg += "\n".join(self.warnings)

        if len(self.notes) > 0:
            msg += "Notes:\n"
            msg += "\n".join(self.notes)

        return msg

    ###########################################################################
    def update_subst(self):
        """ Set up the per-package template substitution mappings """

        cnf = Config()

        # If 'dak process-unchecked' crashed out in the right place, architecture may still be a string.
        if not self.pkg.changes.has_key("architecture") or not \
           isinstance(self.pkg.changes["architecture"], DictType):
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

        if "sponsoremail" in self.pkg.changes:
            self.Subst["__MAINTAINER_TO__"] += ", %s" % self.pkg.changes["sponsoremail"]

        if cnf.has_key("Dinstall::TrackingServer") and self.pkg.changes.has_key("source"):
            self.Subst["__MAINTAINER_TO__"] += "\nBcc: %s@%s" % (self.pkg.changes["source"], cnf["Dinstall::TrackingServer"])

        # Apply any global override of the Maintainer field
        if cnf.get("Dinstall::OverrideMaintainer"):
            self.Subst["__MAINTAINER_TO__"] = cnf["Dinstall::OverrideMaintainer"]
            self.Subst["__MAINTAINER_FROM__"] = cnf["Dinstall::OverrideMaintainer"]

        self.Subst["__REJECT_MESSAGE__"] = self.package_info()
        self.Subst["__SOURCE__"] = self.pkg.changes.get("source", "Unknown")
        self.Subst["__VERSION__"] = self.pkg.changes.get("version", "Unknown")

    ###########################################################################
    def load_changes(self, filename):
        """
        @rtype: boolean
        @rvalue: whether the changes file was valid or not.  We may want to
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
        except ParseChangesError, line:
            self.rejects.append("%s: parse error, can't grok: %s." % (filename, line))
            return False
        except ChangesUnicodeError:
            self.rejects.append("%s: changes file not proper utf-8" % (filename))
            return False

        # Parse the Files field from the .changes into another dictionary
        try:
            self.pkg.files.update(utils.build_file_list(self.pkg.changes))
        except ParseChangesError, line:
            self.rejects.append("%s: parse error, can't grok: %s." % (filename, line))
            return False
        except UnknownFormatError, format:
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
        except ParseMaintError, msg:
            self.rejects.append("%s: Maintainer field ('%s') failed to parse: %s" \
                   % (filename, changes["maintainer"], msg))

        # ...likewise for the Changed-By: field if it exists.
        try:
            (self.pkg.changes["changedby822"],
             self.pkg.changes["changedby2047"],
             self.pkg.changes["changedbyname"],
             self.pkg.changes["changedbyemail"]) = \
                   fix_maintainer (self.pkg.changes.get("changed-by", ""))
        except ParseMaintError, msg:
            self.pkg.changes["changedby822"] = ""
            self.pkg.changes["changedby2047"] = ""
            self.pkg.changes["changedbyname"] = ""
            self.pkg.changes["changedbyemail"] = ""

            self.rejects.append("%s: Changed-By field ('%s') failed to parse: %s" \
                   % (filename, changes["changed-by"], msg))

        # Ensure all the values in Closes: are numbers
        if self.pkg.changes.has_key("closes"):
            for i in self.pkg.changes["closes"].keys():
                if re_isanum.match (i) == None:
                    self.rejects.append(("%s: `%s' from Closes field isn't a number." % (filename, i)))

        # chopversion = no epoch; chopversion2 = no epoch and no revision (e.g. for .orig.tar.gz comparison)
        self.pkg.changes["chopversion"] = re_no_epoch.sub('', self.pkg.changes["version"])
        self.pkg.changes["chopversion2"] = re_no_revision.sub('', self.pkg.changes["chopversion"])

        # Check there isn't already a changes file of the same name in one
        # of the queue directories.
        base_filename = os.path.basename(filename)
        for d in [ "Accepted", "Byhand", "Done", "New", "ProposedUpdates", "OldProposedUpdates" ]:
            if os.path.exists(os.path.join(Cnf["Dir::Queue::%s" % (d) ], base_filename)):
                self.rejects.append("%s: a file with this name already exists in the %s directory." % (base_filename, d))

        # Check the .changes is non-empty
        if not self.pkg.files:
            self.rejects.append("%s: nothing to do (Files field is empty)." % (base_filename))
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
            if not Cnf.has_key("Suite::%s" % (suite)):
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
            self.rejects.append("%s: debExtractControl() raised %s." % (f, sys.exc_type))
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
        default_suite = cnf.get("Dinstall::DefaultSuite", "Unstable")
        architecture = control.Find("Architecture")
        upload_suite = self.pkg.changes["distribution"].keys()[0]

        if      architecture not in [a.arch_string for a in get_suite_architectures(default_suite, session)] \
            and architecture not in [a.arch_string for a in get_suite_architectures(upload_suite, session)]:
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
            if not source_exists(source_package, source_version, self.pkg.changes["distribution"].keys(), session):
                # Check in one of the other directories
                source_epochless_version = re_no_epoch.sub('', source_version)
                dsc_filename = "%s_%s.dsc" % (source_package, source_epochless_version)
                if os.path.exists(os.path.join(cnf["Dir::Queue::Byhand"], dsc_filename)):
                    entry["byhand"] = 1
                elif os.path.exists(os.path.join(cnf["Dir::Queue::New"], dsc_filename)):
                    entry["new"] = 1
                else:
                    dsc_file_exists = False
                    for myq in ["Accepted", "Embargoed", "Unembargoed", "ProposedUpdates", "OldProposedUpdates"]:
                        if cnf.has_key("Dir::Queue::%s" % (myq)):
                            if os.path.exists(os.path.join(cnf["Dir::Queue::" + myq], dsc_filename)):
                                dsc_file_exists = True
                                break

                    if not dsc_file_exists:
                        self.rejects.append("no source found for %s %s (%s)." % (source_package, source_version, f))

        # Check the version and for file overwrites
        self.check_binary_against_db(f, session)

        # Temporarily disable contents generation until we change the table storage layout
        #b = Binary(f)
        #b.scan_package()
        #if len(b.rejects) > 0:
        #    for j in b.rejects:
        #        self.rejects.append(j)

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
        archive = utils.where_am_i()

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
        if cnf.has_key("Suite:%s::Components" % (suite)) and \
           entry["component"] not in cnf.ValueList("Suite::%s::Components" % (suite)):
            self.rejects.append("unknown component `%s' for suite `%s'." % (entry["component"], suite))
            return

        # Validate the component
        if not get_component(entry["component"], session):
            self.rejects.append("file '%s' has unknown component '%s'." % (f, component))
            return

        # See if the package is NEW
        if not self.in_override_p(entry["package"], entry["component"], suite, entry.get("dbtype",""), f, session):
            entry["new"] = 1

        # Validate the priority
        if entry["priority"].find('/') != -1:
            self.rejects.append("file '%s' has invalid priority '%s' [contains '/']." % (f, entry["priority"]))

        # Determine the location
        location = cnf["Dir::Pool"]
        l = get_location(location, entry["component"], archive, session)
        if l is None:
            self.rejects.append("[INTERNAL ERROR] couldn't determine location (Component: %s, Archive: %s)" % (component, archive))
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
        res = get_binary_components(self.pkg.files[f]['package'], suite, entry["architecture"], session)
        if res.rowcount > 0:
            entry["othercomponents"] = res.fetchone()[0]

    def check_files(self, action=True):
        archive = utils.where_am_i()
        file_keys = self.pkg.files.keys()
        holding = Holding()
        cnf = Config()

        # XXX: As far as I can tell, this can no longer happen - see
        #      comments by AJ in old revisions - mhy
        # if reprocess is 2 we've already done this and we're checking
        # things again for the new .orig.tar.gz.
        # [Yes, I'm fully aware of how disgusting this is]
        if action and self.reprocess < 2:
            cwd = os.getcwd()
            os.chdir(self.pkg.directory)
            for f in file_keys:
                ret = holding.copy_to_holding(f)
                if ret is not None:
                    # XXX: Should we bail out here or try and continue?
                    self.rejects.append(ret)

            os.chdir(cwd)

        # Check there isn't already a .changes or .dak file of the same name in
        # the proposed-updates "CopyChanges" or "CopyDotDak" storage directories.
        # [NB: this check must be done post-suite mapping]
        base_filename = os.path.basename(self.pkg.changes_file)
        dot_dak_filename = base_filename[:-8] + ".dak"

        for suite in self.pkg.changes["distribution"].keys():
            copychanges = "Suite::%s::CopyChanges" % (suite)
            if cnf.has_key(copychanges) and \
                   os.path.exists(os.path.join(cnf[copychanges], base_filename)):
                self.rejects.append("%s: a file with this name already exists in %s" \
                           % (base_filename, cnf[copychanges]))

            copy_dot_dak = "Suite::%s::CopyDotDak" % (suite)
            if cnf.has_key(copy_dot_dak) and \
                   os.path.exists(os.path.join(cnf[copy_dot_dak], dot_dak_filename)):
                self.rejects.append("%s: a file with this name already exists in %s" \
                           % (dot_dak_filename, Cnf[copy_dot_dak]))

        self.reprocess = 0
        has_binaries = False
        has_source = False

        session = DBConn().session()

        for f, entry in self.pkg.files.items():
            # Ensure the file does not already exist in one of the accepted directories
            for d in [ "Accepted", "Byhand", "New", "ProposedUpdates", "OldProposedUpdates", "Embargoed", "Unembargoed" ]:
                if not cnf.has_key("Dir::Queue::%s" % (d)): continue
                if os.path.exists(cnf["Dir::Queue::%s" % (d) ] + '/' + f):
                    self.rejects.append("%s file already exists in the %s directory." % (f, d))

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
                        self.rejects.append("Can't read `%s'. [file not found]" % (f))
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

            if not has_binaries and cnf.FindB("Dinstall::Reject::NoSourceOnly"):
                self.rejects.append("source only uploads are not supported.")

    ###########################################################################
    def check_dsc(self, action=True, session=None):
        """Returns bool indicating whether or not the source changes are valid"""
        # Ensure there is source to check
        if not self.pkg.changes["architecture"].has_key("source"):
            return True

        # Find the .dsc
        dsc_filename = None
        for f, entry in self.pkg.files.items():
            if entry["type"] == "dsc":
                if dsc_filename:
                    self.rejects.append("can not process a .changes file with multiple .dsc's.")
                    return False
                else:
                    dsc_filename = f

        # If there isn't one, we have nothing to do. (We have reject()ed the upload already)
        if not dsc_filename:
            self.rejects.append("source uploads must contain a dsc file")
            return False

        # Parse the .dsc file
        try:
            self.pkg.dsc.update(utils.parse_changes(dsc_filename, signing_rules=1))
        except CantOpenError:
            # if not -n copy_to_holding() will have done this for us...
            if not action:
                self.rejects.append("%s: can't read file." % (dsc_filename))
        except ParseChangesError, line:
            self.rejects.append("%s: parse error, can't grok: %s." % (dsc_filename, line))
        except InvalidDscError, line:
            self.rejects.append("%s: syntax error on line %s." % (dsc_filename, line))
        except ChangesUnicodeError:
            self.rejects.append("%s: dsc file not proper utf-8." % (dsc_filename))

        # Build up the file list of files mentioned by the .dsc
        try:
            self.pkg.dsc_files.update(utils.build_file_list(self.pkg.dsc, is_a_dsc=1))
        except NoFilesFieldError:
            self.rejects.append("%s: no Files: field." % (dsc_filename))
            return False
        except UnknownFormatError, format:
            self.rejects.append("%s: unknown format '%s'." % (dsc_filename, format))
            return False
        except ParseChangesError, line:
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
            allowed = [ x.format_name for x in get_suite_src_formats(dist, session) ]
            if self.pkg.dsc["format"] not in allowed:
                self.rejects.append("%s: source format '%s' not allowed in %s (accepted: %s) " % (dsc_filename, self.pkg.dsc["format"], dist, ", ".join(allowed)))

        # Validate the Maintainer field
        try:
            # We ignore the return value
            fix_maintainer(self.pkg.dsc["maintainer"])
        except ParseMaintError, msg:
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
        session.close()

        return True

    ###########################################################################

    def ensure_all_source_exists(self, source_dir, dest_dir=None):
        """
        Ensure that dest_dir contains all the orig tarballs for the specified
        changes. If it does not, symlink them into place.

        If dest_dir is None, populate the current directory.
        """

        if dest_dir is None:
            dest_dir = os.getcwd()

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

        self.ensure_all_source_exists(source_dir)

        # Extract the source
        cmd = "dpkg-source -sn -x %s" % (dsc_filename)
        (result, output) = commands.getstatusoutput(cmd)
        if (result != 0):
            self.rejects.append("'dpkg-source -x' failed for %s [return code: %s]." % (dsc_filename, result))
            self.rejects.append(utils.prefix_multi_line_string(output, " [dpkg-source output:] "))
            return

        if not cnf.Find("Dir::Queue::BTSVersionTrack"):
            return

        # Get the upstream version
        upstr_version = re_no_epoch.sub('', self.pkg.dsc["version"])
        if re_strip_revision.search(upstr_version):
            upstr_version = re_strip_revision.sub('', upstr_version)

        # Ensure the changelog file exists
        changelog_filename = "%s-%s/debian/changelog" % (self.pkg.dsc["source"], upstr_version)
        if not os.path.exists(changelog_filename):
            self.rejects.append("%s: debian/changelog not found in extracted source." % (dsc_filename))
            return

        # Parse the changelog
        self.pkg.dsc["bts changelog"] = ""
        changelog_file = utils.open_file(changelog_filename)
        for line in changelog_file.readlines():
            m = re_changelog_versions.match(line)
            if m:
                self.pkg.dsc["bts changelog"] += line
        changelog_file.close()

        # Check we found at least one revision in the changelog
        if not self.pkg.dsc["bts changelog"]:
            self.rejects.append("%s: changelog format not recognised (empty version tree)." % (dsc_filename))

    def check_source(self):
        # XXX: I'm fairly sure reprocess == 2 can never happen
        #      AJT disabled the is_incoming check years ago - mhy
        #      We should probably scrap or rethink the whole reprocess thing
        # Bail out if:
        #    a) there's no source
        # or b) reprocess is 2 - we will do this check next time when orig
        #       tarball is in 'files'
        # or c) the orig files are MIA
        if not self.pkg.changes["architecture"].has_key("source") or self.reprocess == 2 \
           or len(self.pkg.orig_files) == 0:
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
        except OSError, e:
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
        except Exception, e:
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
    def check_lintian(self):
        # Only check some distributions
        valid_dist = False
        for dist in ('unstable', 'experimental'):
            if dist in self.pkg.changes['distribution']:
                valid_dist = True
                break

        if not valid_dist:
            return

        self.ensure_all_source_exists()

        cnf = Config()
        tagfile = cnf.get("Dinstall::LintianTags")
        if tagfile is None:
            # We don't have a tagfile, so just don't do anything.
            return
        # Parse the yaml file
        sourcefile = file(tagfile, 'r')
        sourcecontent = sourcefile.read()
        sourcefile.close()
        try:
            lintiantags = yaml.load(sourcecontent)['lintian']
        except yaml.YAMLError, msg:
            utils.fubar("Can not read the lintian tags file %s, YAML error: %s." % (tagfile, msg))
            return

        # Now setup the input file for lintian. lintian wants "one tag per line" only,
        # so put it together like it. We put all types of tags in one file and then sort
        # through lintians output later to see if its a fatal tag we detected, or not.
        # So we only run lintian once on all tags, even if we might reject on some, but not
        # reject on others.
        # Additionally build up a set of tags
        tags = set()
        (fd, temp_filename) = utils.temp_filename()
        temptagfile = os.fdopen(fd, 'w')
        for tagtype in lintiantags:
            for tag in lintiantags[tagtype]:
                temptagfile.write("%s\n" % tag)
                tags.add(tag)
        temptagfile.close()

        # So now we should look at running lintian at the .changes file, capturing output
        # to then parse it.
        command = "lintian --show-overrides --tags-from-file %s %s" % (temp_filename, self.pkg.changes_file)
        (result, output) = commands.getstatusoutput(command)
        # We are done with lintian, remove our tempfile
        os.unlink(temp_filename)
        if (result == 2):
            utils.warn("lintian failed for %s [return code: %s]." % (self.pkg.changes_file, result))
            utils.warn(utils.prefix_multi_line_string(output, " [possible output:] "))

        if len(output) == 0:
            return

        def log(*txt):
            if self.logger:
                args = [self.pkg.changes_file, "check_lintian"]
                args.extend(txt)
                self.logger.log(args)

        # We have output of lintian, this package isn't clean. Lets parse it and see if we
        # are having a victim for a reject.
        # W: tzdata: binary-without-manpage usr/sbin/tzconfig
        for line in output.split('\n'):
            m = re_parse_lintian.match(line)
            if m is None:
                continue

            etype = m.group(1)
            epackage = m.group(2)
            etag = m.group(3)
            etext = m.group(4)

            # So lets check if we know the tag at all.
            if etag not in tags:
                continue

            if etype == 'O':
                # We know it and it is overriden. Check that override is allowed.
                if etag in lintiantags['warning']:
                    # The tag is overriden, and it is allowed to be overriden.
                    # Don't add a reject message.
                    pass
                elif etag in lintiantags['error']:
                    # The tag is overriden - but is not allowed to be
                    self.rejects.append("%s: Overriden tag %s found, but this tag may not be overwritten." % (epackage, etag))
                    log("overidden tag is overridden", etag)
            else:
                # Tag is known, it is not overriden, direct reject.
                self.rejects.append("%s: Found lintian output: '%s %s', automatically rejected package." % (epackage, etag, etext))
                log("auto rejecting", etag)
                # Now tell if they *might* override it.
                if etag in lintiantags['warning']:
                    self.rejects.append("%s: If you have a good reason, you may override this lintian tag." % (epackage))

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
                    deb_file = utils.open_file(filename)
                    apt_inst.debExtract(deb_file, tar.callback, "control.tar.gz")
                    deb_file.seek(0)
                    try:
                        apt_inst.debExtract(deb_file, tar.callback, "data.tar.gz")
                    except SystemError, e:
                        # If we can't find a data.tar.gz, look for data.tar.bz2 instead.
                        if not re.search(r"Cannot f[ui]nd chunk data.tar.gz$", str(e)):
                            raise
                        deb_file.seek(0)
                        apt_inst.debExtract(deb_file,tar.callback,"data.tar.bz2")

                    deb_file.close()

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
                    self.rejects.append("%s: deb contents timestamp check failed [%s: %s]" % (filename, sys.exc_type, sys.exc_value))

    ###########################################################################
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
        transpath = cnf.get("Dinstall::Reject::ReleaseTransitions", "")
        if transpath == "" or not os.path.exists(transpath):
            return

        # Parse the yaml file
        sourcefile = file(transpath, 'r')
        sourcecontent = sourcefile.read()
        try:
            transitions = yaml.load(sourcecontent)
        except yaml.YAMLError, msg:
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
    def check_signed_by_key(self):
        """Ensure the .changes is signed by an authorized uploader."""
        session = DBConn().session()

        self.check_transition(session)

        (uid, uid_name, is_dm) = lookup_uid_from_fingerprint(self.pkg.changes["fingerprint"], session=session)

        # match claimed name with actual name:
        if uid is None:
            # This is fundamentally broken but need us to refactor how we get
            # the UIDs/Fingerprints in order for us to fix it properly
            uid, uid_email = self.pkg.changes["fingerprint"], uid
            may_nmu, may_sponsor = 1, 1
            # XXX by default new dds don't have a fingerprint/uid in the db atm,
            #     and can't get one in there if we don't allow nmu/sponsorship
        elif is_dm is False:
            # If is_dm is False, we allow full upload rights
            uid_email = "%s@debian.org" % (uid)
            may_nmu, may_sponsor = 1, 1
        else:
            # Assume limited upload rights unless we've discovered otherwise
            uid_email = uid
            may_nmu, may_sponsor = 0, 0

        if uid_email in [self.pkg.changes["maintaineremail"], self.pkg.changes["changedbyemail"]]:
            sponsored = 0
        elif uid_name in [self.pkg.changes["maintainername"], self.pkg.changes["changedbyname"]]:
            sponsored = 0
            if uid_name == "": sponsored = 1
        else:
            sponsored = 1
            if ("source" in self.pkg.changes["architecture"] and
                uid_email and utils.is_email_alias(uid_email)):
                sponsor_addresses = utils.gpg_get_key_addresses(self.pkg.changes["fingerprint"])
                if (self.pkg.changes["maintaineremail"] not in sponsor_addresses and
                    self.pkg.changes["changedbyemail"] not in sponsor_addresses):
                    self.pkg.changes["sponsoremail"] = uid_email

        if sponsored and not may_sponsor:
            self.rejects.append("%s is not authorised to sponsor uploads" % (uid))

        if not sponsored and not may_nmu:
            should_reject = True
            highest_sid, highest_version = None, None

            # XXX: This reimplements in SQLA what existed before but it's fundamentally fucked
            #      It ignores higher versions with the dm_upload_allowed flag set to false
            #      I'm keeping the existing behaviour for now until I've gone back and
            #      checked exactly what the GR says - mhy
            for si in get_sources_from_name(source=self.pkg.changes['source'], dm_upload_allowed=True, session=session):
                if highest_version is None or apt_pkg.VersionCompare(si.version, highest_version) == 1:
                     highest_sid = si.source_id
                     highest_version = si.version

            if highest_sid is None:
                self.rejects.append("Source package %s does not have 'DM-Upload-Allowed: yes' in its most recent version" % self.pkg.changes["source"])
            else:
                for sup in session.query(SrcUploader).join(DBSource).filter_by(source_id=highest_sid):
                    (rfc822, rfc2047, name, email) = sup.maintainer.get_split_maintainer()
                    if email == uid_email or name == uid_name:
                        should_reject = False
                        break

            if should_reject is True:
                self.rejects.append("%s is not in Maintainer or Uploaders of source package %s" % (uid, self.pkg.changes["source"]))

            for b in self.pkg.changes["binary"].keys():
                for suite in self.pkg.changes["distribution"].keys():
                    q = session.query(DBSource)
                    q = q.join(DBBinary).filter_by(package=b)
                    q = q.join(BinAssociation).join(Suite).filter_by(suite_name=suite)

                    for s in q.all():
                        if s.source != self.pkg.changes["source"]:
                            self.rejects.append("%s may not hijack %s from source package %s in suite %s" % (uid, b, s, suite))

            for f in self.pkg.files.keys():
                if self.pkg.files[f].has_key("byhand"):
                    self.rejects.append("%s may not upload BYHAND file %s" % (uid, f))
                if self.pkg.files[f].has_key("new"):
                    self.rejects.append("%s may not upload NEW file %s" % (uid, f))

        session.close()

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
        announcetemplate = os.path.join(cnf["Dir::Templates"], 'process-unchecked.announce')

        # Only do announcements for source uploads with a recent dpkg-dev installed
        if float(self.pkg.changes.get("format", 0)) < 1.6 or not \
           self.pkg.changes["architecture"].has_key("source"):
            return ""

        lists_done = {}
        summary = ""

        self.Subst["__SHORT_SUMMARY__"] = short_summary

        for dist in self.pkg.changes["distribution"].keys():
            announce_list = cnf.Find("Suite::%s::Announce" % (dist))
            if announce_list == "" or lists_done.has_key(announce_list):
                continue

            lists_done[announce_list] = 1
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
        if self.logger:
            self.logger.log(["Accepting changes", self.pkg.changes_file])

        self.pkg.write_dot_dak(targetdir)

        # Move all the files into the accepted directory
        utils.move(self.pkg.changes_file, targetdir)

        for name, entry in sorted(self.pkg.files.items()):
            utils.move(name, targetdir)
            stats.accept_bytes += float(entry["size"])

        stats.accept_count += 1

        # Send accept mail, announce to lists, close bugs and check for
        # override disparities
        if not cnf["Dinstall::Options::No-Mail"]:
            self.update_subst()
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
        res = get_or_set_queue('accepted').autobuild_upload(self.pkg, cnf["Dir::Queue::Accepted"])
        if res:
            utils.fubar(res)


    def check_override(self):
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

        self.update_subst()
        self.Subst["__SUMMARY__"] = summary
        mail_message = utils.TemplateSubst(self.Subst, overridetemplate)
        utils.send_mail(mail_message)
        del self.Subst["__SUMMARY__"]

    ###########################################################################

    def remove(self, dir=None):
        """
        Used (for instance) in p-u to remove the package from unchecked
        """
        if dir is None:
            os.chdir(self.pkg.directory)
        else:
            os.chdir(dir)

        for f in self.pkg.files.keys():
            os.unlink(f)
        os.unlink(self.pkg.changes_file)

    ###########################################################################

    def move_to_dir (self, dest, perms=0660, changesperms=0664):
        """
        Move files to dest with certain perms/changesperms
        """
        utils.move(self.pkg.changes_file, dest, perms=changesperms)
        for f in self.pkg.files.keys():
            utils.move(f, dest, perms=perms)

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
            self.Subst["__CC__"] = "Cc: " + cnf["Dinstall::MyEmailAddress"]
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

        if self.logger:
            self.logger.log(["rejected", self.pkg.changes_file])

        return 0

    ################################################################################
    def in_override_p(self, package, component, suite, binary_type, file, session):
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

        @type file: string
        @param file: filename we check

        @return: the database result. But noone cares anyway.

        """

        cnf = Config()

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
        anysuite = [suite] + Cnf.ValueList("Suite::%s::VersionChecks::Enhances" % (suite))
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
                    self.rejects.append("%s: old version (%s) in %s >= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite))

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
                            self.warnings.append("ignoring versionconflict: %s: old version (%s) in %s <= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite))
                            cansave = 1
                        elif apt_pkg.VersionCompare(new_version, add_version) > 0 and \
                             apt_pkg.VersionCompare(add_version, target_version) >= 0:
                            # propogate!!
                            self.warnings.append("Propogating upload to %s" % (addsuite))
                            self.pkg.changes.setdefault("propdistribution", {})
                            self.pkg.changes["propdistribution"][addsuite] = 1
                            cansave = 1

                    if not cansave:
                        self.reject.append("%s: old version (%s) in %s <= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite))

    ################################################################################
    def check_binary_against_db(self, file, session):
        # Ensure version is sane
        q = session.query(BinAssociation)
        q = q.join(DBBinary).filter(DBBinary.package==self.pkg.files[file]["package"])
        q = q.join(Architecture).filter(Architecture.arch_string.in_([self.pkg.files[file]["architecture"], 'all']))

        self.cross_suite_version_check([ (x.suite.suite_name, x.binary.version) for x in q.all() ],
                                       file, self.pkg.files[file]["version"], sourceful=False)

        # Check for any existing copies of the file
        q = session.query(DBBinary).filter_by(package=self.pkg.files[file]["package"])
        q = q.filter_by(version=self.pkg.files[file]["version"])
        q = q.join(Architecture).filter_by(arch_string=self.pkg.files[file]["architecture"])

        if q.count() > 0:
            self.rejects.append("%s: can not overwrite existing copy already in the archive." % (file))

    ################################################################################

    def check_source_against_db(self, file, session):
        """
        """
        source = self.pkg.dsc.get("source")
        version = self.pkg.dsc.get("version")

        # Ensure version is sane
        q = session.query(SrcAssociation)
        q = q.join(DBSource).filter(DBSource.source==source)

        self.cross_suite_version_check([ (x.suite.suite_name, x.source.version) for x in q.all() ],
                                       file, version, sourceful=True)

    ################################################################################
    def check_dsc_against_db(self, file, session):
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
                                if not orig_files.has_key(dsc_name):
                                    orig_files[dsc_name] = {}
                                orig_files[dsc_name]["path"] = os.path.join(i.location.path, i.filename)
                                match = 1

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
                    # TODO: Record the queues and info in the DB so we don't hardcode all this crap
                    # Not there? Check the queue directories...
                    for directory in [ "Accepted", "New", "Byhand", "ProposedUpdates", "OldProposedUpdates", "Embargoed", "Unembargoed" ]:
                        if not Cnf.has_key("Dir::Queue::%s" % (directory)):
                            continue
                        in_otherdir = os.path.join(Cnf["Dir::Queue::%s" % (directory)], dsc_name)
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
                        self.rejects.append("%s refers to %s, but I can't find it in the queue or in the pool." % (file, dsc_name))
                        continue
            else:
                self.rejects.append("%s refers to %s, but I can't find it in the queue." % (file, dsc_name))
                continue
            if actual_md5 != dsc_entry["md5sum"]:
                self.rejects.append("md5sum for %s doesn't match %s." % (found, file))
            if actual_size != int(dsc_entry["size"]):
                self.rejects.append("size for %s doesn't match %s." % (found, file))

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
                   and not source_exists(source_package, source_version,  self.pkg.changes["distribution"].keys()):
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
    # This is not really a reject, but an unaccept, but since a) the code for
    # that is non-trivial (reopen bugs, unannounce etc.), b) this should be
    # extremely rare, for now we'll go with whining at our admin folks...

    def do_unaccept(self):
        cnf = Config()

        self.update_subst()
        self.Subst["__REJECTOR_ADDRESS__"] = cnf["Dinstall::MyEmailAddress"]
        self.Subst["__REJECT_MESSAGE__"] = self.package_info()
        self.Subst["__CC__"] = "Cc: " + cnf["Dinstall::MyEmailAddress"]
        self.Subst["__BCC__"] = "X-DAK: dak process-accepted"
        if cnf.has_key("Dinstall::Bcc"):
            self.Subst["__BCC__"] += "\nBcc: %s" % (cnf["Dinstall::Bcc"])

        template = os.path.join(cnf["Dir::Templates"], "process-accepted.unaccept")

        reject_mail_message = utils.TemplateSubst(self.Subst, template)

        # Write the rejection email out as the <foo>.reason file
        reason_filename = os.path.basename(self.pkg.changes_file[:-8]) + ".reason"
        reject_filename = os.path.join(cnf["Dir::Queue::Reject"], reason_filename)

        # If we fail here someone is probably trying to exploit the race
        # so let's just raise an exception ...
        if os.path.exists(reject_filename):
            os.unlink(reject_filename)

        fd = os.open(reject_filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0644)
        os.write(fd, reject_mail_message)
        os.close(fd)

        utils.send_mail(reject_mail_message)

        del self.Subst["__REJECTOR_ADDRESS__"]
        del self.Subst["__REJECT_MESSAGE__"]
        del self.Subst["__CC__"]

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
