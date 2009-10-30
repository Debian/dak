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
import time

import datetime
from cPickle import Unpickler, Pickler
from errno import EPERM

from apt_inst import debExtractControl
from apt_pkg import ParseSection

from utils import open_file, fubar, poolify
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
                    summary += ParseSection(debExtractControl(deb_fh))["Description"] + '\n'
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

    def remove_known_changes(self, session=None):
        if session is None:
            session = DBConn().session()
            privatetrans = True

        session.delete(get_knownchange(self.changes_file, session))

        if privatetrans:
            session.commit()
            session.close()


    def mark_missing_fields(self):
        """add "missing" in fields which we will require for the known_changes table"""
        for key in ['urgency', 'maintainer', 'fingerprint', 'changedby' ]:
            if (not self.changes.has_key(key)) or (not self.changes[key]):
                self.changes[key]='missing'

    def add_known_changes(self, queue, session=None):
        """add "missing" in fields which we will require for the known_changes table"""
        cnf = Config()
        if session is None:
            session = DBConn().session()
            privatetrans = True

        dirpath = cnf["Dir::Queue::%s" % (queue) ]
        changesfile = os.path.join(dirpath, self.changes_file)
        filetime = datetime.datetime.fromtimestamp(os.path.getctime(changesfile))

        self.mark_missing_fields()

        session.execute(
            """INSERT INTO known_changes
              (changesname, seen, source, binaries, architecture, version,
              distribution, urgency, maintainer, fingerprint, changedby, date)
              VALUES (:changesfile,:filetime,:source,:binary, :architecture,
              :version,:distribution,:urgency,:maintainer,:fingerprint,:changedby,:date)""",
              { 'changesfile':changesfile,
                'filetime':filetime,
                'source':self.changes["source"],
                'binary':self.changes["binary"],
                'architecture':self.changes["architecture"],
                'version':self.changes["version"],
                'distribution':self.changes["distribution"],
                'urgency':self.changes["urgency"],
                'maintainer':self.changes["maintainer"],
                'fingerprint':self.changes["fingerprint"],
                'changedby':self.changes["changed-by"],
                'date':self.changes["date"]} )

        if privatetrans:
            session.commit()
            session.close()

    def load_dot_dak(self, changesfile):
        """
        Update ourself by reading a previously created cPickle .dak dumpfile.
        """

        self.changes_file = changesfile
        dump_filename = self.changes_file[:-8]+".dak"
        dump_file = open_file(dump_filename)

        p = Unpickler(dump_file)

        self.changes.update(p.load())
        self.dsc.update(p.load())
        self.files.update(p.load())
        self.dsc_files.update(p.load())

        next_obj = p.load()
        if isinstance(next_obj, dict):
            self.orig_files.update(next_obj)
        else:
            # Auto-convert old dak files to new format supporting
            # multiple tarballs
            orig_tar_gz = None
            for dsc_file in self.dsc_files.keys():
                if dsc_file.endswith(".orig.tar.gz"):
                    orig_tar_gz = dsc_file
            self.orig_files[orig_tar_gz] = {}
            if next_obj != None:
                self.orig_files[orig_tar_gz]["id"] = next_obj
            next_obj = p.load()
            if next_obj != None and next_obj != "":
                self.orig_files[orig_tar_gz]["location"] = next_obj
            if len(self.orig_files[orig_tar_gz]) == 0:
                del self.orig_files[orig_tar_gz]

        dump_file.close()

    def sanitised_files(self):
        ret = {}
        for name, entry in self.files.items():
            ret[name] = {}
            for i in CHANGESFIELDS_FILES:
                if entry.has_key(i):
                    ret[name][i] = entry[i]

        return ret

    def sanitised_changes(self):
        ret = {}
        # Mandatory changes fields
        for i in CHANGESFIELDS_MANDATORY:
            ret[i] = self.changes[i]

        # Optional changes fields
        for i in CHANGESFIELDS_OPTIONAL:
            if self.changes.has_key(i):
                ret[i] = self.changes[i]

        return ret

    def sanitised_dsc(self):
        ret = {}
        for i in CHANGESFIELDS_DSC:
            if self.dsc.has_key(i):
                ret[i] = self.dsc[i]

        return ret

    def sanitised_dsc_files(self):
        ret = {}
        for name, entry in self.dsc_files.items():
            ret[name] = {}
            # Mandatory dsc_files fields
            for i in CHANGESFIELDS_DSCFILES_MANDATORY:
                ret[name][i] = entry[i]

            # Optional dsc_files fields
            for i in CHANGESFIELDS_DSCFILES_OPTIONAL:
                if entry.has_key(i):
                    ret[name][i] = entry[i]

        return ret

    def sanitised_orig_files(self):
        ret = {}
        for name, entry in self.orig_files.items():
            ret[name] = {}
            # Optional orig_files fields
            for i in CHANGESFIELDS_ORIGFILES:
                if entry.has_key(i):
                    ret[name][i] = entry[i]

        return ret

    def write_dot_dak(self, dest_dir):
        """
        Dump ourself into a cPickle file.

        @type dest_dir: string
        @param dest_dir: Path where the dumpfile should be stored

        @note: This could just dump the dictionaries as is, but I'd like to avoid this so
               there's some idea of what process-accepted & process-new use from
               process-unchecked. (JT)

        """

        dump_filename = os.path.join(dest_dir, self.changes_file[:-8] + ".dak")
        dump_file = open_file(dump_filename, 'w')

        try:
            os.chmod(dump_filename, 0664)
        except OSError, e:
            # chmod may fail when the dumpfile is not owned by the user
            # invoking dak (like e.g. when NEW is processed by a member
            # of ftpteam)
            if e.errno == EPERM:
                perms = stat.S_IMODE(os.stat(dump_filename)[stat.ST_MODE])
                # security precaution, should never happen unless a weird
                # umask is set anywhere
                if perms & stat.S_IWOTH:
                    fubar("%s is world writable and chmod failed." % \
                        (dump_filename,))
                # ignore the failed chmod otherwise as the file should
                # already have the right privileges and is just, at worst,
                # unreadable for world
            else:
                raise

        p = Pickler(dump_file, 1)

        p.dump(self.sanitised_changes())
        p.dump(self.sanitised_dsc())
        p.dump(self.sanitised_files())
        p.dump(self.sanitised_dsc_files())
        p.dump(self.sanitised_orig_files())

        dump_file.close()

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
