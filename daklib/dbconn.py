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
from sqlalchemy.orm import sessionmaker, mapper

from singleton import Singleton
from config import Config

################################################################################

class Cache(object):
    def __init__(self, hashfunc=None):
        if hashfunc:
            self.hashfunc = hashfunc
        else:
            self.hashfunc = lambda x: str(x)

        self.data = {}

    def SetValue(self, keys, value):
        self.data[self.hashfunc(keys)] = value

    def GetValue(self, keys):
        return self.data.get(self.hashfunc(keys))

################################################################################

class Architecture(object):
    def __init__(self, arch_id=None, arch_string=None, description=None):
        self.arch_id = arch_id
        self.arch_string = arch_string
        self.description = description

    def __repr__(self):
        return '<Architecture %s>' % self.arch_string

class Archive(object):
    def __init__(self, archive_id=None, archive_name=None, origin_server=None,
                 description=None):
        self.archive_id = archive_id
        self.archive_name = archive_name
        self.origin_server = origin_server
        self.description = description

    def __repr__(self):
        return '<Archive %s>' % self.name

class BinAssociation(object):
    def __init__(self, ba_id=None, suite_id=None, bin_id=None):
        self.ba_id = ba_id
        self.suite_id = suite_id
        self.bin_id = bin_id

    def __repr__(self):
        return '<BinAssociation %s>' % self.ba_id

class Binary(object):
    def __init__(self, binary_id=None, package=None, version=None,
                 maintainer_id=None, source_id=None, arch_id=None,
                 file_id=None, filetype=None, fingerprint_id=None,
                 install_date=None):
        self.binary_id = binary_id
        self.package = package
        self.version = version
        self.maintainer_id = maintainer_id
        self.source_id = source_id
        self.arch_id = arch_id
        self.file_id = file_id
        self.filetype = filetype
        self.fingerprint_id = fingerprint_id
        self.install_date = install_date

    def __repr__(self):
        return '<Binary %s (%s) %s>' % (self.package, self.version, self.arch_id)

class Component(object):
    def __init__(self, component_id=None, component_name=None,
                 description=None, meets_dfsg=None,):
        self.component_id = component_id
        self.component_name = component_name
        self.description = description
        self.meets_dfsg = meets_dfsg

    def __repr__(self):
        return '<Component %s>' % self.component_name

class DBConfig(object):
    def __init__(self, config_id=None, name=None, value=None):
        self.config_id = config_id
        self.name = name
        self.value = value

    def __repr__(self):
        return '<DBConfig %s>' % self.name

class ContentFilename(object):
    def __init__(self, cafilename_id=None, filename=None):
        self.cafilename_id = cafilename_id
        self.filename = filename

    def __repr__(self):
        return '<ContentFilename %s>' % self.filename

class ContentFilepath(object):
    def __init__(self, cafilepath_id=None, filepath=None):
        self.cafilepath_id = cafilepath_id
        self.filepath = filepath

    def __repr__(self):
        return '<ContentFilepath %s>' % self.filepath

class ContentAssociations(object):
    def __init__(self, binary_id=None, filename_id=None, filepath_id=None,
                 ca_id=None):
        self.binary_id = binary_id
        self.filename_id = filename_id
        self.filepath_id = filepath_id
        self.ca_id = ca_id

    def __repr__(self):
        return '<ContentAssociation %s>' % self.ca_id

class DSCFile(object):
    def __init__(self, dscfile_id=None, source_id=None, file_id=None):
        self.dscfile_id = dscfile_id
        self.source_id = source_id
        self.file_id = file_id

    def __repr__(self):
        return '<DSCFile %s>' % self.dscfile_id

class PoolFile(object):
    def __init__(self, file_id=None, filename=None, filesize=None,
                 location_id=None, last_used=None, md5sum=None,
                 sha1sum=None, sha256sum=None):
        self.file_id = file_id
        self.filename = filename
        self.filesize = filesize
        self.location_id = location_id
        self.last_used = last_used
        self.md5sum = md5sum
        self.sha1sum = sha1sum
        self.sha256sum = sha256sum

    def __repr__(self):
        return '<PoolFile %s>' % self.filename

class Fingerprint(object):
    def __init__(self, fingerprint_id=None, fingerprint=None,
                 uid_id=None, keyring_id=None):
        self.fingerprint_id = fingerprint_id
        self.fingerprint = fingerprint
        self.uid_id = uid_id
        self.keyring_id = keyring_id

    def __repr__(self):
        return '<Fingerprint %s>' % self.fingerprint

class Keyring(object):
    def __init__(self, keyring_id=None, keyring_name=None,
                 debian_maintainer=None):
        self.keyring_id = keyring_id
        self.keyring_name = keyring_name
        self.debian_maintainer = debian_maintainer

    def __repr__(self):
        return '<Keyring %s>' % self.keyring_name

class Location(object):
    def __init__(self, location_id=None, path=None,
                 component_id=None, archive_id=None,
                 archive_type=None):
        self.location_id = location_id
        self.path = path
        self.component_id = component_id
        self.archive_id = archive_id
        self.archive_type = archive_type

    def __repr__(self):
        return '<Location %s (%s)>' % (self.path, self.location_id)

class Maintainer(object):
    def __init__(self, maintainer_id=None, name=None):
        self.maintainer_id = maintainer_id
        self.name = name

    def __repr__(self):
        return '''<Maintainer '%s' (%s)>''' % (self.name, self.maintainer_id)

class Override(object):
    def __init__(self, package, suite_id=None, component_id=None,
                 priority_id=None, section_id=None, overridetype_id=None,
                 maintainer=None):
        self.package = package
        self.suite_id = suite_id
        self.component_id = component_id
        self.priority_id = priority_id
        self.section_id = section_id
        self.overridetype_id = overridetype_id
        self.maintainer = maintainer

    def __repr__(self):
        return '<Override %s (%s)>' % (self.package, self.suite_id)

class OverrideType(object):
    def __init__(self, overridetype_id=None, overridetype=None):
        self.overridetype_id = overridetype_id
        self.overridetype = overridetype

    def __repr__(self):
        return '<OverrideType %s>' % self.overridetype

class PendingContentAssociation(object):
    def __init__(self, pca_id=None, package=None, version=None,
                 filepath_id=None, filename_id=None):
        self.pca_id = pca_id
        self.package = package
        self.version = version
        self.filepath_id = filepath_id
        self.filename_id = filename_id

    def __repr__(self):
        return '<PendingContentAssociation %s>' % self.pca_id

class Priority(object):
    def __init__(self, priority_id=None, priority=None, level=None):
        self.priority_id = priority_id
        self.priority = priority
        self.level = level

    def __repr__(self):
        return '<Priority %s (%s)>' % (self.priority, self.priority_id)

class Queue(object):
    def __init__(self, queue_id=None, queue_name=None):
        self.queue_id = queue_id
        self.queue_name = queue_name

    def __repr__(self):
        return '<Queue %s>' % self.queue_name

class QueueBuild(object):
    def __init__(self, suite_id=None, queue_id=None, filename=None,
                 in_queue=None, last_used=None):
        self.suite_id = suite_id
        self.queue_id = queue_id
        self.filename = filename
        self.in_queue = in_queue
        self.last_used = last_used

    def __repr__(self):
        return '<QueueBuild %s (%s)>' % (self.filename, self.queue_id)

class Section(object):
    def __init__(self, section_id=None, section=None):
        self.section_id = section_id
        self.section = section

    def __repr__(self):
        return '<Section %s>' % self.section

class Source(object):
    def __init__(self, source_id=None, source=None, version=None,
                 maintainer_id=None, file_id=None, fingerprint_id=None,
                 install_date=None, changedby_id=None, dm_upload_allowed=None):
        self.source_id = source_id
        self.source = source
        self.version = version
        self.maintainer_id = maintainer_id
        self.file_id = file_id
        self.fingerprint_id = fingerprint_id
        self.install_date = install_date
        self.changedby_id = changedby_id
        self.dm_upload_allowed = dm_upload_allowed

    def __repr__(self):
        return '<Source %s (%s)>' % (self.source, self.version)

class SrcAssociation(object):
    def __init__(self, sa_id=None, suite_id=None, source_id=None):
        self.sa_id = sa_id
        self.suite_id = suite_id
        self.source_id = source_id

    def __repr__(self):
        return '<SrcAssociation %s>' % self.sa_id

class SrcUploader(object):
    def __init__(self, uploader_id=None, source_id=None, maintainer_id=None):
        self.uploader_id = uploader_id
        self.source_id = source_id
        self.maintainer_id = maintainer_id

    def __repr__(self):
        return '<SrcUploader %s>' % self.uploader_id

class Suite(object):
    def __init__(self, suite_id=None, suite_name=None, version=None,
                 origin=None, label=None, policy_engine=None,
                 description=None, untouchable=None, announce=None,
                 codename=None, overridecodename=None, validtime=None,
                 priority=None, notautomatic=None, copychanges=None,
                 copydotdak=None, commentsdir=None, overridesuite=None,
                 changelogbase=None):

        self.suite_id = suite_id
        self.suite_name = suite_name
        self.version = version
        self.origin = origin
        self.label = label
        self.policy_engine = policy_engine
        self.description = description
        self.untouchable = untouchable
        self.announce = announce
        self.codename = codename
        self.overridecodename = overridecodename
        self.validtime = validtime
        self.priority = priority
        self.notautomatic = notautomatic
        self.copychanges = copychanges
        self.copydotdak = copydotdak
        self.commentsdir = commentsdir
        self.overridesuite = overridesuite
        self.changelogbase = changelogbase

    def __repr__(self):
        return '<Suite %s>' % self.suite_name

class SuiteArchitecture(object):
    def __init__(self, suite_id=None, arch_id=None):
        self.suite_id = suite_id
        self.arch_id = arch_id

    def __repr__(self):
        return '<SuiteArchitecture (%s, %s)>' % (self.suite_id, self.arch_id)

class Uid(object):
    def __init__(self, uid_id=None, uid=None, name=None):
        self.uid_id = uid_id
        self.uid = uid
        self.name = name

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
        self.__createconn()
        self.__init_caches()

    def __setuptables(self):
        self.tbl_architecture = Table('architecture', self.db_meta, autoload=True)
        mapper(Architecture, self.tbl_architecture,
               properties = dict(arch_id = self.tbl_architecture.c.id))

        self.tbl_archive = Table('archive', self.db_meta, autoload=True)
        mapper(Archive, self.tbl_archive,
               properties = dict(archive_id = self.tbl_archive.c.id,
                                 archive_name = self.tbl_archive.c.name))

        self.tbl_bin_associations = Table('bin_associations', self.db_meta, autoload=True)
        mapper(BinAssociation, self.tbl_bin_associations,
               properties = dict(ba_id = self.tbl_bin_associations.c.id,
                                 suite_id = self.tbl_bin_associations.c.suite,
                                 bin_id = self.tbl_bin_associations.c.bin))

        self.tbl_binaries = Table('binaries', self.db_meta, autoload=True)
        mapper(Binary, self.tbl_binaries,
               properties = dict(binary_id = self.tbl_binaries.c.id,
                                 file_id = self.tbl_binaries.c.file,
                                 filetype = self.tbl_binaries.c.type,
                                 maintainer_id = self.tbl_binaries.c.maintainer,
                                 source_id = self.tbl_binaries.c.source,
                                 arch_id = self.tbl_binaries.c.architecture,
                                 fingerprint_id = self.tbl_binaries.c.sig_fpr))

        self.tbl_component = Table('component', self.db_meta, autoload=True)
        mapper(Component, self.tbl_component,
               properties = dict(component_id = self.tbl_component.c.id,
                                 component_name = self.tbl_component.c.name))

        self.tbl_config = Table('config', self.db_meta, autoload=True)
        mapper(DBConfig, self.tbl_config,
               properties = dict(config_id = self.tbl_config.c.id))

        self.tbl_content_associations = Table('content_associations', self.db_meta, autoload=True)
        mapper(ContentAssociations, self.tbl_content_associations,
               properties = dict(ca_id = self.tbl_content_associations.c.id,
                                 filename_id = self.tbl_content_associations.c.filename,
                                 filepath_id = self.tbl_content_associations.c.filepath,
                                 binary_id   = self.tbl_content_associations.c.binary_pkg))

        self.tbl_content_file_names = Table('content_file_names', self.db_meta, autoload=True)
        mapper(ContentFilename, self.tbl_content_file_names,
               properties = dict(cafilename_id = self.tbl_content_file_names.c.id,
                                 filename = self.tbl_content_file_names.c.file))

        self.tbl_content_file_paths = Table('content_file_paths', self.db_meta, autoload=True)
        mapper(ContentFilepath, self.tbl_content_file_paths,
               properties = dict(cafilepath_id = self.tbl_content_file_paths.c.id,
                                 filepath = self.tbl_content_file_paths.c.path))

        self.tbl_dsc_files = Table('dsc_files', self.db_meta, autoload=True)
        mapper(DSCFile, self.tbl_dsc_files,
               properties = dict(dscfile_id = self.tbl_dsc_files.c.id,
                                 source_id = self.tbl_dsc_files.c.source,
                                 file_id = self.tbl_dsc_files.c.file))

        self.tbl_files = Table('files', self.db_meta, autoload=True)
        mapper(PoolFile, self.tbl_files,
               properties = dict(file_id = self.tbl_files.c.id,
                                 filesize = self.tbl_files.c.size,
                                 location_id = self.tbl_files.c.location))

        self.tbl_fingerprint = Table('fingerprint', self.db_meta, autoload=True)
        mapper(Fingerprint, self.tbl_fingerprint,
               properties = dict(fingerprint_id = self.tbl_fingerprint.c.id,
                                 uid_id = self.tbl_fingerprint.c.uid,
                                 keyring_id = self.tbl_fingerprint.c.keyring))

        self.tbl_keyrings = Table('keyrings', self.db_meta, autoload=True)
        mapper(Keyring, self.tbl_keyrings,
               properties = dict(keyring_name = self.tbl_keyrings.c.name,
                                 keyring_id = self.tbl_keyrings.c.id))

        self.tbl_location = Table('location', self.db_meta, autoload=True)
        mapper(Location, self.tbl_location,
               properties = dict(location_id = self.tbl_location.c.id,
                                 component_id = self.tbl_location.c.component,
                                 archive_id = self.tbl_location.c.archive,
                                 archive_type = self.tbl_location.c.type))

        self.tbl_maintainer = Table('maintainer', self.db_meta, autoload=True)
        mapper(Maintainer, self.tbl_maintainer,
               properties = dict(maintainer_id = self.tbl_maintainer.c.id))

        self.tbl_override = Table('override', self.db_meta, autoload=True)
        mapper(Override, self.tbl_override,
               properties = dict(suite_id = self.tbl_override.c.suite,
                                 component_id = self.tbl_override.c.component,
                                 priority_id = self.tbl_override.c.priority,
                                 section_id = self.tbl_override.c.section,
                                 overridetype_id = self.tbl_override.c.type))

        self.tbl_override_type = Table('override_type', self.db_meta, autoload=True)
        mapper(OverrideType, self.tbl_override_type,
               properties = dict(overridetype = self.tbl_override_type.c.type,
                                 overridetype_id = self.tbl_override_type.c.id))

        self.tbl_pending_content_associations = Table('pending_content_associations', self.db_meta, autoload=True)
        mapper(PendingContentAssociation, self.tbl_pending_content_associations,
               properties = dict(pca_id = self.tbl_pending_content_associations.c.id,
                                 filepath_id = self.tbl_pending_content_associations.c.filepath,
                                 filename_id = self.tbl_pending_content_associations.c.filename))

        self.tbl_priority = Table('priority', self.db_meta, autoload=True)
        mapper(Priority, self.tbl_priority,
               properties = dict(priority_id = self.tbl_priority.c.id))

        self.tbl_queue = Table('queue', self.db_meta, autoload=True)
        mapper(Queue, self.tbl_queue,
               properties = dict(queue_id = self.tbl_queue.c.id))

        self.tbl_queue_build = Table('queue_build', self.db_meta, autoload=True)
        mapper(QueueBuild, self.tbl_queue_build,
               properties = dict(suite_id = self.tbl_queue_build.c.suite,
                                 queue_id = self.tbl_queue_build.c.queue))

        self.tbl_section = Table('section', self.db_meta, autoload=True)
        mapper(Section, self.tbl_section,
               properties = dict(section_id = self.tbl_section.c.id))

        self.tbl_source = Table('source', self.db_meta, autoload=True)
        mapper(Source, self.tbl_source,
               properties = dict(source_id = self.tbl_source.c.id,
                                 maintainer_id = self.tbl_source.c.maintainer,
                                 file_id = self.tbl_source.c.file,
                                 fingerprint_id = self.tbl_source.c.sig_fpr,
                                 changedby_id = self.tbl_source.c.changedby))

        self.tbl_src_associations = Table('src_associations', self.db_meta, autoload=True)
        mapper(SrcAssociation, self.tbl_src_associations,
               properties = dict(sa_id = self.tbl_src_associations.c.id))

        self.tbl_src_uploaders = Table('src_uploaders', self.db_meta, autoload=True)
        mapper(SrcUploader, self.tbl_src_uploaders,
               properties = dict(uploader_id = self.tbl_src_uploaders.c.id,
                                 source_id = self.tbl_src_uploaders.c.source,
                                 maintainer_id = self.tbl_src_uploaders.c.maintainer))

        self.tbl_suite = Table('suite', self.db_meta, autoload=True)
        mapper(Suite, self.tbl_suite,
               properties = dict(suite_id = self.tbl_suite.c.id))

        self.tbl_suite_architectures = Table('suite_architectures', self.db_meta, autoload=True)
        mapper(SuiteArchitecture, self.tbl_suite_architectures,
               properties = dict(suite_id = self.tbl_suite_architectures.c.suite,
                                 arch_id = self.tbl_suite_architectures.c.architecture))

        self.tbl_uid = Table('uid', self.db_meta, autoload=True)
        mapper(Uid, self.tbl_uid,
               properties = dict(uid_id = self.tbl_uid.c.id))

    ## Connection functions
    def __createconn(self):
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

        self.db_pg   = create_engine(connstr)
        self.db_meta = MetaData()
        self.db_meta.bind = self.db_pg
        self.db_smaker = sessionmaker(bind=self.db_pg,
                                      autoflush=True,
                                      transactional=True)

        self.__setuptables()

    def session(self):
        return self.db_smaker()

    ## Cache functions
    def __init_caches(self):
        self.caches = {'suite':         Cache(),
                       'section':       Cache(),
                       'priority':      Cache(),
                       'override_type': Cache(),
                       'architecture':  Cache(),
                       'archive':       Cache(),
                       'component':     Cache(),
                       'content_path_names':     Cache(),
                       'content_file_names':     Cache(),
                       'location':      Cache(lambda x: '%s_%s_%s' % (x['location'], x['component'], x['location'])),
                       'maintainer':    {}, # TODO
                       'keyring':       {}, # TODO
                       'source':        Cache(lambda x: '%s_%s_' % (x['source'], x['version'])),
                       'files':         Cache(lambda x: '%s_%s_' % (x['filename'], x['location'])),
                       'maintainer':    {}, # TODO
                       'fingerprint':   {}, # TODO
                       'queue':         {}, # TODO
                       'uid':           {}, # TODO
                       'suite_version': Cache(lambda x: '%s_%s' % (x['source'], x['suite'])),
                      }

        self.prepared_statements = {}

    def prepare(self,name,statement):
        if not self.prepared_statements.has_key(name):
            pgc.execute(statement)
            self.prepared_statements[name] = statement

    def clear_caches(self):
        self.__init_caches()

    ## Get functions
    def __get_id(self, retfield, selectobj, cachekey, cachename=None):
        # This is a bit of a hack but it's an internal function only
        if cachename is not None:
            res = self.caches[cachename].GetValue(cachekey)
            if res:
                return res

        c = selectobj.execute()

        if c.rowcount != 1:
            return None

        res = c.fetchone()

        if retfield not in res.keys():
            return None

        res = res[retfield]

        if cachename is not None:
            self.caches[cachename].SetValue(cachekey, res)

        return res

    def get_suite_id(self, suite):
        """
        Returns database id for given C{suite}.
        Results are kept in a cache during runtime to minimize database queries.

        @type suite: string
        @param suite: The name of the suite

        @rtype: int
        @return: the database id for the given suite

        """
        return int(self.__get_id('id',
                                 self.tbl_suite.select(self.tbl_suite.columns.suite_name == suite),
                                 suite,
                                 'suite'))

    def get_section_id(self, section):
        """
        Returns database id for given C{section}.
        Results are kept in a cache during runtime to minimize database queries.

        @type section: string
        @param section: The name of the section

        @rtype: int
        @return: the database id for the given section

        """
        return self.__get_id('id',
                             self.tbl_section.select(self.tbl_section.columns.section == section),
                             section,
                             'section')

    def get_priority_id(self, priority):
        """
        Returns database id for given C{priority}.
        Results are kept in a cache during runtime to minimize database queries.

        @type priority: string
        @param priority: The name of the priority

        @rtype: int
        @return: the database id for the given priority

        """
        return self.__get_id('id',
                             self.tbl_priority.select(self.tbl_priority.columns.priority == priority),
                             priority,
                             'priority')

    def get_override_type_id(self, override_type):
        """
        Returns database id for given override C{type}.
        Results are kept in a cache during runtime to minimize database queries.

        @type override_type: string
        @param override_type: The name of the override type

        @rtype: int
        @return: the database id for the given override type

        """
        return self.__get_id('id',
                             self.tbl_override_type.select(self.tbl_override_type.columns.type == override_type),
                             override_type,
                             'override_type')

    def get_architecture_id(self, architecture):
        """
        Returns database id for given C{architecture}.
        Results are kept in a cache during runtime to minimize database queries.

        @type architecture: string
        @param architecture: The name of the override type

        @rtype: int
        @return: the database id for the given architecture

        """
        return self.__get_id('id',
                             self.tbl_architecture.select(self.tbl_architecture.columns.arch_string == architecture),
                             architecture,
                             'architecture')

    def get_archive_id(self, archive):
        """
        returns database id for given c{archive}.
        results are kept in a cache during runtime to minimize database queries.

        @type archive: string
        @param archive: the name of the override type

        @rtype: int
        @return: the database id for the given archive

        """
        archive = archive.lower()
        return self.__get_id('id',
                             self.tbl_archive.select(self.tbl_archive.columns.name == archive),
                             archive,
                             'archive')

    def get_component_id(self, component):
        """
        Returns database id for given C{component}.
        Results are kept in a cache during runtime to minimize database queries.

        @type component: string
        @param component: The name of the override type

        @rtype: int
        @return: the database id for the given component

        """
        component = component.lower()
        return self.__get_id('id',
                             self.tbl_component.select(self.tbl_component.columns.name == component),
                             component.lower(),
                             'component')

    def get_location_id(self, location, component, archive):
        """
        Returns database id for the location behind the given combination of
          - B{location} - the path of the location, eg. I{/srv/ftp.debian.org/ftp/pool/}
          - B{component} - the id of the component as returned by L{get_component_id}
          - B{archive} - the id of the archive as returned by L{get_archive_id}
        Results are kept in a cache during runtime to minimize database queries.

        @type location: string
        @param location: the path of the location

        @type component: string
        @param component: the name of the component

        @type archive: string
        @param archive: the name of the archive

        @rtype: int
        @return: the database id for the location

        """

        archive = archive.lower()
        component = component.lower()

        values = {'archive': archive, 'location': location, 'component': component}

        s = self.tbl_location.join(self.tbl_archive).join(self.tbl_component)

        s = s.select(self.tbl_location.columns.path == location)
        s = s.where(self.tbl_archive.columns.name == archive)
        s = s.where(self.tbl_component.columns.name == component)

        return self.__get_id('location.id', s, values, 'location')

    def get_source_id(self, source, version):
        """
        Returns database id for the combination of C{source} and C{version}
          - B{source} - source package name, eg. I{mailfilter}, I{bbdb}, I{glibc}
          - B{version}
        Results are kept in a cache during runtime to minimize database queries.

        @type source: string
        @param source: source package name

        @type version: string
        @param version: the source version

        @rtype: int
        @return: the database id for the source

        """
        s = self.tbl_source.select()
        s = s.where(self.tbl_source.columns.source  == source)
        s = s.where(self.tbl_source.columns.version == version)

        return self.__get_id('id', s, {'source': source, 'version': version}, 'source')

    def get_suite(self, suite):
        if isinstance(suite, str):
            suite_id = self.get_suite_id(suite.lower())
        elif type(suite) == int:
            suite_id = suite

        s = self.tbl_suite.select(self.tbl_suite.columns.id == suite_id)
        c = s.execute()
        if c.rowcount < 1:
            return None
        else:
            return c.fetchone()

    def get_suite_version(self, source, suite):
        """
        Returns database id for a combination of C{source} and C{suite}.

          - B{source} - source package name, eg. I{mailfilter}, I{bbdb}, I{glibc}
          - B{suite} - a suite name, eg. I{unstable}

        Results are kept in a cache during runtime to minimize database queries.

        @type source: string
        @param source: source package name

        @type suite: string
        @param suite: the suite name

        @rtype: string
        @return: the version for I{source} in I{suite}

        """
        s = select([self.tbl_source.columns.source, self.tbl_source.columns.version])
#        s = self.tbl_source.join(self.tbl_src_associations).join(self.tbl_suite)

        s = s.select(self.tbl_suite.columns.suite_name == suite, use_labels=True)
        s = s.select(self.tbl_source.columns.source == source)

        return self.__get_id('source.version', s, {'suite': suite, 'source': source}, 'suite_version')


    def get_files_id (self, filename, size, md5sum, location_id):
        """
        Returns -1, -2 or the file_id for filename, if its C{size} and C{md5sum} match an
        existing copy.

        The database is queried using the C{filename} and C{location_id}. If a file does exist
        at that location, the existing size and md5sum are checked against the provided
        parameters. A size or checksum mismatch returns -2. If more than one entry is
        found within the database, a -1 is returned, no result returns None, otherwise
        the file id.

        Results are kept in a cache during runtime to minimize database queries.

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

        res = self.caches['files'].GetValue( values )

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
                    self.caches['files'].SetValue(values, row[0])
                    res = row[0]

        return res


    def get_or_set_contents_file_id(self, filename):
        """
        Returns database id for given filename.

        Results are kept in a cache during runtime to minimize database queries.
        If no matching file is found, a row is inserted.

        @type filename: string
        @param filename: The filename

        @rtype: int
        @return: the database id for the given component
        """
        try:
            values={'value': filename}
            query = "SELECT id FROM content_file_names WHERE file = %(value)s"
            id = self.__get_single_id(query, values, cachename='content_file_names')
            if not id:
                c = self.db_con.cursor()
                c.execute( "INSERT INTO content_file_names VALUES (DEFAULT, %(value)s) RETURNING id",
                           values )

                id = c.fetchone()[0]
                self.caches['content_file_names'].SetValue(values, id)

            return id
        except:
            traceback.print_exc()
            raise

    def get_or_set_contents_path_id(self, path):
        """
        Returns database id for given path.

        Results are kept in a cache during runtime to minimize database queries.
        If no matching file is found, a row is inserted.

        @type path: string
        @param path: The filename

        @rtype: int
        @return: the database id for the given component
        """
        try:
            values={'value': path}
            query = "SELECT id FROM content_file_paths WHERE path = %(value)s"
            id = self.__get_single_id(query, values, cachename='content_path_names')
            if not id:
                c = self.db_con.cursor()
                c.execute( "INSERT INTO content_file_paths VALUES (DEFAULT, %(value)s) RETURNING id",
                           values )

                id = c.fetchone()[0]
                self.caches['content_path_names'].SetValue(values, id)

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

                if path.startswith( "./" ):
                    path = path[2:]
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

