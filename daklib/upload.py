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
archive.  Central is the `Changes` class which represents a changes file.
It provides methods to access the included binary and source packages.
"""

import apt_inst
import apt_pkg
import os
import re
from .gpg import SignedFile
from .regexes import *

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
        return "Invalid {0} hash for {1}: expected {2}, but got {3}.".format(self.hash_name, self.filename, self.expected, self.actual)

class InvalidFilenameException(Exception):
    def __init__(self, filename):
        self.filename = filename
    def __str__(self):
        return "Invalid filename '{0}'.".format(self.filename)

class HashedFile(object):
    """file with checksums

    Attributes:
       filename (str): name of the file
       size (long): size in bytes
       md5sum (str): MD5 hash in hexdigits
       sha1sum (str): SHA1 hash in hexdigits
       sha256sum (str): SHA256 hash in hexdigits
       section (str): section or None
       priority (str): priority or None
    """
    def __init__(self, filename, size, md5sum, sha1sum, sha256sum, section=None, priority=None):
        self.filename = filename
        self.size = size
        self.md5sum = md5sum
        self.sha1sum = sha1sum
        self.sha256sum = sha256sum
        self.section = section
        self.priority = priority

    def check(self, directory):
        """Validate hashes

        Check if size and hashes match the expected value.

        Args:
           directory (str): directory the file is located in

        Raises:
           InvalidHashException: hash mismatch
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

    Args:
       control (dict-like): control file to take fields from
       has_priority_and_section (bool): Files include section and priority (as in .changes)

    Raises:
       InvalidChangesException: missing fields or other grave errors

    Returns:
       dictonary mapping filenames to `daklib.upload.HashedFile` objects
    """
    entries = {}

    for line in control["Files"].split('\n'):
        if len(line) == 0:
            continue

        if has_priority_and_section:
            (md5sum, size, section, priority, filename) = line.split()
            entry = dict(md5sum=md5sum, size=long(size), section=section, priority=priority, filename=filename)
        else:
            (md5sum, size, filename) = line.split()
            entry = dict(md5sum=md5sum, size=long(size), filename=filename)

        entries[filename] = entry

    for line in control["Checksums-Sha1"].split('\n'):
        if len(line) == 0:
            continue
        (sha1sum, size, filename) = line.split()
        entry = entries.get(filename, None)
        if entry.get('size', None) != long(size):
            raise InvalidChangesException('Size for {0} in Files and Checksum-Sha1 fields differ.'.format(filename))
        entry['sha1sum'] = sha1sum

    for line in control["Checksums-Sha256"].split('\n'):
        if len(line) == 0:
            continue
        (sha256sum, size, filename) = line.split()
        entry = entries.get(filename, None)
        if entry is None:
            raise InvalidChangesException('No sha256sum for {0}.'.format(filename))
        if entry.get('size', None) != long(size):
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

    Attributes:
       architectures (list of str): list of architectures included in the upload
       binaries (list of daklib.upload.Binary): included binary packages
       binary_names (list of str): names of included binary packages
       byhand_files (list of daklib.upload.HashedFile): included byhand files
       bytes (int): total size of files included in this upload in bytes
       changes (dict-like): dict to access fields of the .changes file
       closed_bugs (list of str): list of bugs closed by this upload
       directory (str): directory the .changes is located in
       distributions (list of str): list of target distributions for the upload
       filename (str): name of the .changes file
       files (dict): dict mapping filenames to daklib.upload.HashedFile objects
       path (str): path to the .changes files
       primary_fingerprint (str): fingerprint of the PGP key used for the signature
       source (daklib.upload.Source or None): included source
       valid_signature (bool): True if the changes has a valid signature
    """
    def __init__(self, directory, filename, keyrings, require_signature=True):
        if not re_file_safe.match(filename):
            raise InvalidChangesException('{0}: unsafe filename'.format(filename))
        self.directory = directory
        self.filename = filename
        data = open(self.path).read()
        self._signed_file = SignedFile(data, keyrings, require_signature)
        self.changes = apt_pkg.TagSection(self._signed_file.contents)
        self._binaries = None
        self._source = None
        self._files = None
        self._keyrings = keyrings
        self._require_signature = require_signature

    @property
    def path(self):
        return os.path.join(self.directory, self.filename)

    @property
    def primary_fingerprint(self):
        return self._signed_file.primary_fingerprint

    @property
    def valid_signature(self):
        return self._signed_file.valid

    @property
    def architectures(self):
        return self.changes['Architecture'].split()

    @property
    def distributions(self):
        return self.changes['Distribution'].split()

    @property
    def source(self):
        if self._source is None:
            source_files = []
            for f in self.files.itervalues():
                if re_file_dsc.match(f.filename) or re_file_source.match(f.filename):
                    source_files.append(f)
            if len(source_files) > 0:
                self._source = Source(self.directory, source_files, self._keyrings, self._require_signature)
        return self._source

    @property
    def binaries(self):
        if self._binaries is None:
            binaries = []
            for f in self.files.itervalues():
                if re_file_binary.match(f.filename):
                    binaries.append(Binary(self.directory, f))
            self._binaries = binaries
        return self._binaries

    @property
    def byhand_files(self):
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
        return self.changes['Binary'].split()

    @property
    def closed_bugs(self):
        return self.changes.get('Closes', '').split()

    @property
    def files(self):
        if self._files is None:
            self._files = parse_file_list(self.changes, True)
        return self._files

    @property
    def bytes(self):
        count = 0
        for f in self.files.itervalues():
            count += f.size
        return count

    def __cmp__(self, other):
        """Compare two changes packages

        We sort by source name and version first.  If these are identical,
        we sort changes that include source before those without source (so
        that sourceful uploads get processed first), and finally fall back
        to the filename (this should really never happen).

        Returns:
           -1 if self < other, 0 if self == other, 1 if self > other
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

    Attributes:
       component (str): component name
       control (dict-like): dict to access fields in DEBIAN/control
       hashed_file (HashedFile): HashedFile object for the .deb
    """
    def __init__(self, directory, hashed_file):
        self.hashed_file = hashed_file

        path = os.path.join(directory, hashed_file.filename)
        data = apt_inst.DebFile(path).control.extractdata("control")
        self.control = apt_pkg.TagSection(data)

    @property
    def source(self):
        """Get source package name and version

        Returns:
           tuple containing source package name and version
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
        """Get package type

        Returns:
           String with the package type ('deb' or 'udeb')
        """
        match = re_file_binary.match(self.hashed_file.filename)
        if not match:
            raise InvalidBinaryException('{0}: Does not match re_file_binary'.format(self.hashed_file.filename))
        return match.group('type')

    @property
    def component(self):
        fields = self.control['Section'].split('/')
        if len(fields) > 1:
            return fields[0]
        return "main"

class Source(object):
    """Representation of a source package

    Attributes:
       component (str): guessed component name. Might be wrong!
       dsc (dict-like): dict to access fields in the .dsc file
       hashed_files (list of daklib.upload.HashedFile): list of source files (including .dsc)
       files (dict): dictonary mapping filenames to HashedFile objects for
           additional source files (not including .dsc)
       primary_fingerprint (str): fingerprint of the PGP key used for the signature
       valid_signature (bool):  True if the dsc has a valid signature
    """
    def __init__(self, directory, hashed_files, keyrings, require_signature=True):
        self.hashed_files = hashed_files
        self._dsc_file = None
        for f in hashed_files:
            if re_file_dsc.match(f.filename):
                if self._dsc_file is not None:
                    raise InvalidSourceException("Multiple .dsc found ({0} and {1})".format(self._dsc_file.filename, f.filename))
                else:
                    self._dsc_file = f
        dsc_file_path = os.path.join(directory, self._dsc_file.filename)
        data = open(dsc_file_path, 'r').read()
        self._signed_file = SignedFile(data, keyrings, require_signature)
        self.dsc = apt_pkg.TagSection(self._signed_file.contents)
        self._files = None

    @property
    def files(self):
        if self._files is None:
            self._files = parse_file_list(self.dsc, False)
        return self._files

    @property
    def primary_fingerprint(self):
        return self._signed_file.primary_fingerprint

    @property
    def valid_signature(self):
        return self._signed_file.valid

    @property
    def component(self):
        if 'Section' not in self.dsc:
            return 'main'
        fields = self.dsc['Section'].split('/')
        if len(fields) > 1:
            return fields[0]
        return "main"
