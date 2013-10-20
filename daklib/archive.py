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

"""module to manipulate the archive

This module provides classes to manipulate the archive.
"""

from daklib.dbconn import *
import daklib.checks as checks
from daklib.config import Config
import daklib.upload as upload
import daklib.utils as utils
from daklib.fstransactions import FilesystemTransaction
from daklib.regexes import re_changelog_versions, re_bin_only_nmu
import daklib.daksubprocess

import apt_pkg
from datetime import datetime
import os
import shutil
from sqlalchemy.orm.exc import NoResultFound
import sqlalchemy.exc
import tempfile
import traceback

class ArchiveException(Exception):
    pass

class HashMismatchException(ArchiveException):
    pass

class ArchiveTransaction(object):
    """manipulate the archive in a transaction
    """
    def __init__(self):
        self.fs = FilesystemTransaction()
        self.session = DBConn().session()

    def get_file(self, hashed_file, source_name, check_hashes=True):
        """Look for file C{hashed_file} in database

        @type  hashed_file: L{daklib.upload.HashedFile}
        @param hashed_file: file to look for in the database

        @type  source_name: str
        @param source_name: source package name

        @type  check_hashes: bool
        @param check_hashes: check size and hashes match

        @raise KeyError: file was not found in the database
        @raise HashMismatchException: hash mismatch

        @rtype:  L{daklib.dbconn.PoolFile}
        @return: database entry for the file
        """
        poolname = os.path.join(utils.poolify(source_name), hashed_file.filename)
        try:
            poolfile = self.session.query(PoolFile).filter_by(filename=poolname).one()
            if check_hashes and (poolfile.filesize != hashed_file.size
                                 or poolfile.md5sum != hashed_file.md5sum
                                 or poolfile.sha1sum != hashed_file.sha1sum
                                 or poolfile.sha256sum != hashed_file.sha256sum):
                raise HashMismatchException('{0}: Does not match file already existing in the pool.'.format(hashed_file.filename))
            return poolfile
        except NoResultFound:
            raise KeyError('{0} not found in database.'.format(poolname))

    def _install_file(self, directory, hashed_file, archive, component, source_name):
        """Install a file

        Will not give an error when the file is already present.

        @rtype:  L{daklib.dbconn.PoolFile}
        @return: database object for the new file
        """
        session = self.session

        poolname = os.path.join(utils.poolify(source_name), hashed_file.filename)
        try:
            poolfile = self.get_file(hashed_file, source_name)
        except KeyError:
            poolfile = PoolFile(filename=poolname, filesize=hashed_file.size)
            poolfile.md5sum = hashed_file.md5sum
            poolfile.sha1sum = hashed_file.sha1sum
            poolfile.sha256sum = hashed_file.sha256sum
            session.add(poolfile)
            session.flush()

        try:
            session.query(ArchiveFile).filter_by(archive=archive, component=component, file=poolfile).one()
        except NoResultFound:
            archive_file = ArchiveFile(archive, component, poolfile)
            session.add(archive_file)
            session.flush()

            path = os.path.join(archive.path, 'pool', component.component_name, poolname)
            hashed_file_path = os.path.join(directory, hashed_file.filename)
            self.fs.copy(hashed_file_path, path, link=False, mode=archive.mode)

        return poolfile

    def install_binary(self, directory, binary, suite, component, allow_tainted=False, fingerprint=None, source_suites=None, extra_source_archives=None):
        """Install a binary package

        @type  directory: str
        @param directory: directory the binary package is located in

        @type  binary: L{daklib.upload.Binary}
        @param binary: binary package to install

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: target suite

        @type  component: L{daklib.dbconn.Component}
        @param component: target component

        @type  allow_tainted: bool
        @param allow_tainted: allow to copy additional files from tainted archives

        @type  fingerprint: L{daklib.dbconn.Fingerprint}
        @param fingerprint: optional fingerprint

        @type  source_suites: SQLAlchemy subquery for C{daklib.dbconn.Suite} or C{True}
        @param source_suites: suites to copy the source from if they are not
                              in C{suite} or C{True} to allow copying from any
                              suite.

        @type  extra_source_archives: list of L{daklib.dbconn.Archive}
        @param extra_source_archives: extra archives to copy Built-Using sources from

        @rtype:  L{daklib.dbconn.DBBinary}
        @return: databse object for the new package
        """
        session = self.session
        control = binary.control
        maintainer = get_or_set_maintainer(control['Maintainer'], session)
        architecture = get_architecture(control['Architecture'], session)

        (source_name, source_version) = binary.source
        source_query = session.query(DBSource).filter_by(source=source_name, version=source_version)
        source = source_query.filter(DBSource.suites.contains(suite)).first()
        if source is None:
            if source_suites != True:
                source_query = source_query.join(DBSource.suites) \
                    .filter(Suite.suite_id == source_suites.c.id)
            source = source_query.first()
            if source is None:
                raise ArchiveException('{0}: trying to install to {1}, but could not find source'.format(binary.hashed_file.filename, suite.suite_name))
            self.copy_source(source, suite, component)

        db_file = self._install_file(directory, binary.hashed_file, suite.archive, component, source_name)

        unique = dict(
            package=control['Package'],
            version=control['Version'],
            architecture=architecture,
            )
        rest = dict(
            source=source,
            maintainer=maintainer,
            poolfile=db_file,
            binarytype=binary.type,
            fingerprint=fingerprint,
            )

        try:
            db_binary = session.query(DBBinary).filter_by(**unique).one()
            for key, value in rest.iteritems():
                if getattr(db_binary, key) != value:
                    raise ArchiveException('{0}: Does not match binary in database.'.format(binary.hashed_file.filename))
        except NoResultFound:
            db_binary = DBBinary(**unique)
            for key, value in rest.iteritems():
                setattr(db_binary, key, value)
            session.add(db_binary)
            session.flush()
            import_metadata_into_db(db_binary, session)

            self._add_built_using(db_binary, binary.hashed_file.filename, control, suite, extra_archives=extra_source_archives)

        if suite not in db_binary.suites:
            db_binary.suites.append(suite)

        session.flush()

        return db_binary

    def _ensure_extra_source_exists(self, filename, source, archive, extra_archives=None):
        """ensure source exists in the given archive

        This is intended to be used to check that Built-Using sources exist.

        @type  filename: str
        @param filename: filename to use in error messages

        @type  source: L{daklib.dbconn.DBSource}
        @param source: source to look for

        @type  archive: L{daklib.dbconn.Archive}
        @param archive: archive to look in

        @type  extra_archives: list of L{daklib.dbconn.Archive}
        @param extra_archives: list of archives to copy the source package from
                               if it is not yet present in C{archive}
        """
        session = self.session
        db_file = session.query(ArchiveFile).filter_by(file=source.poolfile, archive=archive).first()
        if db_file is not None:
            return True

        # Try to copy file from one extra archive
        if extra_archives is None:
            extra_archives = []
        db_file = session.query(ArchiveFile).filter_by(file=source.poolfile).filter(ArchiveFile.archive_id.in_([ a.archive_id for a in extra_archives])).first()
        if db_file is None:
            raise ArchiveException('{0}: Built-Using refers to package {1} (= {2}) not in target archive {3}.'.format(filename, source.source, source.version, archive.archive_name))

        source_archive = db_file.archive
        for dsc_file in source.srcfiles:
            af = session.query(ArchiveFile).filter_by(file=dsc_file.poolfile, archive=source_archive, component=db_file.component).one()
            # We were given an explicit list of archives so it is okay to copy from tainted archives.
            self._copy_file(af.file, archive, db_file.component, allow_tainted=True)

    def _add_built_using(self, db_binary, filename, control, suite, extra_archives=None):
        """Add Built-Using sources to C{db_binary.extra_sources}
        """
        session = self.session
        built_using = control.get('Built-Using', None)

        if built_using is not None:
            for dep in apt_pkg.parse_depends(built_using):
                assert len(dep) == 1, 'Alternatives are not allowed in Built-Using field'
                bu_source_name, bu_source_version, comp = dep[0]
                assert comp == '=', 'Built-Using must contain strict dependencies'

                bu_source = session.query(DBSource).filter_by(source=bu_source_name, version=bu_source_version).first()
                if bu_source is None:
                    raise ArchiveException('{0}: Built-Using refers to non-existing source package {1} (= {2})'.format(filename, bu_source_name, bu_source_version))

                self._ensure_extra_source_exists(filename, bu_source, suite.archive, extra_archives=extra_archives)

                db_binary.extra_sources.append(bu_source)

    def install_source(self, directory, source, suite, component, changed_by, allow_tainted=False, fingerprint=None):
        """Install a source package

        @type  directory: str
        @param directory: directory the source package is located in

        @type  source: L{daklib.upload.Source}
        @param source: source package to install

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: target suite

        @type  component: L{daklib.dbconn.Component}
        @param component: target component

        @type  changed_by: L{daklib.dbconn.Maintainer}
        @param changed_by: person who prepared this version of the package

        @type  allow_tainted: bool
        @param allow_tainted: allow to copy additional files from tainted archives

        @type  fingerprint: L{daklib.dbconn.Fingerprint}
        @param fingerprint: optional fingerprint

        @rtype:  L{daklib.dbconn.DBSource}
        @return: database object for the new source
        """
        session = self.session
        archive = suite.archive
        control = source.dsc
        maintainer = get_or_set_maintainer(control['Maintainer'], session)
        source_name = control['Source']

        ### Add source package to database

        # We need to install the .dsc first as the DBSource object refers to it.
        db_file_dsc = self._install_file(directory, source._dsc_file, archive, component, source_name)

        unique = dict(
            source=source_name,
            version=control['Version'],
            )
        rest = dict(
            maintainer=maintainer,
            changedby=changed_by,
            #install_date=datetime.now().date(),
            poolfile=db_file_dsc,
            fingerprint=fingerprint,
            dm_upload_allowed=(control.get('DM-Upload-Allowed', 'no') == 'yes'),
            )

        created = False
        try:
            db_source = session.query(DBSource).filter_by(**unique).one()
            for key, value in rest.iteritems():
                if getattr(db_source, key) != value:
                    raise ArchiveException('{0}: Does not match source in database.'.format(source._dsc_file.filename))
        except NoResultFound:
            created = True
            db_source = DBSource(**unique)
            for key, value in rest.iteritems():
                setattr(db_source, key, value)
            # XXX: set as default in postgres?
            db_source.install_date = datetime.now().date()
            session.add(db_source)
            session.flush()

            # Add .dsc file. Other files will be added later.
            db_dsc_file = DSCFile()
            db_dsc_file.source = db_source
            db_dsc_file.poolfile = db_file_dsc
            session.add(db_dsc_file)
            session.flush()

        if suite in db_source.suites:
            return db_source

        db_source.suites.append(suite)

        if not created:
            for f in db_source.srcfiles:
                self._copy_file(f.poolfile, archive, component, allow_tainted=allow_tainted)
            return db_source

        ### Now add remaining files and copy them to the archive.

        for hashed_file in source.files.itervalues():
            hashed_file_path = os.path.join(directory, hashed_file.filename)
            if os.path.exists(hashed_file_path):
                db_file = self._install_file(directory, hashed_file, archive, component, source_name)
                session.add(db_file)
            else:
                db_file = self.get_file(hashed_file, source_name)
                self._copy_file(db_file, archive, component, allow_tainted=allow_tainted)

            db_dsc_file = DSCFile()
            db_dsc_file.source = db_source
            db_dsc_file.poolfile = db_file
            session.add(db_dsc_file)

        session.flush()

        # Importing is safe as we only arrive here when we did not find the source already installed earlier.
        import_metadata_into_db(db_source, session)

        # Uploaders are the maintainer and co-maintainers from the Uploaders field
        db_source.uploaders.append(maintainer)
        if 'Uploaders' in control:
            from daklib.textutils import split_uploaders
            for u in split_uploaders(control['Uploaders']):
                db_source.uploaders.append(get_or_set_maintainer(u, session))
        session.flush()

        return db_source

    def _copy_file(self, db_file, archive, component, allow_tainted=False):
        """Copy a file to the given archive and component

        @type  db_file: L{daklib.dbconn.PoolFile}
        @param db_file: file to copy

        @type  archive: L{daklib.dbconn.Archive}
        @param archive: target archive

        @type  component: L{daklib.dbconn.Archive}
        @param component: target component

        @type  allow_tainted: bool
        @param allow_tainted: allow to copy from tainted archives (such as NEW)
        """
        session = self.session

        if session.query(ArchiveFile).filter_by(archive=archive, component=component, file=db_file).first() is None:
            query = session.query(ArchiveFile).filter_by(file=db_file)
            if not allow_tainted:
                query = query.join(Archive).filter(Archive.tainted == False)

            source_af = query.first()
            if source_af is None:
                raise ArchiveException('cp: Could not find {0} in any archive.'.format(db_file.filename))
            target_af = ArchiveFile(archive, component, db_file)
            session.add(target_af)
            session.flush()
            self.fs.copy(source_af.path, target_af.path, link=False, mode=archive.mode)

    def copy_binary(self, db_binary, suite, component, allow_tainted=False, extra_archives=None):
        """Copy a binary package to the given suite and component

        @type  db_binary: L{daklib.dbconn.DBBinary}
        @param db_binary: binary to copy

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: target suite

        @type  component: L{daklib.dbconn.Component}
        @param component: target component

        @type  allow_tainted: bool
        @param allow_tainted: allow to copy from tainted archives (such as NEW)

        @type  extra_archives: list of L{daklib.dbconn.Archive}
        @param extra_archives: extra archives to copy Built-Using sources from
        """
        session = self.session
        archive = suite.archive
        if archive.tainted:
            allow_tainted = True

        filename = db_binary.poolfile.filename

        # make sure source is present in target archive
        db_source = db_binary.source
        if session.query(ArchiveFile).filter_by(archive=archive, file=db_source.poolfile).first() is None:
            raise ArchiveException('{0}: cannot copy to {1}: source is not present in target archive'.format(filename, suite.suite_name))

        # make sure built-using packages are present in target archive
        for db_source in db_binary.extra_sources:
            self._ensure_extra_source_exists(filename, db_source, archive, extra_archives=extra_archives)

        # copy binary
        db_file = db_binary.poolfile
        self._copy_file(db_file, suite.archive, component, allow_tainted=allow_tainted)
        if suite not in db_binary.suites:
            db_binary.suites.append(suite)
        self.session.flush()

    def copy_source(self, db_source, suite, component, allow_tainted=False):
        """Copy a source package to the given suite and component

        @type  db_source: L{daklib.dbconn.DBSource}
        @param db_source: source to copy

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: target suite

        @type  component: L{daklib.dbconn.Component}
        @param component: target component

        @type  allow_tainted: bool
        @param allow_tainted: allow to copy from tainted archives (such as NEW)
        """
        archive = suite.archive
        if archive.tainted:
            allow_tainted = True
        for db_dsc_file in db_source.srcfiles:
            self._copy_file(db_dsc_file.poolfile, archive, component, allow_tainted=allow_tainted)
        if suite not in db_source.suites:
            db_source.suites.append(suite)
        self.session.flush()

    def remove_file(self, db_file, archive, component):
        """Remove a file from a given archive and component

        @type  db_file: L{daklib.dbconn.PoolFile}
        @param db_file: file to remove

        @type  archive: L{daklib.dbconn.Archive}
        @param archive: archive to remove the file from

        @type  component: L{daklib.dbconn.Component}
        @param component: component to remove the file from
        """
        af = self.session.query(ArchiveFile).filter_by(file=db_file, archive=archive, component=component)
        self.fs.unlink(af.path)
        self.session.delete(af)

    def remove_binary(self, binary, suite):
        """Remove a binary from a given suite and component

        @type  binary: L{daklib.dbconn.DBBinary}
        @param binary: binary to remove

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: suite to remove the package from
        """
        binary.suites.remove(suite)
        self.session.flush()

    def remove_source(self, source, suite):
        """Remove a source from a given suite and component

        @type  source: L{daklib.dbconn.DBSource}
        @param source: source to remove

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: suite to remove the package from

        @raise ArchiveException: source package is still referenced by other
                                 binaries in the suite
        """
        session = self.session

        query = session.query(DBBinary).filter_by(source=source) \
            .filter(DBBinary.suites.contains(suite))
        if query.first() is not None:
            raise ArchiveException('src:{0} is still used by binaries in suite {1}'.format(source.source, suite.suite_name))

        source.suites.remove(suite)
        session.flush()

    def commit(self):
        """commit changes"""
        try:
            self.session.commit()
            self.fs.commit()
        finally:
            self.session.rollback()
            self.fs.rollback()

    def rollback(self):
        """rollback changes"""
        self.session.rollback()
        self.fs.rollback()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if type is None:
            self.commit()
        else:
            self.rollback()
        return None

class ArchiveUpload(object):
    """handle an upload

    This class can be used in a with-statement::

       with ArchiveUpload(...) as upload:
          ...

    Doing so will automatically run any required cleanup and also rollback the
    transaction if it was not committed.
    """
    def __init__(self, directory, changes, keyrings):
        self.transaction = ArchiveTransaction()
        """transaction used to handle the upload
        @type: L{daklib.archive.ArchiveTransaction}
        """

        self.session = self.transaction.session
        """database session"""

        self.original_directory = directory
        self.original_changes = changes

        self.changes = None
        """upload to process
        @type: L{daklib.upload.Changes}
        """

        self.directory = None
        """directory with temporary copy of files. set by C{prepare}
        @type: str
        """

        self.keyrings = keyrings

        self.fingerprint = self.session.query(Fingerprint).filter_by(fingerprint=changes.primary_fingerprint).one()
        """fingerprint of the key used to sign the upload
        @type: L{daklib.dbconn.Fingerprint}
        """

        self.reject_reasons = []
        """reasons why the upload cannot by accepted
        @type: list of str
        """

        self.warnings = []
        """warnings
        @note: Not used yet.
        @type: list of str
        """

        self.final_suites = None

        self.new = False
        """upload is NEW. set by C{check}
        @type: bool
        """

        self._checked = False
        """checks passes. set by C{check}
        @type: bool
        """

        self._new_queue = self.session.query(PolicyQueue).filter_by(queue_name='new').one()
        self._new = self._new_queue.suite

    def warn(self, message):
        """add a warning message

        Adds a warning message that can later be seen in C{self.warnings}

        @type  message: string
        @param message: warning message
        """
        self.warnings.append(message)

    def prepare(self):
        """prepare upload for further processing

        This copies the files involved to a temporary directory.  If you use
        this method directly, you have to remove the directory given by the
        C{directory} attribute later on your own.

        Instead of using the method directly, you can also use a with-statement::

           with ArchiveUpload(...) as upload:
              ...

        This will automatically handle any required cleanup.
        """
        assert self.directory is None
        assert self.original_changes.valid_signature

        cnf = Config()
        session = self.transaction.session

        group = cnf.get('Dinstall::UnprivGroup') or None
        self.directory = utils.temp_dirname(parent=cnf.get('Dir::TempPath'),
                                            mode=0o2750, group=group)
        with FilesystemTransaction() as fs:
            src = os.path.join(self.original_directory, self.original_changes.filename)
            dst = os.path.join(self.directory, self.original_changes.filename)
            fs.copy(src, dst, mode=0o640)

            self.changes = upload.Changes(self.directory, self.original_changes.filename, self.keyrings)

            for f in self.changes.files.itervalues():
                src = os.path.join(self.original_directory, f.filename)
                dst = os.path.join(self.directory, f.filename)
                if not os.path.exists(src):
                    continue
                fs.copy(src, dst, mode=0o640)

            source = None
            try:
                source = self.changes.source
            except Exception:
                # Do not raise an exception here if the .dsc is invalid.
                pass

            if source is not None:
                for f in source.files.itervalues():
                    src = os.path.join(self.original_directory, f.filename)
                    dst = os.path.join(self.directory, f.filename)
                    if not os.path.exists(dst):
                        try:
                            db_file = self.transaction.get_file(f, source.dsc['Source'], check_hashes=False)
                            db_archive_file = session.query(ArchiveFile).filter_by(file=db_file).first()
                            fs.copy(db_archive_file.path, dst, mode=0o640)
                        except KeyError:
                            # Ignore if get_file could not find it. Upload will
                            # probably be rejected later.
                            pass

    def unpacked_source(self):
        """Path to unpacked source

        Get path to the unpacked source. This method does unpack the source
        into a temporary directory under C{self.directory} if it has not
        been done so already.

        @rtype:  str or C{None}
        @return: string giving the path to the unpacked source directory
                 or C{None} if no source was included in the upload.
        """
        assert self.directory is not None

        source = self.changes.source
        if source is None:
            return None
        dsc_path = os.path.join(self.directory, source._dsc_file.filename)

        sourcedir = os.path.join(self.directory, 'source')
        if not os.path.exists(sourcedir):
            devnull = open('/dev/null', 'w')
            daklib.daksubprocess.check_call(["dpkg-source", "--no-copy", "--no-check", "-x", dsc_path, sourcedir], shell=False, stdout=devnull)
        if not os.path.isdir(sourcedir):
            raise Exception("{0} is not a directory after extracting source package".format(sourcedir))
        return sourcedir

    def _map_suite(self, suite_name):
        for rule in Config().value_list("SuiteMappings"):
            fields = rule.split()
            rtype = fields[0]
            if rtype == "map" or rtype == "silent-map":
                (src, dst) = fields[1:3]
                if src == suite_name:
                    suite_name = dst
                    if rtype != "silent-map":
                        self.warnings.append('Mapping {0} to {1}.'.format(src, dst))
            elif rtype == "ignore":
                ignored = fields[1]
                if suite_name == ignored:
                    self.warnings.append('Ignoring target suite {0}.'.format(ignored))
                    suite_name = None
            elif rtype == "reject":
                rejected = fields[1]
                if suite_name == rejected:
                    raise checks.Reject('Uploads to {0} are not accepted.'.format(rejected))
            ## XXX: propup-version and map-unreleased not yet implemented
        return suite_name

    def _mapped_suites(self):
        """Get target suites after mappings

        @rtype:  list of L{daklib.dbconn.Suite}
        @return: list giving the mapped target suites of this upload
        """
        session = self.session

        suite_names = []
        for dist in self.changes.distributions:
            suite_name = self._map_suite(dist)
            if suite_name is not None:
                suite_names.append(suite_name)

        suites = session.query(Suite).filter(Suite.suite_name.in_(suite_names))
        return suites

    def _check_new(self, suite):
        """Check if upload is NEW

        An upload is NEW if it has binary or source packages that do not have
        an override in C{suite} OR if it references files ONLY in a tainted
        archive (eg. when it references files in NEW).

        @rtype:  bool
        @return: C{True} if the upload is NEW, C{False} otherwise
        """
        session = self.session
        new = False

        # Check for missing overrides
        for b in self.changes.binaries:
            override = self._binary_override(suite, b)
            if override is None:
                self.warnings.append('binary:{0} is NEW.'.format(b.control['Package']))
                new = True

        if self.changes.source is not None:
            override = self._source_override(suite, self.changes.source)
            if override is None:
                self.warnings.append('source:{0} is NEW.'.format(self.changes.source.dsc['Source']))
                new = True

        # Check if we reference a file only in a tainted archive
        files = self.changes.files.values()
        if self.changes.source is not None:
            files.extend(self.changes.source.files.values())
        for f in files:
            query = session.query(ArchiveFile).join(PoolFile).filter(PoolFile.sha1sum == f.sha1sum)
            query_untainted = query.join(Archive).filter(Archive.tainted == False)

            in_archive = (query.first() is not None)
            in_untainted_archive = (query_untainted.first() is not None)

            if in_archive and not in_untainted_archive:
                self.warnings.append('{0} is only available in NEW.'.format(f.filename))
                new = True

        return new

    def _final_suites(self):
        session = self.session

        mapped_suites = self._mapped_suites()
        final_suites = set()

        for suite in mapped_suites:
            overridesuite = suite
            if suite.overridesuite is not None:
                overridesuite = session.query(Suite).filter_by(suite_name=suite.overridesuite).one()
            if self._check_new(overridesuite):
                self.new = True
            final_suites.add(suite)

        return final_suites

    def _binary_override(self, suite, binary):
        """Get override entry for a binary

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: suite to get override for

        @type  binary: L{daklib.upload.Binary}
        @param binary: binary to get override for

        @rtype:  L{daklib.dbconn.Override} or C{None}
        @return: override for the given binary or C{None}
        """
        if suite.overridesuite is not None:
            suite = self.session.query(Suite).filter_by(suite_name=suite.overridesuite).one()

        mapped_component = get_mapped_component(binary.component)
        if mapped_component is None:
            return None

        query = self.session.query(Override).filter_by(suite=suite, package=binary.control['Package']) \
                .join(Component).filter(Component.component_name == mapped_component.component_name) \
                .join(OverrideType).filter(OverrideType.overridetype == binary.type)

        try:
            return query.one()
        except NoResultFound:
            return None

    def _source_override(self, suite, source):
        """Get override entry for a source

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: suite to get override for

        @type  source: L{daklib.upload.Source}
        @param source: source to get override for

        @rtype:  L{daklib.dbconn.Override} or C{None}
        @return: override for the given source or C{None}
        """
        if suite.overridesuite is not None:
            suite = self.session.query(Suite).filter_by(suite_name=suite.overridesuite).one()

        # XXX: component for source?
        query = self.session.query(Override).filter_by(suite=suite, package=source.dsc['Source']) \
                .join(OverrideType).filter(OverrideType.overridetype == 'dsc')

        try:
            return query.one()
        except NoResultFound:
            return None

    def _binary_component(self, suite, binary, only_overrides=True):
        """get component for a binary

        By default this will only look at overrides to get the right component;
        if C{only_overrides} is C{False} this method will also look at the
        Section field.

        @type  suite: L{daklib.dbconn.Suite}

        @type  binary: L{daklib.upload.Binary}

        @type  only_overrides: bool
        @param only_overrides: only use overrides to get the right component

        @rtype: L{daklib.dbconn.Component} or C{None}
        """
        override = self._binary_override(suite, binary)
        if override is not None:
            return override.component
        if only_overrides:
            return None
        return get_mapped_component(binary.component, self.session)

    def check(self, force=False):
        """run checks against the upload

        @type  force: bool
        @param force: ignore failing forcable checks

        @rtype:  bool
        @return: C{True} if all checks passed, C{False} otherwise
        """
        # XXX: needs to be better structured.
        assert self.changes.valid_signature

        try:
            # Validate signatures and hashes before we do any real work:
            for chk in (
                    checks.SignatureAndHashesCheck,
                    checks.ChangesCheck,
                    checks.ExternalHashesCheck,
                    checks.SourceCheck,
                    checks.BinaryCheck,
                    checks.BinaryTimestampCheck,
                    checks.SingleDistributionCheck,
                    ):
                chk().check(self)

            final_suites = self._final_suites()
            if len(final_suites) == 0:
                self.reject_reasons.append('No target suite found. Please check your target distribution and that you uploaded to the right archive.')
                return False

            self.final_suites = final_suites

            for chk in (
                    checks.TransitionCheck,
                    checks.ACLCheck,
                    checks.NoSourceOnlyCheck,
                    checks.LintianCheck,
                    ):
                chk().check(self)

            for chk in (
                    checks.ACLCheck,
                    checks.SourceFormatCheck,
                    checks.SuiteArchitectureCheck,
                    checks.VersionCheck,
                    ):
                for suite in final_suites:
                    chk().per_suite_check(self, suite)

            if len(self.reject_reasons) != 0:
                return False

            self._checked = True
            return True
        except checks.Reject as e:
            self.reject_reasons.append(unicode(e))
        except Exception as e:
            self.reject_reasons.append("Processing raised an exception: {0}.\n{1}".format(e, traceback.format_exc()))
        return False

    def _install_to_suite(self, suite, source_component_func, binary_component_func, source_suites=None, extra_source_archives=None):
        """Install upload to the given suite

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: suite to install the package into. This is the real suite,
                      ie. after any redirection to NEW or a policy queue

        @param source_component_func: function to get the L{daklib.dbconn.Component}
                                      for a L{daklib.upload.Source} object

        @param binary_component_func: function to get the L{daklib.dbconn.Component}
                                      for a L{daklib.upload.Binary} object

        @param source_suites: see L{daklib.archive.ArchiveTransaction.install_binary}

        @param extra_source_archives: see L{daklib.archive.ArchiveTransaction.install_binary}

        @return: tuple with two elements. The first is a L{daklib.dbconn.DBSource}
                 object for the install source or C{None} if no source was
                 included. The second is a list of L{daklib.dbconn.DBBinary}
                 objects for the installed binary packages.
        """
        # XXX: move this function to ArchiveTransaction?

        control = self.changes.changes
        changed_by = get_or_set_maintainer(control.get('Changed-By', control['Maintainer']), self.session)

        if source_suites is None:
            source_suites = self.session.query(Suite).join((VersionCheck, VersionCheck.reference_id == Suite.suite_id)).filter(VersionCheck.check == 'Enhances').filter(VersionCheck.suite == suite).subquery()

        source = self.changes.source
        if source is not None:
            component = source_component_func(source)
            db_source = self.transaction.install_source(self.directory, source, suite, component, changed_by, fingerprint=self.fingerprint)
        else:
            db_source = None

        db_binaries = []
        for binary in self.changes.binaries:
            component = binary_component_func(binary)
            db_binary = self.transaction.install_binary(self.directory, binary, suite, component, fingerprint=self.fingerprint, source_suites=source_suites, extra_source_archives=extra_source_archives)
            db_binaries.append(db_binary)

        if suite.copychanges:
            src = os.path.join(self.directory, self.changes.filename)
            dst = os.path.join(suite.archive.path, 'dists', suite.suite_name, self.changes.filename)
            self.transaction.fs.copy(src, dst, mode=suite.archive.mode)

        return (db_source, db_binaries)

    def _install_changes(self):
        assert self.changes.valid_signature
        control = self.changes.changes
        session = self.transaction.session
        config = Config()

        changelog_id = None
        # Only add changelog for sourceful uploads and binNMUs
        if 'source' in self.changes.architectures or re_bin_only_nmu.search(control['Version']):
            query = 'INSERT INTO changelogs_text (changelog) VALUES (:changelog) RETURNING id'
            changelog_id = session.execute(query, {'changelog': control['Changes']}).scalar()
            assert changelog_id is not None

        db_changes = DBChange()
        db_changes.changesname = self.changes.filename
        db_changes.source = control['Source']
        db_changes.binaries = control.get('Binary', None)
        db_changes.architecture = control['Architecture']
        db_changes.version = control['Version']
        db_changes.distribution = control['Distribution']
        db_changes.urgency = control['Urgency']
        db_changes.maintainer = control['Maintainer']
        db_changes.changedby = control.get('Changed-By', control['Maintainer'])
        db_changes.date = control['Date']
        db_changes.fingerprint = self.fingerprint.fingerprint
        db_changes.changelog_id = changelog_id
        db_changes.closes = self.changes.closed_bugs

        try:
            self.transaction.session.add(db_changes)
            self.transaction.session.flush()
        except sqlalchemy.exc.IntegrityError:
            raise ArchiveException('{0} is already known.'.format(self.changes.filename))

        return db_changes

    def _install_policy(self, policy_queue, target_suite, db_changes, db_source, db_binaries):
        u = PolicyQueueUpload()
        u.policy_queue = policy_queue
        u.target_suite = target_suite
        u.changes = db_changes
        u.source = db_source
        u.binaries = db_binaries
        self.transaction.session.add(u)
        self.transaction.session.flush()

        dst = os.path.join(policy_queue.path, self.changes.filename)
        self.transaction.fs.copy(self.changes.path, dst, mode=policy_queue.change_perms)

        return u

    def try_autobyhand(self):
        """Try AUTOBYHAND

        Try to handle byhand packages automatically.

        @rtype:  list of L{daklib.upload.HashedFile}
        @return: list of remaining byhand files
        """
        assert len(self.reject_reasons) == 0
        assert self.changes.valid_signature
        assert self.final_suites is not None
        assert self._checked

        byhand = self.changes.byhand_files
        if len(byhand) == 0:
            return True

        suites = list(self.final_suites)
        assert len(suites) == 1, "BYHAND uploads must be to a single suite"
        suite = suites[0]

        cnf = Config()
        control = self.changes.changes
        automatic_byhand_packages = cnf.subtree("AutomaticByHandPackages")

        remaining = []
        for f in byhand:
            if '_' in f.filename:
                parts = f.filename.split('_', 2)
                if len(parts) != 3:
                    print "W: unexpected byhand filename {0}. No automatic processing.".format(f.filename)
                    remaining.append(f)
                    continue

                package, version, archext = parts
                arch, ext = archext.split('.', 1)
            else:
                parts = f.filename.split('.')
                if len(parts) < 2:
                    print "W: unexpected byhand filename {0}. No automatic processing.".format(f.filename)
                    remaining.append(f)
                    continue

                package = parts[0]
                version = '0'
                arch = 'all'
                ext = parts[-1]

            try:
                rule = automatic_byhand_packages.subtree(package)
            except KeyError:
                remaining.append(f)
                continue

            if rule['Source'] != self.changes.source_name \
                    or rule['Section'] != f.section \
                    or ('Extension' in rule and rule['Extension'] != ext):
                remaining.append(f)
                continue

            script = rule['Script']
            retcode = daklib.daksubprocess.call([script, os.path.join(self.directory, f.filename), control['Version'], arch, os.path.join(self.directory, self.changes.filename)], shell=False)
            if retcode != 0:
                print "W: error processing {0}.".format(f.filename)
                remaining.append(f)

        return len(remaining) == 0

    def _install_byhand(self, policy_queue_upload, hashed_file):
        """install byhand file

        @type  policy_queue_upload: L{daklib.dbconn.PolicyQueueUpload}

        @type  hashed_file: L{daklib.upload.HashedFile}
        """
        fs = self.transaction.fs
        session = self.transaction.session
        policy_queue = policy_queue_upload.policy_queue

        byhand_file = PolicyQueueByhandFile()
        byhand_file.upload = policy_queue_upload
        byhand_file.filename = hashed_file.filename
        session.add(byhand_file)
        session.flush()

        src = os.path.join(self.directory, hashed_file.filename)
        dst = os.path.join(policy_queue.path, hashed_file.filename)
        fs.copy(src, dst, mode=policy_queue.change_perms)

        return byhand_file

    def _do_bts_versiontracking(self):
        cnf = Config()
        fs = self.transaction.fs

        btsdir = cnf.get('Dir::BTSVersionTrack')
        if btsdir is None or btsdir == '':
            return

        base = os.path.join(btsdir, self.changes.filename[:-8])

        # version history
        sourcedir = self.unpacked_source()
        if sourcedir is not None:
            fh = open(os.path.join(sourcedir, 'debian', 'changelog'), 'r')
            versions = fs.create("{0}.versions".format(base), mode=0o644)
            for line in fh.readlines():
                if re_changelog_versions.match(line):
                    versions.write(line)
            fh.close()
            versions.close()

        # binary -> source mapping
        debinfo = fs.create("{0}.debinfo".format(base), mode=0o644)
        for binary in self.changes.binaries:
            control = binary.control
            source_package, source_version = binary.source
            line = " ".join([control['Package'], control['Version'], control['Architecture'], source_package, source_version])
            print >>debinfo, line
        debinfo.close()

    def _policy_queue(self, suite):
        if suite.policy_queue is not None:
            return suite.policy_queue
        return None

    def install(self):
        """install upload

        Install upload to a suite or policy queue.  This method does B{not}
        handle uploads to NEW.

        You need to have called the C{check} method before calling this method.
        """
        assert len(self.reject_reasons) == 0
        assert self.changes.valid_signature
        assert self.final_suites is not None
        assert self._checked
        assert not self.new

        db_changes = self._install_changes()

        for suite in self.final_suites:
            overridesuite = suite
            if suite.overridesuite is not None:
                overridesuite = self.session.query(Suite).filter_by(suite_name=suite.overridesuite).one()

            policy_queue = self._policy_queue(suite)

            redirected_suite = suite
            if policy_queue is not None:
                redirected_suite = policy_queue.suite

            # source can be in the suite we install to or any suite we enhance
            source_suite_ids = set([suite.suite_id, redirected_suite.suite_id])
            for enhanced_suite_id, in self.session.query(VersionCheck.reference_id) \
                    .filter(VersionCheck.suite_id.in_(source_suite_ids)) \
                    .filter(VersionCheck.check == 'Enhances'):
                source_suite_ids.add(enhanced_suite_id)

            source_suites = self.session.query(Suite).filter(Suite.suite_id.in_(source_suite_ids)).subquery()

            source_component_func = lambda source: self._source_override(overridesuite, source).component
            binary_component_func = lambda binary: self._binary_component(overridesuite, binary)

            (db_source, db_binaries) = self._install_to_suite(redirected_suite, source_component_func, binary_component_func, source_suites=source_suites, extra_source_archives=[suite.archive])

            if policy_queue is not None:
                self._install_policy(policy_queue, suite, db_changes, db_source, db_binaries)

            # copy to build queues
            if policy_queue is None or policy_queue.send_to_build_queues:
                for build_queue in suite.copy_queues:
                    self._install_to_suite(build_queue.suite, source_component_func, binary_component_func, source_suites=source_suites, extra_source_archives=[suite.archive])

        self._do_bts_versiontracking()

    def install_to_new(self):
        """install upload to NEW

        Install upload to NEW.  This method does B{not} handle regular uploads
        to suites or policy queues.

        You need to have called the C{check} method before calling this method.
        """
        # Uploads to NEW are special as we don't have overrides.
        assert len(self.reject_reasons) == 0
        assert self.changes.valid_signature
        assert self.final_suites is not None

        source = self.changes.source
        binaries = self.changes.binaries
        byhand = self.changes.byhand_files

        # we need a suite to guess components
        suites = list(self.final_suites)
        assert len(suites) == 1, "NEW uploads must be to a single suite"
        suite = suites[0]

        # decide which NEW queue to use
        if suite.new_queue is None:
            new_queue = self.transaction.session.query(PolicyQueue).filter_by(queue_name='new').one()
        else:
            new_queue = suite.new_queue
        if len(byhand) > 0:
            # There is only one global BYHAND queue
            new_queue = self.transaction.session.query(PolicyQueue).filter_by(queue_name='byhand').one()
        new_suite = new_queue.suite


        def binary_component_func(binary):
            return self._binary_component(suite, binary, only_overrides=False)

        # guess source component
        # XXX: should be moved into an extra method
        binary_component_names = set()
        for binary in binaries:
            component = binary_component_func(binary)
            binary_component_names.add(component.component_name)
        source_component_name = None
        for c in self.session.query(Component).order_by(Component.component_id):
            guess = c.component_name
            if guess in binary_component_names:
                source_component_name = guess
                break
        if source_component_name is None:
            source_component = self.session.query(Component).order_by(Component.component_id).first()
        else:
            source_component = self.session.query(Component).filter_by(component_name=source_component_name).one()
        source_component_func = lambda source: source_component

        db_changes = self._install_changes()
        (db_source, db_binaries) = self._install_to_suite(new_suite, source_component_func, binary_component_func, source_suites=True, extra_source_archives=[suite.archive])
        policy_upload = self._install_policy(new_queue, suite, db_changes, db_source, db_binaries)

        for f in byhand:
            self._install_byhand(policy_upload, f)

        self._do_bts_versiontracking()

    def commit(self):
        """commit changes"""
        self.transaction.commit()

    def rollback(self):
        """rollback changes"""
        self.transaction.rollback()

    def __enter__(self):
        self.prepare()
        return self

    def __exit__(self, type, value, traceback):
        if self.directory is not None:
            shutil.rmtree(self.directory)
            self.directory = None
        self.changes = None
        self.transaction.rollback()
        return None
