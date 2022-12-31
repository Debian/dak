# Copyright (C) 2015, Ansgar Burchardt <ansgar@debian.org>
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

import daklib.compress
import daklib.config
import daklib.dakapt
import daklib.dbconn
import daklib.gpg
import daklib.upload
import daklib.regexes

import apt_pkg
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import urllib.parse

from daklib.dbconn import Archive, Component, DBBinary, DBSource, PoolFile
from sqlalchemy.orm import object_session
from typing import Optional

# Hmm, maybe use APT directly for all of this?

_release_hashes_fields = ('MD5Sum', 'SHA1', 'SHA256')


class Release:
    def __init__(self, base, suite_name, data):
        self._base = base
        self._suite_name = suite_name
        self._dict = apt_pkg.TagSection(data)
        self._hashes = daklib.upload.parse_file_list(self._dict, False, daklib.regexes.re_file_safe_slash, _release_hashes_fields)

    def architectures(self):
        return self._dict['Architectures'].split()

    def components(self):
        return self._dict['Components'].split()

    def packages(self, component, architecture):
        fn = '{0}/binary-{1}/Packages'.format(component, architecture)
        tmp = obtain_release_file(self, fn)
        return apt_pkg.TagFile(tmp.fh())

    def sources(self, component):
        fn = '{0}/source/Sources'.format(component)
        tmp = obtain_release_file(self, fn)
        return apt_pkg.TagFile(tmp.fh())

    def suite(self):
        return self._dict['Suite']

    def codename(self):
        return self._dict['Codename']
    # TODO: Handle Date/Valid-Until to make sure we import
    # a newer version than before


class File:
    def __init__(self):
        config = daklib.config.Config()
        self._tmp = tempfile.NamedTemporaryFile(dir=config['Dir::TempPath'])

    def fh(self):
        self._tmp.seek(0)
        return self._tmp

    def hashes(self):
        return daklib.dakapt.DakHashes(self.fh())


def obtain_file(base, path) -> File:
    """Obtain a file 'path' located below 'base'

    .. note::

       return type can still change
    """
    fn = '{0}/{1}'.format(base, path)
    tmp = File()
    if fn.startswith('http://'):
        fh = urllib.request.urlopen(fn, timeout=300)
        shutil.copyfileobj(fh, tmp._tmp)
        fh.close()
    else:
        with open(fn, 'rb') as fh:
            shutil.copyfileobj(fh, tmp._tmp)
    return tmp


def obtain_release(base, suite_name, keyring, fingerprint=None) -> Release:
    """Obtain release information"""
    tmp = obtain_file(base, 'dists/{0}/InRelease'.format(suite_name))
    data = tmp.fh().read()
    f = daklib.gpg.SignedFile(data, [keyring])
    r = Release(base, suite_name, f.contents)
    if r.suite() != suite_name and r.codename() != suite_name:
        raise Exception("Suite {0} doesn't match suite or codename from Release file.".format(suite_name))
    return r


_compressions = ('.zst', '.xz', '.gz', '.bz2')


def obtain_release_file(release, filename) -> File:
    """Obtain file referenced from Release

    A compressed version is automatically selected and decompressed if it exists.
    """
    if filename not in release._hashes:
        raise ValueError("File {0} not referenced in Release".format(filename))

    compressed = False
    for ext in _compressions:
        compressed_file = filename + ext
        if compressed_file in release._hashes:
            compressed = True
            filename = compressed_file
            break

    # Obtain file and check hashes
    tmp = obtain_file(release._base, 'dists/{0}/{1}'.format(release._suite_name, filename))
    hashedfile = release._hashes[filename]
    hashedfile.check_fh(tmp.fh())

    if compressed:
        tmp2 = File()
        daklib.compress.decompress(tmp.fh(), tmp2.fh(), filename)
        tmp = tmp2

    return tmp


def import_source_to_archive(base, entry, transaction, archive, component) -> DBSource:
    """Import source package described by 'entry' into the given 'archive' and 'component'

    'entry' needs to be a dict-like object with at least the following
    keys as used in a Sources index: Directory, Files, Checksums-Sha1,
    Checksums-Sha256
    """
    # Obtain and verify files
    if not daklib.regexes.re_file_safe_slash.match(entry['Directory']):
        raise Exception("Unsafe path in Directory field")
    hashed_files = daklib.upload.parse_file_list(entry, False)
    files = []
    for f in hashed_files.values():
        path = os.path.join(entry['Directory'], f.filename)
        tmp = obtain_file(base, path)
        f.check_fh(tmp.fh())
        files.append(tmp)
        directory, f.input_filename = os.path.split(tmp.fh().name)

    # Inject files into archive
    source = daklib.upload.Source(directory, list(hashed_files.values()), [], require_signature=False)
    # TODO: ugly hack!
    for f in hashed_files.keys():
        if f.endswith('.dsc'):
            continue
        source.files[f].input_filename = hashed_files[f].input_filename

    # TODO: allow changed_by to be NULL
    changed_by = source.dsc['Maintainer']
    db_changed_by = daklib.dbconn.get_or_set_maintainer(changed_by, transaction.session)
    db_source = transaction.install_source_to_archive(directory, source, archive, component, db_changed_by)

    return db_source


def import_package_to_suite(base, entry, transaction, suite, component) -> DBBinary:
    """Import binary package described by 'entry' into the given 'suite' and 'component'

    'entry' needs to be a dict-like object with at least the following
    keys as used in a Packages index: Filename, Size, MD5sum, SHA1,
    SHA256
    """
    # Obtain and verify file
    filename = entry['Filename']
    tmp = obtain_file(base, filename)
    directory, fn = os.path.split(tmp.fh().name)
    hashedfile = daklib.upload.HashedFile(os.path.basename(filename), int(entry['Size']), entry['MD5sum'], entry['SHA1'], entry['SHA256'], input_filename=fn)
    hashedfile.check_fh(tmp.fh())

    # Inject file into archive
    binary = daklib.upload.Binary(directory, hashedfile)
    db_binary = transaction.install_binary(directory, binary, suite, component)
    transaction.flush()

    return db_binary


def import_source_to_suite(base, entry, transaction, suite, component):
    """Import source package described by 'entry' into the given 'suite' and 'component'

    'entry' needs to be a dict-like object with at least the following
    keys as used in a Sources index: Directory, Files, Checksums-Sha1,
    Checksums-Sha256
    """
    source = import_source_to_archive(base, entry, transaction, suite.archive, component)
    source.suites.append(suite)
    transaction.flush()


def source_in_archive(source: str, version: str, archive: Archive, component: Optional[daklib.dbconn.Component] = None) -> bool:
    """Check that source package 'source' with version 'version' exists in 'archive',
    with an optional check for the given component 'component'.

    .. note::

       This should probably be moved somewhere else
    """
    session = object_session(archive)
    query = session.query(DBSource).filter_by(source=source, version=version) \
        .join(DBSource.poolfile).join(PoolFile.archives).filter_by(archive=archive)
    if component is not None:
        query = query.filter_by(component=component)
    return session.query(query.exists()).scalar()
