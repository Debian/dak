#!/usr/bin/env python
# vim:set et sw=4:

"""
Changes class for dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001 - 2006 James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
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
import stat

import datetime
from cPickle import Unpickler, Pickler
from errno import EPERM

from apt_pkg import TagSection

from utils import open_file, fubar, poolify, deb_extract_control
from config import *
from dbconn import *

###############################################################################

__all__ = []

###############################################################################

CHANGESFIELDS_MANDATORY = [ "distribution", "source", "architecture",
        "version", "maintainer", "urgency", "fingerprint", "changedby822",
        "changedby2047", "changedbyname", "maintainer822", "maintainer2047",
        "maintainername", "maintaineremail", "closes", "changes" ]

__all__.append('CHANGESFIELDS_MANDATORY')

CHANGESFIELDS_OPTIONAL = [ "changed-by", "filecontents", "format",
        "process-new note", "adv id", "distribution-version", "sponsoremail" ]

__all__.append('CHANGESFIELDS_OPTIONAL')

CHANGESFIELDS_FILES = [ "package", "version", "architecture", "type", "size",
        "md5sum", "sha1sum", "sha256sum", "component", "location id",
        "source package", "source version", "maintainer", "dbtype", "files id",
        "new", "section", "priority", "othercomponents", "pool name",
        "original component" ]

__all__.append('CHANGESFIELDS_FILES')

CHANGESFIELDS_DSC = [ "source", "version", "maintainer", "fingerprint",
        "uploaders", "bts changelog", "dm-upload-allowed" ]

__all__.append('CHANGESFIELDS_DSC')

CHANGESFIELDS_DSCFILES_MANDATORY = [ "size", "md5sum" ]

__all__.append('CHANGESFIELDS_DSCFILES_MANDATORY')

CHANGESFIELDS_DSCFILES_OPTIONAL = [ "files id" ]

__all__.append('CHANGESFIELDS_DSCFILES_OPTIONAL')

CHANGESFIELDS_ORIGFILES = [ "id", "location" ]

__all__.append('CHANGESFIELDS_ORIGFILES')

###############################################################################

class Changes(object):
    """ Convenience wrapper to carry around all the package information """

    def __init__(self, **kwds):
        self.reset()

    def reset(self):
        self.changes_file = ""

        self.changes = {}
        self.dsc = {}
        self.files = {}
        self.dsc_files = {}
        self.orig_files = {}

    def file_summary(self):
        # changes["distribution"] may not exist in corner cases
        # (e.g. unreadable changes files)
        if not self.changes.has_key("distribution") or not \
               isinstance(self.changes["distribution"], dict):
            self.changes["distribution"] = {}

        byhand = False
        new = False
        summary = ""
        override_summary = ""

        for name, entry in sorted(self.files.items()):
            if entry.has_key("byhand"):
                byhand = True
                summary += name + " byhand\n"

            elif entry.has_key("new"):
                new = True
                summary += "(new) %s %s %s\n" % (name, entry["priority"], entry["section"])

                if entry.has_key("othercomponents"):
                    summary += "WARNING: Already present in %s distribution.\n" % (entry["othercomponents"])

                if entry["type"] == "deb":
                    deb_fh = open_file(name)
                    summary += TagSection(deb_extract_control(deb_fh))["Description"] + '\n'
                    deb_fh.close()

            else:
                entry["pool name"] = poolify(self.changes.get("source", ""), entry["component"])
                destination = entry["pool name"] + name
                summary += name + "\n  to " + destination + "\n"

                if not entry.has_key("type"):
                    entry["type"] = "unknown"

                if entry["type"] in ["deb", "udeb", "dsc"]:
                    # (queue/unchecked), there we have override entries already, use them
                    # (process-new), there we dont have override entries, use the newly generated ones.
                    override_prio = entry.get("override priority", entry["priority"])
                    override_sect = entry.get("override section", entry["section"])
                    override_summary += "%s - %s %s\n" % (name, override_prio, override_sect)

        return (byhand, new, summary, override_summary)

    def check_override(self):
        """
        Checks override entries for validity.

        Returns an empty string if there are no problems
        or the text of a warning if there are
        """

        summary = ""

        # Abandon the check if it's a non-sourceful upload
        if not self.changes["architecture"].has_key("source"):
            return summary

        for name, entry in sorted(self.files.items()):
            if not entry.has_key("new") and entry["type"] == "deb":
                if entry["section"] != "-":
                    if entry["section"].lower() != entry["override section"].lower():
                        summary += "%s: package says section is %s, override says %s.\n" % (name,
                                                                                            entry["section"],
                                                                                            entry["override section"])

                if entry["priority"] != "-":
                    if entry["priority"] != entry["override priority"]:
                        summary += "%s: package says priority is %s, override says %s.\n" % (name,
                                                                                             entry["priority"],
                                                                                             entry["override priority"])

        return summary

    @session_wrapper
    def remove_known_changes(self, session=None):
        session.delete(get_dbchange(self.changes_file, session))

    def mark_missing_fields(self):
        """add "missing" in fields which we will require for the known_changes table"""
        for key in ['urgency', 'maintainer', 'fingerprint', 'changed-by' ]:
            if (not self.changes.has_key(key)) or (not self.changes[key]):
                self.changes[key]='missing'

    def __get_file_from_pool(self, filename, entry, session, logger):
        cnf = Config()

        if cnf.has_key("Dinstall::SuiteSuffix"):
            component = cnf["Dinstall::SuiteSuffix"] + entry["component"]
        else:
            component = entry["component"]

        poolname = poolify(entry["source"], component)
        l = get_location(cnf["Dir::Pool"], component, session=session)

        found, poolfile = check_poolfile(os.path.join(poolname, filename),
                                         entry['size'],
                                         entry["md5sum"],
                                         l.location_id,
                                         session=session)

        if found is None:
            if logger is not None:
                logger.log(["E: Found multiple files for pool (%s) for %s" % (filename, component)])
            return None
        elif found is False and poolfile is not None:
            if logger is not None:
                logger.log(["E: md5sum/size mismatch for %s in pool" % (filename)])
            return None
        else:
            if poolfile is None:
                if logger is not None:
                    logger.log(["E: Could not find %s in pool" % (filename)])
                return None
            else:
                return poolfile

    @session_wrapper
    def add_known_changes(self, dirpath, in_queue=None, session=None, logger=None):
        """add "missing" in fields which we will require for the known_changes table"""
        cnf = Config()

        changesfile = os.path.join(dirpath, self.changes_file)
        filetime = datetime.datetime.fromtimestamp(os.path.getctime(changesfile))

        self.mark_missing_fields()

        multivalues = {}
        for key in ("distribution", "architecture", "binary"):
            if isinstance(self.changes[key], dict):
                multivalues[key] = " ".join(self.changes[key].keys())
            else:
                multivalues[key] = self.changes[key]

        chg = DBChange()
        chg.changesname = self.changes_file
        chg.seen = filetime
        chg.in_queue_id = in_queue
        chg.source = self.changes["source"]
        chg.binaries = multivalues["binary"]
        chg.architecture = multivalues["architecture"]
        chg.version = self.changes["version"]
        chg.distribution = multivalues["distribution"]
        chg.urgency = self.changes["urgency"]
        chg.maintainer = self.changes["maintainer"]
        chg.fingerprint = self.changes["fingerprint"]
        chg.changedby = self.changes["changed-by"]
        chg.date = self.changes["date"]

        session.add(chg)

        files = []
        for chg_fn, entry in self.files.items():
            try:
                f = open(os.path.join(dirpath, chg_fn))
                cpf = ChangePendingFile()
                cpf.filename = chg_fn
                cpf.size = entry['size']
                cpf.md5sum = entry['md5sum']

                if entry.has_key('sha1sum'):
                    cpf.sha1sum = entry['sha1sum']
                else:
                    f.seek(0)
                    cpf.sha1sum = apt_pkg.sha1sum(f)

                if entry.has_key('sha256sum'):
                    cpf.sha256sum = entry['sha256sum']
                else:
                    f.seek(0)
                    cpf.sha256sum = apt_pkg.sha256sum(f)

                session.add(cpf)
                files.append(cpf)
                f.close()

            except IOError:
                # Can't find the file, try to look it up in the pool
                poolfile = self.__get_file_from_pool(chg_fn, entry, session)
                if poolfile:
                    chg.poolfiles.append(poolfile)

        chg.files = files

        # Add files referenced in .dsc, but not included in .changes
        for name, entry in self.dsc_files.items():
            if self.files.has_key(name):
                continue

            entry['source'] = self.changes['source']
            poolfile = self.__get_file_from_pool(name, entry, session, logger)
            if poolfile:
                chg.poolfiles.append(poolfile)

        session.commit()
        chg = session.query(DBChange).filter_by(changesname = self.changes_file).one();

        return chg

    def unknown_files_fields(self, name):
        return sorted(list( set(self.files[name].keys()) -
                            set(CHANGESFIELDS_FILES)))

    def unknown_changes_fields(self):
        return sorted(list( set(self.changes.keys()) -
                            set(CHANGESFIELDS_MANDATORY + CHANGESFIELDS_OPTIONAL)))

    def unknown_dsc_fields(self):
        return sorted(list( set(self.dsc.keys()) -
                            set(CHANGESFIELDS_DSC)))

    def unknown_dsc_files_fields(self, name):
        return sorted(list( set(self.dsc_files[name].keys()) -
                            set(CHANGESFIELDS_DSCFILES_MANDATORY + CHANGESFIELDS_DSCFILES_OPTIONAL)))

    def str_files(self):
        r = []
        for name, entry in self.files.items():
            r.append("  %s:" % (name))
            for i in CHANGESFIELDS_FILES:
                if entry.has_key(i):
                    r.append("   %s: %s" % (i.capitalize(), entry[i]))
            xfields = self.unknown_files_fields(name)
            if len(xfields) > 0:
                r.append("files[%s] still has following unrecognised keys: %s" % (name, ", ".join(xfields)))

        return r

    def str_changes(self):
        r = []
        for i in CHANGESFIELDS_MANDATORY:
            val = self.changes[i]
            if isinstance(val, list):
                val = " ".join(val)
            elif isinstance(val, dict):
                val = " ".join(val.keys())
            r.append('  %s: %s' % (i.capitalize(), val))

        for i in CHANGESFIELDS_OPTIONAL:
            if self.changes.has_key(i):
                r.append('  %s: %s' % (i.capitalize(), self.changes[i]))

        xfields = self.unknown_changes_fields()
        if len(xfields) > 0:
            r.append("Warning: changes still has the following unrecognised fields: %s" % ", ".join(xfields))

        return r

    def str_dsc(self):
        r = []
        for i in CHANGESFIELDS_DSC:
            if self.dsc.has_key(i):
                r.append('  %s: %s' % (i.capitalize(), self.dsc[i]))

        xfields = self.unknown_dsc_fields()
        if len(xfields) > 0:
            r.append("Warning: dsc still has the following unrecognised fields: %s" % ", ".join(xfields))

        return r

    def str_dsc_files(self):
        r = []
        for name, entry in self.dsc_files.items():
            r.append("  %s:" % (name))
            for i in CHANGESFIELDS_DSCFILES_MANDATORY:
                r.append("   %s: %s" % (i.capitalize(), entry[i]))
            for i in CHANGESFIELDS_DSCFILES_OPTIONAL:
                if entry.has_key(i):
                    r.append("   %s: %s" % (i.capitalize(), entry[i]))
            xfields = self.unknown_dsc_files_fields(name)
            if len(xfields) > 0:
                r.append("dsc_files[%s] still has following unrecognised keys: %s" % (name, ", ".join(xfields)))

        return r

    def __str__(self):
        r = []

        r.append(" Changes:")
        r += self.str_changes()

        r.append("")

        r.append(" Dsc:")
        r += self.str_dsc()

        r.append("")

        r.append(" Files:")
        r += self.str_files()

        r.append("")

        r.append(" Dsc Files:")
        r += self.str_dsc_files()

        return "\n".join(r)

__all__.append('Changes')
