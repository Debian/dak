#!/usr/bin/python

""" DB access class

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
@copyright: 2008-2009  Mark Hymers <mhy@debian.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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

################################################################################

# < mhy> I need a funny comment
# < sgran> two peanuts were walking down a dark street
# < sgran> one was a-salted
#  * mhy looks up the definition of "funny"

################################################################################

import os
import psycopg2
import traceback

from sqlalchemy import create_engine, Table, MetaData, select
from sqlalchemy.orm import sessionmaker, mapper, relation

# Don't remove this, we re-export the exceptions to scripts which import us
from sqlalchemy.exc import *

from singleton import Singleton

################################################################################

__all__ = []

################################################################################

class Architecture(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Architecture %s>' % self.arch_string

__all__.append('Architecture')

def get_architecture(architecture, session=None):
    """
    Returns database id for given C{architecture}.

    @type architecture: string
    @param architecture: The name of the architecture

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Architecture
    @return: Architecture object for the given arch (None if not present)

    """
    if session is None:
        session = DBConn().session()
    q = session.query(Architecture).filter_by(arch_string=architecture)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_architecture')

def get_architecture_suites(architecture, session=None):
    """
    Returns list of Suite objects for given C{architecture} name

    @type source: str
    @param source: Architecture name to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of Suite objects for the given name (may be empty)
    """

    if session is None:
        session = DBConn().session()

    q = session.query(Suite)
    q = q.join(SuiteArchitecture)
    q = q.join(Architecture).filter_by(arch_string=architecture).order_by('suite_name')
    return q.all()

__all__.append('get_architecture_suites')

################################################################################

class Archive(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Archive %s>' % self.name

__all__.append('Archive')

def get_archive(archive, session=None):
    """
    returns database id for given c{archive}.

    @type archive: string
    @param archive: the name of the arhive

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Archive
    @return: Archive object for the given name (None if not present)

    """
    archive = archive.lower()
    if session is None:
        session = DBConn().session()
    q = session.query(Archive).filter_by(archive_name=archive)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_archive')

################################################################################

class BinAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BinAssociation %s (%s, %s)>' % (self.ba_id, self.binary, self.suite)

__all__.append('BinAssociation')

################################################################################

class DBBinary(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBBinary %s (%s, %s)>' % (self.package, self.version, self.architecture)

__all__.append('DBBinary')

def get_binary_from_id(id, session=None):
    """
    Returns DBBinary object for given C{id}

    @type id: int
    @param id: Id of the required binary

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: DBBinary
    @return: DBBinary object for the given binary (None if not present)
    """
    if session is None:
        session = DBConn().session()
    q = session.query(DBBinary).filter_by(binary_id=id)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_binary_from_id')

def get_binaries_from_name(package, session=None):
    """
    Returns list of DBBinary objects for given C{package} name

    @type package: str
    @param package: DBBinary package name to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of DBBinary objects for the given name (may be empty)
    """
    if session is None:
        session = DBConn().session()
    return session.query(DBBinary).filter_by(package=package).all()

__all__.append('get_binaries_from_name')

################################################################################

class Component(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Component %s>' % self.component_name


__all__.append('Component')

def get_component(component, session=None):
    """
    Returns database id for given C{component}.

    @type component: string
    @param component: The name of the override type

    @rtype: int
    @return: the database id for the given component

    """
    component = component.lower()
    if session is None:
        session = DBConn().session()
    q = session.query(Component).filter_by(component_name=component)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_component')

################################################################################

class DBConfig(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBConfig %s>' % self.name

__all__.append('DBConfig')

################################################################################

class ContentFilename(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ContentFilename %s>' % self.filename

__all__.append('ContentFilename')

def get_or_set_contents_file_id(filename, session=None):
    """
    Returns database id for given filename.

    If no matching file is found, a row is inserted.

    @type filename: string
    @param filename: The filename
    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: int
    @return: the database id for the given component
    """
    if session is None:
        session = DBConn().session()

    try:
        q = session.query(ContentFilename).filter_by(filename=filename)
        if q.count() < 1:
            cf = ContentFilename()
            cf.filename = filename
            session.add(cf)
            return cf.cafilename_id
        else:
            return q.one().cafilename_id

    except:
        traceback.print_exc()
        raise

__all__.append('get_or_set_contents_file_id')

################################################################################

class ContentFilepath(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ContentFilepath %s>' % self.filepath

__all__.append('ContentFilepath')

def get_or_set_contents_path_id(filepath, session):
    """
    Returns database id for given path.

    If no matching file is found, a row is inserted.

    @type filename: string
    @param filename: The filepath
    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: int
    @return: the database id for the given path
    """
    if session is None:
        session = DBConn().session()

    try:
        q = session.query(ContentFilepath).filter_by(filepath=filepath)
        if q.count() < 1:
            cf = ContentFilepath()
            cf.filepath = filepath
            session.add(cf)
            return cf.cafilepath_id
        else:
            return q.one().cafilepath_id

    except:
        traceback.print_exc()
        raise

__all__.append('get_or_set_contents_path_id')

################################################################################

class ContentAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ContentAssociation %s>' % self.ca_id

__all__.append('ContentAssociation')

def insert_content_paths(binary_id, fullpaths, session=None):
    """
    Make sure given path is associated with given binary id

    @type binary_id: int
    @param binary_id: the id of the binary
    @type fullpaths: list
    @param fullpaths: the list of paths of the file being associated with the binary
    @type session: SQLAlchemy session
    @param session: Optional SQLAlchemy session.  If this is passed, the caller
    is responsible for ensuring a transaction has begun and committing the
    results or rolling back based on the result code.  If not passed, a commit
    will be performed at the end of the function

    @return: True upon success
    """

    privatetrans = False

    if session is None:
        session = DBConn().session()
        privatetrans = True

    try:
        for fullpath in fullpaths:
            (path, file) = os.path.split(fullpath)

            # Get the necessary IDs ...
            ca = ContentAssociation()
            ca.binary_id = binary_id
            ca.filename_id = get_or_set_contents_file_id(file)
            ca.filepath_id = get_or_set_contents_path_id(path)
            session.add(ca)

        # Only commit if we set up the session ourself
        if privatetrans:
            session.commit()

        return True
    except:
        traceback.print_exc()

        # Only rollback if we set up the session ourself
        if privatetrans:
            session.rollback()

        return False

__all__.append('insert_content_paths')

################################################################################

class DSCFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DSCFile %s>' % self.dscfile_id

__all__.append('DSCFile')

################################################################################

class PoolFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<PoolFile %s>' % self.filename

__all__.append('PoolFile')

def get_poolfile_by_name(filename, location_id=None, session=None):
    """
    Returns an array of PoolFile objects for the given filename and
    (optionally) location_id

    @type filename: string
    @param filename: the filename of the file to check against the DB

    @type location_id: int
    @param location_id: the id of the location to look in (optional)

    @rtype: array
    @return: array of PoolFile objects
    """

    if session is not None:
        session = DBConn().session()

    q = session.query(PoolFile).filter_by(filename=filename)

    if location_id is not None:
        q = q.join(Location).filter_by(location_id=location_id)

    return q.all()

__all__.append('get_poolfile_by_name')

################################################################################

class Fingerprint(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Fingerprint %s>' % self.fingerprint

__all__.append('Fingerprint')

################################################################################

class Keyring(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Keyring %s>' % self.keyring_name

__all__.append('Keyring')

################################################################################

class Location(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Location %s (%s)>' % (self.path, self.location_id)

__all__.append('Location')

def get_location(location, component=None, archive=None, session=None):
    """
    Returns Location object for the given combination of location, component
    and archive

    @type location: string
    @param location: the path of the location, e.g. I{/srv/ftp.debian.org/ftp/pool/}

    @type component: string
    @param component: the component name (if None, no restriction applied)

    @type archive: string
    @param archive_id: the archive name (if None, no restriction applied)

    @rtype: Location / None
    @return: Either a Location object or None if one can't be found
    """

    if session is None:
        session = DBConn().session()

    q = session.query(Location).filter_by(path=location)

    if archive is not None:
        q = q.join(Archive).filter_by(archive_name=archive)

    if component is not None:
        q = q.join(Component).filter_by(component_name=component)

    if q.count() < 1:
        return None
    else:
        return q.one()

__all__.append('get_location')

################################################################################

class Maintainer(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '''<Maintainer '%s' (%s)>''' % (self.name, self.maintainer_id)

__all__.append('Maintainer')

################################################################################

class Override(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Override %s (%s)>' % (self.package, self.suite_id)

__all__.append('Override')

################################################################################

class OverrideType(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<OverrideType %s>' % self.overridetype

__all__.append('OverrideType')

def get_override_type(override_type, session=None):
    """
    Returns OverrideType object for given C{override type}.

    @type override_type: string
    @param override_type: The name of the override type

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: int
    @return: the database id for the given override type

    """
    if session is None:
        session = DBConn().session()
    q = session.query(Priority).filter_by(priority=priority)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_override_type')

################################################################################

class PendingContentAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<PendingContentAssociation %s>' % self.pca_id

__all__.append('PendingContentAssociation')

def insert_pending_content_paths(package, fullpaths, session=None):
    """
    Make sure given paths are temporarily associated with given
    package

    @type package: dict
    @param package: the package to associate with should have been read in from the binary control file
    @type fullpaths: list
    @param fullpaths: the list of paths of the file being associated with the binary
    @type session: SQLAlchemy session
    @param session: Optional SQLAlchemy session.  If this is passed, the caller
    is responsible for ensuring a transaction has begun and committing the
    results or rolling back based on the result code.  If not passed, a commit
    will be performed at the end of the function

    @return: True upon success, False if there is a problem
    """

    privatetrans = False

    if session is None:
        session = DBConn().session()
        privatetrans = True

    try:
        arch = get_architecture(package['Architecture'], session)
        arch_id = arch.arch_id

        # Remove any already existing recorded files for this package
        q = session.query(PendingContentAssociation)
        q = q.filter_by(package=package['Package'])
        q = q.filter_by(version=package['Version'])
        q = q.filter_by(architecture=arch_id)
        q.delete()

        # Insert paths
        for fullpath in fullpaths:
            (path, file) = os.path.split(fullpath)

            if path.startswith( "./" ):
                path = path[2:]

            pca = PendingContentAssociation()
            pca.package = package['Package']
            pca.version = package['Version']
            pca.filename_id = get_or_set_contents_file_id(file, session)
            pca.filepath_id = get_or_set_contents_path_id(path, session)
            pca.architecture = arch_id
            session.add(pca)

        # Only commit if we set up the session ourself
        if privatetrans:
            session.commit()

        return True
    except:
        traceback.print_exc()

        # Only rollback if we set up the session ourself
        if privatetrans:
            session.rollback()

        return False

__all__.append('insert_pending_content_paths')

################################################################################

class Priority(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Priority %s (%s)>' % (self.priority, self.priority_id)

__all__.append('Priority')

def get_priority(priority, session=None):
    """
    Returns Priority object for given C{priority name}.

    @type priority: string
    @param priority: The name of the priority

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Priority
    @return: Priority object for the given priority

    """
    if session is None:
        session = DBConn().session()
    q = session.query(Priority).filter_by(priority=priority)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_priority')

################################################################################

class Queue(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Queue %s>' % self.queue_name

__all__.append('Queue')

################################################################################

class QueueBuild(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<QueueBuild %s (%s)>' % (self.filename, self.queue_id)

__all__.append('QueueBuild')

################################################################################

class Section(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Section %s>' % self.section

__all__.append('Section')

def get_section(section, session=None):
    """
    Returns Section object for given C{section name}.

    @type section: string
    @param section: The name of the section

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Section
    @return: Section object for the given section name

    """
    if session is None:
        session = DBConn().session()
    q = session.query(Section).filter_by(section=section)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_section')

################################################################################

class DBSource(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBSource %s (%s)>' % (self.source, self.version)

__all__.append('DBSource')

def get_sources_from_name(source, session=None):
    """
    Returns list of DBSource objects for given C{source} name

    @type source: str
    @param source: DBSource package name to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of DBSource objects for the given name (may be empty)
    """
    if session is None:
        session = DBConn().session()
    return session.query(DBSource).filter_by(source=source).all()

__all__.append('get_sources_from_name')

def get_source_in_suite(source, suite, session=None):
    """
    Returns list of DBSource objects for a combination of C{source} and C{suite}.

      - B{source} - source package name, eg. I{mailfilter}, I{bbdb}, I{glibc}
      - B{suite} - a suite name, eg. I{unstable}

    @type source: string
    @param source: source package name

    @type suite: string
    @param suite: the suite name

    @rtype: string
    @return: the version for I{source} in I{suite}

    """
    if session is None:
        session = DBConn().session()
    q = session.query(SrcAssociation)
    q = q.join('source').filter_by(source=source)
    q = q.join('suite').filter_by(suite_name=suite)
    if q.count() == 0:
        return None
    # ???: Maybe we should just return the SrcAssociation object instead
    return q.one().source

__all__.append('get_source_in_suite')

################################################################################

class SrcAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcAssociation %s (%s, %s)>' % (self.sa_id, self.source, self.suite)

__all__.append('SrcAssociation')

################################################################################

class SrcUploader(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcUploader %s>' % self.uploader_id

__all__.append('SrcUploader')

################################################################################

class Suite(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Suite %s>' % self.suite_name

__all__.append('Suite')

def get_suite_architecture(suite, architecture, session=None):
    """
    Returns a SuiteArchitecture object given C{suite} and ${arch} or None if it
    doesn't exist

    @type suite: str
    @param suite: Suite name to search for

    @type architecture: str
    @param architecture: Architecture name to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: SuiteArchitecture
    @return: the SuiteArchitecture object or None
    """

    if session is None:
        session = DBConn().session()

    q = session.query(SuiteArchitecture)
    q = q.join(Architecture).filter_by(arch_string=architecture)
    q = q.join(Suite).filter_by(suite_name=suite)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_suite_architecture')

def get_suite(suite, session=None):
    """
    Returns Suite object for given C{suite name}.

    @type suite: string
    @param suite: The name of the suite

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Suite
    @return: Suite object for the requested suite name (None if not presenT)

    """
    if session is None:
        session = DBConn().session()
    q = session.query(Suite).filter_by(suite_name=suite)
    if q.count() == 0:
        return None
    return q.one()

__all__.append('get_suite')

################################################################################

class SuiteArchitecture(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SuiteArchitecture (%s, %s)>' % (self.suite_id, self.arch_id)

__all__.append('SuiteArchitecture')

def get_suite_architectures(suite, session=None):
    """
    Returns list of Architecture objects for given C{suite} name

    @type source: str
    @param source: Suite name to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of Architecture objects for the given name (may be empty)
    """

    if session is None:
        session = DBConn().session()

    q = session.query(Architecture)
    q = q.join(SuiteArchitecture)
    q = q.join(Suite).filter_by(suite_name=suite).order_by('arch_string')
    return q.all()

__all__.append('get_suite_architectures')

################################################################################

class Uid(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Uid %s (%s)>' % (self.uid, self.name)

__all__.append('Uid')

################################################################################

class DBConn(Singleton):
    """
    database module init.
    """
    def __init__(self, *args, **kwargs):
        super(DBConn, self).__init__(*args, **kwargs)

    def _startup(self, *args, **kwargs):
        self.debug = False
        if kwargs.has_key('debug'):
            self.debug = True
        self.__createconn()

    def __setuptables(self):
        self.tbl_architecture = Table('architecture', self.db_meta, autoload=True)
        self.tbl_archive = Table('archive', self.db_meta, autoload=True)
        self.tbl_bin_associations = Table('bin_associations', self.db_meta, autoload=True)
        self.tbl_binaries = Table('binaries', self.db_meta, autoload=True)
        self.tbl_component = Table('component', self.db_meta, autoload=True)
        self.tbl_config = Table('config', self.db_meta, autoload=True)
        self.tbl_content_associations = Table('content_associations', self.db_meta, autoload=True)
        self.tbl_content_file_names = Table('content_file_names', self.db_meta, autoload=True)
        self.tbl_content_file_paths = Table('content_file_paths', self.db_meta, autoload=True)
        self.tbl_dsc_files = Table('dsc_files', self.db_meta, autoload=True)
        self.tbl_files = Table('files', self.db_meta, autoload=True)
        self.tbl_fingerprint = Table('fingerprint', self.db_meta, autoload=True)
        self.tbl_keyrings = Table('keyrings', self.db_meta, autoload=True)
        self.tbl_location = Table('location', self.db_meta, autoload=True)
        self.tbl_maintainer = Table('maintainer', self.db_meta, autoload=True)
        self.tbl_override = Table('override', self.db_meta, autoload=True)
        self.tbl_override_type = Table('override_type', self.db_meta, autoload=True)
        self.tbl_pending_content_associations = Table('pending_content_associations', self.db_meta, autoload=True)
        self.tbl_priority = Table('priority', self.db_meta, autoload=True)
        self.tbl_queue = Table('queue', self.db_meta, autoload=True)
        self.tbl_queue_build = Table('queue_build', self.db_meta, autoload=True)
        self.tbl_section = Table('section', self.db_meta, autoload=True)
        self.tbl_source = Table('source', self.db_meta, autoload=True)
        self.tbl_src_associations = Table('src_associations', self.db_meta, autoload=True)
        self.tbl_src_uploaders = Table('src_uploaders', self.db_meta, autoload=True)
        self.tbl_suite = Table('suite', self.db_meta, autoload=True)
        self.tbl_suite_architectures = Table('suite_architectures', self.db_meta, autoload=True)
        self.tbl_uid = Table('uid', self.db_meta, autoload=True)

    def __setupmappers(self):
        mapper(Architecture, self.tbl_architecture,
               properties = dict(arch_id = self.tbl_architecture.c.id))

        mapper(Archive, self.tbl_archive,
               properties = dict(archive_id = self.tbl_archive.c.id,
                                 archive_name = self.tbl_archive.c.name))

        mapper(BinAssociation, self.tbl_bin_associations,
               properties = dict(ba_id = self.tbl_bin_associations.c.id,
                                 suite_id = self.tbl_bin_associations.c.suite,
                                 suite = relation(Suite),
                                 binary_id = self.tbl_bin_associations.c.bin,
                                 binary = relation(DBBinary)))

        mapper(DBBinary, self.tbl_binaries,
               properties = dict(binary_id = self.tbl_binaries.c.id,
                                 package = self.tbl_binaries.c.package,
                                 version = self.tbl_binaries.c.version,
                                 maintainer_id = self.tbl_binaries.c.maintainer,
                                 maintainer = relation(Maintainer),
                                 source_id = self.tbl_binaries.c.source,
                                 source = relation(DBSource),
                                 arch_id = self.tbl_binaries.c.architecture,
                                 architecture = relation(Architecture),
                                 poolfile_id = self.tbl_binaries.c.file,
                                 poolfile = relation(PoolFile),
                                 binarytype = self.tbl_binaries.c.type,
                                 fingerprint_id = self.tbl_binaries.c.sig_fpr,
                                 fingerprint = relation(Fingerprint),
                                 install_date = self.tbl_binaries.c.install_date,
                                 binassociations = relation(BinAssociation,
                                                            primaryjoin=(self.tbl_binaries.c.id==self.tbl_bin_associations.c.bin))))

        mapper(Component, self.tbl_component,
               properties = dict(component_id = self.tbl_component.c.id,
                                 component_name = self.tbl_component.c.name))

        mapper(DBConfig, self.tbl_config,
               properties = dict(config_id = self.tbl_config.c.id))

        mapper(ContentAssociation, self.tbl_content_associations,
               properties = dict(ca_id = self.tbl_content_associations.c.id,
                                 filename_id = self.tbl_content_associations.c.filename,
                                 filename    = relation(ContentFilename),
                                 filepath_id = self.tbl_content_associations.c.filepath,
                                 filepath    = relation(ContentFilepath),
                                 binary_id   = self.tbl_content_associations.c.binary_pkg,
                                 binary      = relation(DBBinary)))


        mapper(ContentFilename, self.tbl_content_file_names,
               properties = dict(cafilename_id = self.tbl_content_file_names.c.id,
                                 filename = self.tbl_content_file_names.c.file))

        mapper(ContentFilepath, self.tbl_content_file_paths,
               properties = dict(cafilepath_id = self.tbl_content_file_paths.c.id,
                                 filepath = self.tbl_content_file_paths.c.path))

        mapper(DSCFile, self.tbl_dsc_files,
               properties = dict(dscfile_id = self.tbl_dsc_files.c.id,
                                 source_id = self.tbl_dsc_files.c.source,
                                 source = relation(DBSource),
                                 poolfile_id = self.tbl_dsc_files.c.file,
                                 poolfile = relation(PoolFile)))

        mapper(PoolFile, self.tbl_files,
               properties = dict(file_id = self.tbl_files.c.id,
                                 filesize = self.tbl_files.c.size,
                                 location_id = self.tbl_files.c.location,
                                 location = relation(Location)))

        mapper(Fingerprint, self.tbl_fingerprint,
               properties = dict(fingerprint_id = self.tbl_fingerprint.c.id,
                                 uid_id = self.tbl_fingerprint.c.uid,
                                 uid = relation(Uid),
                                 keyring_id = self.tbl_fingerprint.c.keyring,
                                 keyring = relation(Keyring)))

        mapper(Keyring, self.tbl_keyrings,
               properties = dict(keyring_name = self.tbl_keyrings.c.name,
                                 keyring_id = self.tbl_keyrings.c.id))

        mapper(Location, self.tbl_location,
               properties = dict(location_id = self.tbl_location.c.id,
                                 component_id = self.tbl_location.c.component,
                                 component = relation(Component),
                                 archive_id = self.tbl_location.c.archive,
                                 archive = relation(Archive),
                                 archive_type = self.tbl_location.c.type))

        mapper(Maintainer, self.tbl_maintainer,
               properties = dict(maintainer_id = self.tbl_maintainer.c.id))

        mapper(Override, self.tbl_override,
               properties = dict(suite_id = self.tbl_override.c.suite,
                                 suite = relation(Suite),
                                 component_id = self.tbl_override.c.component,
                                 component = relation(Component),
                                 priority_id = self.tbl_override.c.priority,
                                 priority = relation(Priority),
                                 section_id = self.tbl_override.c.section,
                                 section = relation(Section),
                                 overridetype_id = self.tbl_override.c.type,
                                 overridetype = relation(OverrideType)))

        mapper(OverrideType, self.tbl_override_type,
               properties = dict(overridetype = self.tbl_override_type.c.type,
                                 overridetype_id = self.tbl_override_type.c.id))

        mapper(PendingContentAssociation, self.tbl_pending_content_associations,
               properties = dict(pca_id = self.tbl_pending_content_associations.c.id,
                                 filepath_id = self.tbl_pending_content_associations.c.filepath,
                                 filepath = relation(ContentFilepath),
                                 filename_id = self.tbl_pending_content_associations.c.filename,
                                 filename = relation(ContentFilename)))

        mapper(Priority, self.tbl_priority,
               properties = dict(priority_id = self.tbl_priority.c.id))

        mapper(Queue, self.tbl_queue,
               properties = dict(queue_id = self.tbl_queue.c.id))

        mapper(QueueBuild, self.tbl_queue_build,
               properties = dict(suite_id = self.tbl_queue_build.c.suite,
                                 queue_id = self.tbl_queue_build.c.queue,
                                 queue = relation(Queue)))

        mapper(Section, self.tbl_section,
               properties = dict(section_id = self.tbl_section.c.id))

        mapper(DBSource, self.tbl_source,
               properties = dict(source_id = self.tbl_source.c.id,
                                 version = self.tbl_source.c.version,
                                 maintainer_id = self.tbl_source.c.maintainer,
                                 maintainer = relation(Maintainer,
                                                       primaryjoin=(self.tbl_source.c.maintainer==self.tbl_maintainer.c.id)),
                                 poolfile_id = self.tbl_source.c.file,
                                 poolfile = relation(PoolFile),
                                 fingerprint_id = self.tbl_source.c.sig_fpr,
                                 fingerprint = relation(Fingerprint),
                                 changedby_id = self.tbl_source.c.changedby,
                                 changedby = relation(Maintainer,
                                                      primaryjoin=(self.tbl_source.c.changedby==self.tbl_maintainer.c.id)),
                                 srcfiles = relation(DSCFile,
                                                     primaryjoin=(self.tbl_source.c.id==self.tbl_dsc_files.c.source)),
                                 srcassociations = relation(SrcAssociation,
                                                            primaryjoin=(self.tbl_source.c.id==self.tbl_src_associations.c.source))))

        mapper(SrcAssociation, self.tbl_src_associations,
               properties = dict(sa_id = self.tbl_src_associations.c.id,
                                 suite_id = self.tbl_src_associations.c.suite,
                                 suite = relation(Suite),
                                 source_id = self.tbl_src_associations.c.source,
                                 source = relation(DBSource)))

        mapper(SrcUploader, self.tbl_src_uploaders,
               properties = dict(uploader_id = self.tbl_src_uploaders.c.id,
                                 source_id = self.tbl_src_uploaders.c.source,
                                 source = relation(DBSource,
                                                   primaryjoin=(self.tbl_src_uploaders.c.source==self.tbl_source.c.id)),
                                 maintainer_id = self.tbl_src_uploaders.c.maintainer,
                                 maintainer = relation(Maintainer,
                                                       primaryjoin=(self.tbl_src_uploaders.c.maintainer==self.tbl_maintainer.c.id))))

        mapper(Suite, self.tbl_suite,
               properties = dict(suite_id = self.tbl_suite.c.id))

        mapper(SuiteArchitecture, self.tbl_suite_architectures,
               properties = dict(suite_id = self.tbl_suite_architectures.c.suite,
                                 suite = relation(Suite, backref='suitearchitectures'),
                                 arch_id = self.tbl_suite_architectures.c.architecture,
                                 architecture = relation(Architecture)))

        mapper(Uid, self.tbl_uid,
               properties = dict(uid_id = self.tbl_uid.c.id))

    ## Connection functions
    def __createconn(self):
        from config import Config
        cnf = Config()
        if cnf["DB::Host"]:
            # TCP/IP
            connstr = "postgres://%s" % cnf["DB::Host"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += ":%s" % cnf["DB::Port"]
            connstr += "/%s" % cnf["DB::Name"]
        else:
            # Unix Socket
            connstr = "postgres:///%s" % cnf["DB::Name"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += "?port=%s" % cnf["DB::Port"]

        self.db_pg   = create_engine(connstr, echo=self.debug)
        self.db_meta = MetaData()
        self.db_meta.bind = self.db_pg
        self.db_smaker = sessionmaker(bind=self.db_pg,
                                      autoflush=True,
                                      autocommit=False)

        self.__setuptables()
        self.__setupmappers()

    def session(self):
        return self.db_smaker()

__all__.append('DBConn')

