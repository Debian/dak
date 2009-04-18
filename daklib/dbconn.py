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

from singleton import Singleton

################################################################################

class Architecture(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Architecture %s>' % self.arch_string

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

class Archive(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Archive %s>' % self.name

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


class BinAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BinAssociation %s (%s, %s)>' % (self.ba_id, self.binary, self.suite)

class Binary(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Binary %s (%s, %s)>' % (self.package, self.version, self.architecture)

def get_binary_from_id(id, session=None):
    """
    Returns Binary object for given C{id}

    @type id: int
    @param id: Id of the required binary

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Binary
    @return: Binary object for the given binary (None if not present)
    """
    if session is None:
        session = DBConn().session()
    q = session.query(Binary).filter_by(binary_id=id)
    if q.count() == 0:
        return None
    return q.one()

class Component(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Component %s>' % self.component_name

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

class DBConfig(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBConfig %s>' % self.name

class ContentFilename(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ContentFilename %s>' % self.filename

class ContentFilepath(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ContentFilepath %s>' % self.filepath

class ContentAssociations(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ContentAssociation %s>' % self.ca_id

class DSCFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DSCFile %s>' % self.dscfile_id

class PoolFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<PoolFile %s>' % self.filename

class Fingerprint(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Fingerprint %s>' % self.fingerprint

class Keyring(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Keyring %s>' % self.keyring_name

class Location(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Location %s (%s)>' % (self.path, self.location_id)

class Maintainer(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '''<Maintainer '%s' (%s)>''' % (self.name, self.maintainer_id)

class Override(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Override %s (%s)>' % (self.package, self.suite_id)

class OverrideType(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<OverrideType %s>' % self.overridetype

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

class PendingContentAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<PendingContentAssociation %s>' % self.pca_id

class Priority(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Priority %s (%s)>' % (self.priority, self.priority_id)

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

class Queue(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Queue %s>' % self.queue_name

class QueueBuild(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<QueueBuild %s (%s)>' % (self.filename, self.queue_id)

class Section(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Section %s>' % self.section

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

class Source(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Source %s (%s)>' % (self.source, self.version)

def get_source_in_suite(source, suite, session=None):
    """
    Returns list of Source objects for a combination of C{source} and C{suite}.

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

class SrcAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcAssociation %s (%s, %s)>' % (self.sa_id, self.source, self.suite)

class SrcUploader(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcUploader %s>' % self.uploader_id

class Suite(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Suite %s>' % self.suite_name

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

class SuiteArchitecture(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SuiteArchitecture (%s, %s)>' % (self.suite_id, self.arch_id)

class Uid(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Uid %s (%s)>' % (self.uid, self.name)

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
                                 binary = relation(Binary)))

        mapper(Binary, self.tbl_binaries,
               properties = dict(binary_id = self.tbl_binaries.c.id,
                                 package = self.tbl_binaries.c.package,
                                 version = self.tbl_binaries.c.version,
                                 maintainer_id = self.tbl_binaries.c.maintainer,
                                 maintainer = relation(Maintainer),
                                 source_id = self.tbl_binaries.c.source,
                                 source = relation(Source),
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

        mapper(ContentAssociations, self.tbl_content_associations,
               properties = dict(ca_id = self.tbl_content_associations.c.id,
                                 filename_id = self.tbl_content_associations.c.filename,
                                 filename    = relation(ContentFilename),
                                 filepath_id = self.tbl_content_associations.c.filepath,
                                 filepath    = relation(ContentFilepath),
                                 binary_id   = self.tbl_content_associations.c.binary_pkg,
                                 binary      = relation(Binary)))


        mapper(ContentFilename, self.tbl_content_file_names,
               properties = dict(cafilename_id = self.tbl_content_file_names.c.id,
                                 filename = self.tbl_content_file_names.c.file))

        mapper(ContentFilepath, self.tbl_content_file_paths,
               properties = dict(cafilepath_id = self.tbl_content_file_paths.c.id,
                                 filepath = self.tbl_content_file_paths.c.path))

        mapper(DSCFile, self.tbl_dsc_files,
               properties = dict(dscfile_id = self.tbl_dsc_files.c.id,
                                 source_id = self.tbl_dsc_files.c.source,
                                 source = relation(Source),
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

        mapper(Source, self.tbl_source,
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
                                 source = relation(Source)))

        mapper(SrcUploader, self.tbl_src_uploaders,
               properties = dict(uploader_id = self.tbl_src_uploaders.c.id,
                                 source_id = self.tbl_src_uploaders.c.source,
                                 source = relation(Source,
                                                   primaryjoin=(self.tbl_src_uploaders.c.source==self.tbl_source.c.id)),
                                 maintainer_id = self.tbl_src_uploaders.c.maintainer,
                                 maintainer = relation(Maintainer,
                                                       primaryjoin=(self.tbl_src_uploaders.c.maintainer==self.tbl_maintainer.c.id))))

        mapper(Suite, self.tbl_suite,
               properties = dict(suite_id = self.tbl_suite.c.id))

        mapper(SuiteArchitecture, self.tbl_suite_architectures,
               properties = dict(suite_id = self.tbl_suite_architectures.c.suite,
                                 suite = relation(Suite),
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
                                      transactional=True)

        self.__setuptables()
        self.__setupmappers()

    def session(self):
        return self.db_smaker()

    def prepare(self,name,statement):
        if not self.prepared_statements.has_key(name):
            pgc.execute(statement)
            self.prepared_statements[name] = statement


    def get_location_id(self, location, component, archive):
        """
        Returns database id for the location behind the given combination of
          - B{location} - the path of the location, eg. I{/srv/ftp.debian.org/ftp/pool/}
          - B{component} - the id of the component as returned by L{get_component_id}
          - B{archive} - the id of the archive as returned by L{get_archive_id}
        Results are kept in a cache during runtime to minimize database queries.

        @type location: string
        @param location: the path of the location

        @type component: int
        @param component: the id of the component

        @type archive: int
        @param archive: the id of the archive

        @rtype: int
        @return: the database id for the location

        """

        archive_id = self.get_archive_id(archive)

        if not archive_id:
            return None

        res = None

        if component:
            component_id = self.get_component_id(component)
            if component_id:
                res = self.__get_single_id("SELECT id FROM location WHERE path=%(location)s AND component=%(component)s AND archive=%(archive)s",
                        {'location': location,
                         'archive': int(archive_id),
                         'component': component_id}, cachename='location')
        else:
            res = self.__get_single_id("SELECT id FROM location WHERE path=%(location)s AND archive=%(archive)d",
                    {'location': location, 'archive': archive_id, 'component': ''}, cachename='location')

        return res



def get_files_id (self, filename, size, md5sum, location_id):
    """
    Returns -1, -2 or the file_id for filename, if its C{size} and C{md5sum} match an
    existing copy.

    The database is queried using the C{filename} and C{location_id}. If a file does exist
    at that location, the existing size and md5sum are checked against the provided
    parameters. A size or checksum mismatch returns -2. If more than one entry is
    found within the database, a -1 is returned, no result returns None, otherwise
    the file id.

    @type filename: string
    @param filename: the filename of the file to check against the DB

    @type size: int
    @param size: the size of the file to check against the DB

    @type md5sum: string
    @param md5sum: the md5sum of the file to check against the DB

    @type location_id: int
    @param location_id: the id of the location as returned by L{get_location_id}

    @rtype: int / None
    @return: Various return values are possible:
               - -2: size/checksum error
               - -1: more than one file found in database
               - None: no file found in database
               - int: file id

    """
    values = {'filename' : filename,
              'location' : location_id}

    if not res:
        query = """SELECT id, size, md5sum
                   FROM files
                   WHERE filename = %(filename)s AND location = %(location)s"""

        cursor = self.db_con.cursor()
        cursor.execute( query, values )

        if cursor.rowcount == 0:
            res = None

        elif cursor.rowcount != 1:
            res = -1

        else:
            row = cursor.fetchone()

            if row[1] != int(size) or row[2] != md5sum:
                res =  -2

            else:
                res = row[0]

    return res


def get_or_set_contents_file_id(self, filename):
    """
    Returns database id for given filename.

    If no matching file is found, a row is inserted.

    @type filename: string
    @param filename: The filename

    @rtype: int
    @return: the database id for the given component
    """
    try:
        values={'value': filename}
        query = "SELECT id FROM content_file_names WHERE file = %(value)s"
        if not id:
            c = self.db_con.cursor()
            c.execute( "INSERT INTO content_file_names VALUES (DEFAULT, %(value)s) RETURNING id",
                       values )

            id = c.fetchone()[0]

        return id
    except:
        traceback.print_exc()
        raise

def get_or_set_contents_path_id(self, path):
    """
    Returns database id for given path.

    If no matching file is found, a row is inserted.

    @type path: string
    @param path: The filename

    @rtype: int
    @return: the database id for the given component
    """
    try:
        values={'value': path}
        query = "SELECT id FROM content_file_paths WHERE path = %(value)s"
        if not id:
            c = self.db_con.cursor()
            c.execute( "INSERT INTO content_file_paths VALUES (DEFAULT, %(value)s) RETURNING id",
                       values )

            id = c.fetchone()[0]

        return id
    except:
        traceback.print_exc()
        raise

def get_suite_architectures(self, suite):
    """
    Returns list of architectures for C{suite}.

    @type suite: string, int
    @param suite: the suite name or the suite_id

    @rtype: list
    @return: the list of architectures for I{suite}
    """

    suite_id = None
    if type(suite) == str:
        suite_id = self.get_suite_id(suite)
    elif type(suite) == int:
        suite_id = suite
    else:
        return None

    c = self.db_con.cursor()
    c.execute( """SELECT a.arch_string FROM suite_architectures sa
                  JOIN architecture a ON (a.id = sa.architecture)
                  WHERE suite='%s'""" % suite_id )

    return map(lambda x: x[0], c.fetchall())

def insert_content_paths(self, bin_id, fullpaths):
    """
    Make sure given path is associated with given binary id

    @type bin_id: int
    @param bin_id: the id of the binary
    @type fullpaths: list
    @param fullpaths: the list of paths of the file being associated with the binary

    @return: True upon success
    """

    c = self.db_con.cursor()

    c.execute("BEGIN WORK")
    try:

        for fullpath in fullpaths:
            (path, file) = os.path.split(fullpath)

            # Get the necessary IDs ...
            file_id = self.get_or_set_contents_file_id(file)
            path_id = self.get_or_set_contents_path_id(path)

            c.execute("""INSERT INTO content_associations
                           (binary_pkg, filepath, filename)
                       VALUES ( '%d', '%d', '%d')""" % (bin_id, path_id, file_id) )

        c.execute("COMMIT")
        return True
    except:
        traceback.print_exc()
        c.execute("ROLLBACK")
        return False

def insert_pending_content_paths(self, package, fullpaths):
    """
    Make sure given paths are temporarily associated with given
    package

    @type package: dict
    @param package: the package to associate with should have been read in from the binary control file
    @type fullpaths: list
    @param fullpaths: the list of paths of the file being associated with the binary

    @return: True upon success
    """

    c = self.db_con.cursor()

    c.execute("BEGIN WORK")
    try:
        arch_id = self.get_architecture_id(package['Architecture'])

        # Remove any already existing recorded files for this package
        c.execute("""DELETE FROM pending_content_associations
                     WHERE package=%(Package)s
                     AND version=%(Version)s
                     AND architecture=%(ArchID)s""", {'Package': package['Package'],
                                                      'Version': package['Version'],
                                                      'ArchID':  arch_id})

        for fullpath in fullpaths:
            (path, file) = os.path.split(fullpath)

            if path.startswith( "./" ):
                path = path[2:]
            # Get the necessary IDs ...
            file_id = self.get_or_set_contents_file_id(file)
            path_id = self.get_or_set_contents_path_id(path)

            c.execute("""INSERT INTO pending_content_associations
                           (package, version, architecture, filepath, filename)
                        VALUES (%%(Package)s, %%(Version)s, '%d', '%d', '%d')"""
                % (arch_id, path_id, file_id), package )

        c.execute("COMMIT")
        return True
    except:
        traceback.print_exc()
        c.execute("ROLLBACK")
        return False
