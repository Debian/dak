# Copyright (C) 2012, Ansgar Burchardt <ansgar@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""module to handle uploads not yet installed to the archive

This module provides classes to handle uploads not yet installed to the
archive.  Central is the L{Changes} class which represents a changes file.
It provides methods to access the included binary and source packages.
"""

import apt_inst
import apt_pkg
import os
import re

from daklib.gpg import SignedFile
from daklib.regexes import *

class InvalidChangesException(Exception):
    pass

class InvalidBinaryException(Exception):
    pass

class InvalidSourceException(Exception):
    pass

class InvalidHashException(Exception):
    def __init__(self, filename, hash_name, expected, actual):
        self.filename = filename
        self.hash_name = hash_name
        self.expected = expected
        self.actual = actual
    def __str__(self):
        return ("Invalid {0} hash for {1}:\n"
                "According to the control file the {0} hash should be {2},\n"
                "but {1} has {3}.\n"
                "\n"
                "If you did not include {1} in you upload, a different version\n"
                "might already be known to the archive software.") \
                .format(self.hash_name, self.filename, self.expected, self.actual)

class InvalidFilenameException(Exception):
    def __init__(self, filename):
        self.filename = filename
    def __str__(self):
        return "Invalid filename '{0}'.".format(self.filename)

class HashedFile(object):
    """file with checksums
    """
    def __init__(self, filename, size, md5sum, sha1sum, sha256sum, section=None, priority=None):
        self.filename = filename
        """name of the file
        @type: str
        """

        self.size = size
        """size in bytes
        @type: long
        """

        self.md5sum = md5sum
        """MD5 hash in hexdigits
        @type: str
        """

        self.sha1sum = sha1sum
        """SHA1 hash in hexdigits
        @type: str
        """

        self.sha256sum = sha256sum
        """SHA256 hash in hexdigits
        @type: str
        """

        self.section = section
        """section or C{None}
        @type: str or C{None}
        """

        self.priority = priority
        """priority or C{None}
        @type: str of C{None}
        """

    @classmethod
    def from_file(cls, directory, filename, section=None, priority=None):
        """create with values for an existing file

        Create a C{HashedFile} object that refers to an already existing file.

        @type  directory: str
        @param directory: directory the file is located in

        @type  filename: str
        @param filename: filename

        @type  section: str or C{None}
        @param section: optional section as given in .changes files

        @type  priority: str or C{None}
        @param priority: optional priority as given in .changes files

        @rtype:  L{HashedFile}
        @return: C{HashedFile} object for the given file
        """
        path = os.path.join(directory, filename)
        size = os.stat(path).st_size
        with open(path, 'r') as fh:
            hashes = apt_pkg.Hashes(fh)
        return cls(filename, size, hashes.md5, hashes.sha1, hashes.sha256, section, priority)

    def check(self, directory):
        """Validate hashes

        Check if size and hashes match the expected value.

        @type  directory: str
        @param directory: directory the file is located in

        @raise InvalidHashException: hash mismatch
        """
        path = os.path.join(directory, self.filename)
        fh = open(path, 'r')

        size = os.stat(path).st_size
        if size != self.size:
            raise InvalidHashException(self.filename, 'size', self.size, size)

        md5sum = apt_pkg.md5sum(fh)
        if md5sum != self.md5sum:
            raise InvalidHashException(self.filename, 'md5sum', self.md5sum, md5sum)

        fh.seek(0)
        sha1sum = apt_pkg.sha1sum(fh)
        if sha1sum != self.sha1sum:
            raise InvalidHashException(self.filename, 'sha1sum', self.sha1sum, sha1sum)

        fh.seek(0)
        sha256sum = apt_pkg.sha256sum(fh)
        if sha256sum != self.sha256sum:
            raise InvalidHashException(self.filename, 'sha256sum', self.sha256sum, sha256sum)

def parse_file_list(control, has_priority_and_section):
    """Parse Files and Checksums-* fields

    @type  control: dict-like
    @param control: control file to take fields from

    @type  has_priority_and_section: bool
    @param has_priority_and_section: Files field include section and priority
                                     (as in .changes)

    @raise InvalidChangesException: missing fields or other grave errors

    @rtype:  dict
    @return: dict mapping filenames to L{daklib.upload.HashedFile} objects
    """
    entries = {}

    for line in control.get("Files", "").split('\n'):
        if len(line) == 0:
            continue

        if has_priority_and_section:
            (md5sum, size, section, priority, filename) = line.split()
            entry = dict(md5sum=md5sum, size=long(size), section=section, priority=priority, filename=filename)
        else:
            (md5sum, size, filename) = line.split()
            entry = dict(md5sum=md5sum, size=long(size), filename=filename)

        entries[filename] = entry

    for line in control.get("Checksums-Sha1", "").split('\n'):
        if len(line) == 0:
            continue
        (sha1sum, size, filename) = line.split()
        entry = entries.get(filename, None)
        if entry is None:
            raise InvalidChangesException('{0} is listed in Checksums-Sha1, but not in Files.'.format(filename))
        if entry is not None and entry.get('size', None) != long(size):
            raise InvalidChangesException('Size for {0} in Files and Checksum-Sha1 fields differ.'.format(filename))
        entry['sha1sum'] = sha1sum

    for line in control.get("Checksums-Sha256", "").split('\n'):
        if len(line) == 0:
            continue
        (sha256sum, size, filename) = line.split()
        entry = entries.get(filename, None)
        if entry is None:
            raise InvalidChangesException('{0} is listed in Checksums-Sha256, but not in Files.'.format(filename))
        if entry is not None and entry.get('size', None) != long(size):
            raise InvalidChangesException('Size for {0} in Files and Checksum-Sha256 fields differ.'.format(filename))
        entry['sha256sum'] = sha256sum

    files = {}
    for entry in entries.itervalues():
        filename = entry['filename']
        if 'size' not in entry:
            raise InvalidChangesException('No size for {0}.'.format(filename))
        if 'md5sum' not in entry:
            raise InvalidChangesException('No md5sum for {0}.'.format(filename))
        if 'sha1sum' not in entry:
            raise InvalidChangesException('No sha1sum for {0}.'.format(filename))
        if 'sha256sum' not in entry:
            raise InvalidChangesException('No sha256sum for {0}.'.format(filename))
        if not re_file_safe.match(filename):
            raise InvalidChangesException("{0}: References file with unsafe filename {1}.".format(self.filename, filename))
        f = files[filename] = HashedFile(**entry)

    return files

class Changes(object):
    """Representation of a .changes file
    """
    def __init__(self, directory, filename, keyrings, require_signature=True):
        if not re_file_safe.match(filename):
            raise InvalidChangesException('{0}: unsafe filename'.format(filename))

        self.directory = directory
        """directory the .changes is located in
        @type: str
        """

        self.filename = filename
        """name of the .changes file
        @type: str
        """

        data = open(self.path).read()
        self._signed_file = SignedFile(data, keyrings, require_signature)
        self.changes = apt_pkg.TagSection(self._signed_file.contents)
        """dict to access fields of the .changes file
        @type: dict-like
        """

        self._binaries = None
        self._source = None
        self._files = None
        self._keyrings = keyrings
        self._require_signature = require_signature

    @property
    def path(self):
        """path to the .changes file
        @type: str
        """
        return os.path.join(self.directory, self.filename)

    @property
    def primary_fingerprint(self):
        """fingerprint of the key used for signing the .changes file
        @type: str
        """
        return self._signed_file.primary_fingerprint

    @property
    def valid_signature(self):
        """C{True} if the .changes has a valid signature
        @type: bool
        """
        return self._signed_file.valid

    @property
    def architectures(self):
        """list of architectures included in the upload
        @type: list of str
        """
        return self.changes.get('Architecture', '').split()

    @property
    def distributions(self):
        """list of target distributions for the upload
        @type: list of str
        """
        return self.changes['Distribution'].split()

    @property
    def source(self):
        """included source or C{None}
        @type: L{daklib.upload.Source} or C{None}
        """
        if self._source is None:
            source_files = []
            for f in self.files.itervalues():
                if re_file_dsc.match(f.filename) or re_file_source.match(f.filename):
                    source_files.append(f)
            if len(source_files) > 0:
                self._source = Source(self.directory, source_files, self._keyrings, self._require_signature)
        return self._source

    @property
    def sourceful(self):
        """C{True} if the upload includes source
        @type: bool
        """
        return "source" in self.architectures

    @property
    def source_name(self):
        """source package name
        @type: str
        """
        return re_field_source.match(self.changes['Source']).group('package')

    @property
    def binaries(self):
        """included binary packages
        @type: list of L{daklib.upload.Binary}
        """
        if self._binaries is None:
            binaries = []
            for f in self.files.itervalues():
                if re_file_binary.match(f.filename):
                    binaries.append(Binary(self.directory, f))
            self._binaries = binaries
        return self._binaries

    @property
    def byhand_files(self):
        """included byhand files
        @type: list of L{daklib.upload.HashedFile}
        """
        byhand = []

        for f in self.files.itervalues():
            if re_file_dsc.match(f.filename) or re_file_source.match(f.filename) or re_file_binary.match(f.filename):
                continue
            if f.section != 'byhand' and f.section[:4] != 'raw-':
                raise InvalidChangesException("{0}: {1} looks like a byhand package, but is in section {2}".format(self.filename, f.filename, f.section))
            byhand.append(f)

        return byhand

    @property
    def binary_names(self):
        """names of included binary packages
        @type: list of str
        """
        return self.changes['Binary'].split()

    @property
    def closed_bugs(self):
        """bugs closed by this upload
        @type: list of str
        """
        return self.changes.get('Closes', '').split()

    @property
    def files(self):
        """dict mapping filenames to L{daklib.upload.HashedFile} objects
        @type: dict
        """
        if self._files is None:
            self._files = parse_file_list(self.changes, True)
        return self._files

    @property
    def bytes(self):
        """total size of files included in this upload in bytes
        @type: number
        """
        count = 0
        for f in self.files.itervalues():
            count += f.size
        return count

    def __cmp__(self, other):
        """compare two changes files

        We sort by source name and version first.  If these are identical,
        we sort changes that include source before those without source (so
        that sourceful uploads get processed first), and finally fall back
        to the filename (this should really never happen).

        @rtype:  number
        @return: n where n < 0 if self < other, n = 0 if self == other, n > 0 if self > other
        """
        ret = cmp(self.changes.get('Source'), other.changes.get('Source'))

        if ret == 0:
            # compare version
            ret = apt_pkg.version_compare(self.changes.get('Version', ''), other.changes.get('Version', ''))

        if ret == 0:
            # sort changes with source before changes without source
            if 'source' in self.architectures and 'source' not in other.architectures:
                ret = -1
            elif 'source' not in self.architectures and 'source' in other.architectures:
                ret = 1
            else:
                ret = 0

        if ret == 0:
            # fall back to filename
            ret = cmp(self.filename, other.filename)

        return ret

class Binary(object):
    """Representation of a binary package
    """
    def __init__(self, directory, hashed_file):
        self.hashed_file = hashed_file
        """file object for the .deb
        @type: HashedFile
        """

        path = os.path.join(directory, hashed_file.filename)
        data = apt_inst.DebFile(path).control.extractdata("control")

        self.control = apt_pkg.TagSection(data)
        """dict to access fields in DEBIAN/control
        @type: dict-like
        """

    @classmethod
    def from_file(cls, directory, filename):
        hashed_file = HashedFile.from_file(directory, filename)
        return cls(directory, hashed_file)

    @property
    def source(self):
        """get tuple with source package name and version
        @type: tuple of str
        """
        source = self.control.get("Source", None)
        if source is None:
            return (self.control["Package"], self.control["Version"])
        match = re_field_source.match(source)
        if not match:
            raise InvalidBinaryException('{0}: Invalid Source field.'.format(self.hashed_file.filename))
        version = match.group('version')
        if version is None:
            version = self.control['Version']
        return (match.group('package'), version)

    @property
    def type(self):
        """package type ('deb' or 'udeb')
        @type: str
        """
        match = re_file_binary.match(self.hashed_file.filename)
        if not match:
            raise InvalidBinaryException('{0}: Does not match re_file_binary'.format(self.hashed_file.filename))
        return match.group('type')

    @property
    def component(self):
        """component name
        @type: str
        """
        fields = self.control['Section'].split('/')
        if len(fields) > 1:
            return fields[0]
        return "main"

class Source(object):
    """Representation of a source package
    """
    def __init__(self, directory, hashed_files, keyrings, require_signature=True):
        self.hashed_files = hashed_files
        """list of source files (including the .dsc itself)
        @type: list of L{HashedFile}
        """

        self._dsc_file = None
        for f in hashed_files:
            if re_file_dsc.match(f.filename):
                if self._dsc_file is not None:
                    raise InvalidSourceException("Multiple .dsc found ({0} and {1})".format(self._dsc_file.filename, f.filename))
                else:
                    self._dsc_file = f

        # make sure the hash for the dsc is valid before we use it
        self._dsc_file.check(directory)

        dsc_file_path = os.path.join(directory, self._dsc_file.filename)
        data = open(dsc_file_path, 'r').read()
        self._signed_file = SignedFile(data, keyrings, require_signature)
        self.dsc = apt_pkg.TagSection(self._signed_file.contents)
        """dict to access fields in the .dsc file
        @type: dict-like
        """

        self._files = None

    @classmethod
    def from_file(cls, directory, filename, keyrings, require_signature=True):
        hashed_file = HashedFile.from_file(directory, filename)
        return cls(directory, [hashed_file], keyrings, require_signature)

    @property
    def files(self):
        """dict mapping filenames to L{HashedFile} objects for additional source files

        This list does not include the .dsc itself.

        @type: dict
        """
        if self._files is None:
            self._files = parse_file_list(self.dsc, False)
        return self._files

    @property
    def primary_fingerprint(self):
        """fingerprint of the key used to sign the .dsc
        @type: str
        """
        return self._signed_file.primary_fingerprint

    @property
    def valid_signature(self):
        """C{True} if the .dsc has a valid signature
        @type: bool
        """
        return self._signed_file.valid

    @property
    def component(self):
        """guessed component name

        Might be wrong. Don't rely on this.

        @type: str
        """
        if 'Section' not in self.dsc:
            return 'main'
        fields = self.dsc['Section'].split('/')
        if len(fields) > 1:
            return fields[0]
        return "main"

    @property
    def filename(self):
        """filename of .dsc file
        @type: str
        """
        return self._dsc_file.filename
