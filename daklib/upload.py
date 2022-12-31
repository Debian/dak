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
import errno
import functools
import os

from daklib.aptversion import AptVersion
from daklib.gpg import SignedFile
from daklib.regexes import *
import daklib.dakapt
import daklib.packagelist


class UploadException(Exception):
    pass


class InvalidChangesException(UploadException):
    pass


class InvalidBinaryException(UploadException):
    pass


class InvalidSourceException(UploadException):
    pass


class InvalidHashException(UploadException):
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
                "If you did not include {1} in your upload, a different version\n"
                "might already be known to the archive software.") \
                .format(self.hash_name, self.filename, self.expected, self.actual)


class InvalidFilenameException(UploadException):
    def __init__(self, filename):
        self.filename = filename

    def __str__(self):
        return "Invalid filename '{0}'.".format(self.filename)


class FileDoesNotExist(UploadException):
    def __init__(self, filename):
        self.filename = filename

    def __str__(self):
        return "Refers to non-existing file '{0}'".format(self.filename)


class HashedFile:
    """file with checksums
    """

    def __init__(self, filename, size, md5sum, sha1sum, sha256sum, section=None, priority=None, input_filename=None):
        self.filename = filename
        """name of the file
        @type: str
        """

        if input_filename is None:
            input_filename = filename
        self.input_filename = input_filename
        """name of the file on disk

        Used for temporary files that should not be installed using their on-disk name.
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
        with open(path, 'r') as fh:
            size = os.fstat(fh.fileno()).st_size
            hashes = daklib.dakapt.DakHashes(fh)
        return cls(filename, size, hashes.md5, hashes.sha1, hashes.sha256, section, priority)

    def check(self, directory):
        """Validate hashes

        Check if size and hashes match the expected value.

        @type  directory: str
        @param directory: directory the file is located in

        @raise InvalidHashException: hash mismatch
        """
        path = os.path.join(directory, self.input_filename)
        try:
            with open(path) as fh:
                self.check_fh(fh)
        except OSError as e:
            if e.errno == errno.ENOENT:
                raise FileDoesNotExist(self.input_filename)
            raise

    def check_fh(self, fh):
        size = os.fstat(fh.fileno()).st_size
        fh.seek(0)
        hashes = daklib.dakapt.DakHashes(fh)

        if size != self.size:
            raise InvalidHashException(self.filename, 'size', self.size, size)

        if hashes.md5 != self.md5sum:
            raise InvalidHashException(self.filename, 'md5sum', self.md5sum, hashes.md5)

        if hashes.sha1 != self.sha1sum:
            raise InvalidHashException(self.filename, 'sha1sum', self.sha1sum, hashes.sha1)

        if hashes.sha256 != self.sha256sum:
            raise InvalidHashException(self.filename, 'sha256sum', self.sha256sum, hashes.sha256)


def parse_file_list(control, has_priority_and_section, safe_file_regexp=re_file_safe, fields=('Files', 'Checksums-Sha1', 'Checksums-Sha256')):
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

    for line in control.get(fields[0], "").split('\n'):
        if len(line) == 0:
            continue

        if has_priority_and_section:
            (md5sum, size, section, priority, filename) = line.split()
            entry = dict(md5sum=md5sum, size=int(size), section=section, priority=priority, filename=filename)
        else:
            (md5sum, size, filename) = line.split()
            entry = dict(md5sum=md5sum, size=int(size), filename=filename)

        entries[filename] = entry

    for line in control.get(fields[1], "").split('\n'):
        if len(line) == 0:
            continue
        (sha1sum, size, filename) = line.split()
        entry = entries.get(filename, None)
        if entry is None:
            raise InvalidChangesException('{0} is listed in {1}, but not in {2}.'.format(filename, fields[1], fields[0]))
        if entry is not None and entry.get('size', None) != int(size):
            raise InvalidChangesException('Size for {0} in {1} and {2} fields differ.'.format(filename, fields[0], fields[1]))
        entry['sha1sum'] = sha1sum

    for line in control.get(fields[2], "").split('\n'):
        if len(line) == 0:
            continue
        (sha256sum, size, filename) = line.split()
        entry = entries.get(filename, None)
        if entry is None:
            raise InvalidChangesException('{0} is listed in {1}, but not in {2}.'.format(filename, fields[2], fields[0]))
        if entry is not None and entry.get('size', None) != int(size):
            raise InvalidChangesException('Size for {0} in {1} and {2} fields differ.'.format(filename, fields[0], fields[2]))
        entry['sha256sum'] = sha256sum

    files = {}
    for entry in entries.values():
        filename = entry['filename']
        if 'size' not in entry:
            raise InvalidChangesException('No size for {0}.'.format(filename))
        if 'md5sum' not in entry:
            raise InvalidChangesException('No md5sum for {0}.'.format(filename))
        if 'sha1sum' not in entry:
            raise InvalidChangesException('No sha1sum for {0}.'.format(filename))
        if 'sha256sum' not in entry:
            raise InvalidChangesException('No sha256sum for {0}.'.format(filename))
        if safe_file_regexp is not None and not safe_file_regexp.match(filename):
            raise InvalidChangesException("{0}: References file with unsafe filename {1}.".format(self.filename, filename))
        files[filename] = HashedFile(**entry)

    return files


@functools.total_ordering
class Changes:
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

        with open(self.path, 'rb') as fd:
            data = fd.read()
        self.signature = SignedFile(data, keyrings, require_signature)
        self.changes = apt_pkg.TagSection(self.signature.contents)
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
        return self.signature.primary_fingerprint

    @property
    def valid_signature(self):
        """C{True} if the .changes has a valid signature
        @type: bool
        """
        return self.signature.valid

    @property
    def weak_signature(self):
        """C{True} if the .changes was signed using a weak algorithm
        @type: bool
        """
        return self.signature.weak_signature

    @property
    def signature_timestamp(self):
        return self.signature.signature_timestamp

    @property
    def contents_sha1(self):
        return self.signature.contents_sha1

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
            for f in self.files.values():
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
            self._binaries = [
                Binary(self.directory, f)
                for f in self.files.values()
                if re_file_binary.match(f.filename)
            ]
        return self._binaries

    @property
    def byhand_files(self):
        """included byhand files
        @type: list of L{daklib.upload.HashedFile}
        """
        byhand = []

        for f in self.files.values():
            if f.section == 'byhand' or f.section[:4] == 'raw-':
                byhand.append(f)
                continue
            if re_file_dsc.match(f.filename) or re_file_source.match(f.filename) or re_file_binary.match(f.filename):
                continue
            if re_file_buildinfo.match(f.filename):
                continue

            raise InvalidChangesException("{0}: {1} looks like a byhand package, but is in section {2}".format(self.filename, f.filename, f.section))

        return byhand

    @property
    def buildinfo_files(self):
        """included buildinfo files
        @type: list of L{daklib.upload.HashedFile}
        """
        return [
            f for f in self.files.values()
            if re_file_buildinfo.match(f.filename)
        ]

    @property
    def binary_names(self):
        """names of included binary packages
        @type: list of str
        """
        return self.changes.get('Binary', '').split()

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
        return sum(f.size for f in self.files.values())

    def _key(self):
        """tuple used to compare two changes files

        We sort by source name and version first.  If these are identical,
        we sort changes that include source before those without source (so
        that sourceful uploads get processed first), and finally fall back
        to the filename (this should really never happen).

        @rtype:  tuple
        """
        return (
            self.changes.get('Source'),
            AptVersion(self.changes.get('Version', '')),
            not self.sourceful,
            self.filename
        )

    def __eq__(self, other):
        return self._key() == other._key()

    def __lt__(self, other):
        return self._key() < other._key()


class Binary:
    """Representation of a binary package
    """

    def __init__(self, directory, hashed_file):
        self.hashed_file = hashed_file
        """file object for the .deb
        @type: HashedFile
        """

        path = os.path.join(directory, hashed_file.input_filename)
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
    def name(self):
        return self.control['Package']

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


class Source:
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

        if self._dsc_file is None:
            raise InvalidSourceException("No .dsc included in source files")

        # make sure the hash for the dsc is valid before we use it
        self._dsc_file.check(directory)

        dsc_file_path = os.path.join(directory, self._dsc_file.input_filename)
        with open(dsc_file_path, 'rb') as fd:
            data = fd.read()
        self.signature = SignedFile(data, keyrings, require_signature)
        self.dsc = apt_pkg.TagSection(self.signature.contents)
        """dict to access fields in the .dsc file
        @type: dict-like
        """

        self.package_list = daklib.packagelist.PackageList(self.dsc)
        """Information about packages built by the source.
        @type: daklib.packagelist.PackageList
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
        return self.signature.primary_fingerprint

    @property
    def valid_signature(self):
        """C{True} if the .dsc has a valid signature
        @type: bool
        """
        return self.signature.valid

    @property
    def weak_signature(self):
        """C{True} if the .dsc was signed using a weak algorithm
        @type: bool
        """
        return self.signature.weak_signature

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
