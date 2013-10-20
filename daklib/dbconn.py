#!/usr/bin/python

""" DB access class

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
@copyright: 2008-2009  Mark Hymers <mhy@debian.org>
@copyright: 2009, 2010  Joerg Jaspert <joerg@debian.org>
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

import apt_pkg
import daklib.daksubprocess
import os
from os.path import normpath
import re
import psycopg2
import subprocess
import traceback

try:
    # python >= 2.6
    import json
except:
    # python <= 2.5
    import simplejson as json

from datetime import datetime, timedelta
from errno import ENOENT
from tempfile import mkstemp, mkdtemp
from tarfile import TarFile

from inspect import getargspec

import sqlalchemy
from sqlalchemy import create_engine, Table, MetaData, Column, Integer, desc, \
    Text, ForeignKey
from sqlalchemy.orm import sessionmaker, mapper, relation, object_session, \
    backref, MapperExtension, EXT_CONTINUE, object_mapper, clear_mappers
from sqlalchemy import types as sqltypes
from sqlalchemy.orm.collections import attribute_mapped_collection
from sqlalchemy.ext.associationproxy import association_proxy

# Don't remove this, we re-export the exceptions to scripts which import us
from sqlalchemy.exc import *
from sqlalchemy.orm.exc import NoResultFound

# Only import Config until Queue stuff is changed to store its config
# in the database
from config import Config
from textutils import fix_maintainer
from dak_exceptions import DBUpdateError, NoSourceFieldError, FileExistsError

# suppress some deprecation warnings in squeeze related to sqlalchemy
import warnings
warnings.filterwarnings('ignore', \
    "The SQLAlchemy PostgreSQL dialect has been renamed from 'postgres' to 'postgresql'.*", \
    SADeprecationWarning)
warnings.filterwarnings('ignore', \
    "Predicate of partial index .* ignored during reflection", \
    SAWarning)


################################################################################

# Patch in support for the debversion field type so that it works during
# reflection

try:
    # that is for sqlalchemy 0.6
    UserDefinedType = sqltypes.UserDefinedType
except:
    # this one for sqlalchemy 0.5
    UserDefinedType = sqltypes.TypeEngine

class DebVersion(UserDefinedType):
    def get_col_spec(self):
        return "DEBVERSION"

    def bind_processor(self, dialect):
        return None

    # ' = None' is needed for sqlalchemy 0.5:
    def result_processor(self, dialect, coltype = None):
        return None

sa_major_version = sqlalchemy.__version__[0:3]
if sa_major_version in ["0.5", "0.6", "0.7", "0.8"]:
    from sqlalchemy.databases import postgres
    postgres.ischema_names['debversion'] = DebVersion
else:
    raise Exception("dak only ported to SQLA versions 0.5 to 0.8.  See daklib/dbconn.py")

################################################################################

__all__ = ['IntegrityError', 'SQLAlchemyError', 'DebVersion']

################################################################################

def session_wrapper(fn):
    """
    Wrapper around common ".., session=None):" handling. If the wrapped
    function is called without passing 'session', we create a local one
    and destroy it when the function ends.

    Also attaches a commit_or_flush method to the session; if we created a
    local session, this is a synonym for session.commit(), otherwise it is a
    synonym for session.flush().
    """

    def wrapped(*args, **kwargs):
        private_transaction = False

        # Find the session object
        session = kwargs.get('session')

        if session is None:
            if len(args) <= len(getargspec(fn)[0]) - 1:
                # No session specified as last argument or in kwargs
                private_transaction = True
                session = kwargs['session'] = DBConn().session()
            else:
                # Session is last argument in args
                session = args[-1]
                if session is None:
                    args = list(args)
                    session = args[-1] = DBConn().session()
                    private_transaction = True

        if private_transaction:
            session.commit_or_flush = session.commit
        else:
            session.commit_or_flush = session.flush

        try:
            return fn(*args, **kwargs)
        finally:
            if private_transaction:
                # We created a session; close it.
                session.close()

    wrapped.__doc__ = fn.__doc__
    wrapped.func_name = fn.func_name

    return wrapped

__all__.append('session_wrapper')

################################################################################

class ORMObject(object):
    """
    ORMObject is a base class for all ORM classes mapped by SQLalchemy. All
    derived classes must implement the properties() method.
    """

    def properties(self):
        '''
        This method should be implemented by all derived classes and returns a
        list of the important properties. The properties 'created' and
        'modified' will be added automatically. A suffix '_count' should be
        added to properties that are lists or query objects. The most important
        property name should be returned as the first element in the list
        because it is used by repr().
        '''
        return []

    def json(self):
        '''
        Returns a JSON representation of the object based on the properties
        returned from the properties() method.
        '''
        data = {}
        # add created and modified
        all_properties = self.properties() + ['created', 'modified']
        for property in all_properties:
            # check for list or query
            if property[-6:] == '_count':
                real_property = property[:-6]
                if not hasattr(self, real_property):
                    continue
                value = getattr(self, real_property)
                if hasattr(value, '__len__'):
                    # list
                    value = len(value)
                elif hasattr(value, 'count'):
                    # query (but not during validation)
                    if self.in_validation:
                        continue
                    value = value.count()
                else:
                    raise KeyError('Do not understand property %s.' % property)
            else:
                if not hasattr(self, property):
                    continue
                # plain object
                value = getattr(self, property)
                if value is None:
                    # skip None
                    continue
                elif isinstance(value, ORMObject):
                    # use repr() for ORMObject types
                    value = repr(value)
                else:
                    # we want a string for all other types because json cannot
                    # encode everything
                    value = str(value)
            data[property] = value
        return json.dumps(data)

    def classname(self):
        '''
        Returns the name of the class.
        '''
        return type(self).__name__

    def __repr__(self):
        '''
        Returns a short string representation of the object using the first
        element from the properties() method.
        '''
        primary_property = self.properties()[0]
        value = getattr(self, primary_property)
        return '<%s %s>' % (self.classname(), str(value))

    def __str__(self):
        '''
        Returns a human readable form of the object using the properties()
        method.
        '''
        return '<%s %s>' % (self.classname(), self.json())

    def not_null_constraints(self):
        '''
        Returns a list of properties that must be not NULL. Derived classes
        should override this method if needed.
        '''
        return []

    validation_message = \
        "Validation failed because property '%s' must not be empty in object\n%s"

    in_validation = False

    def validate(self):
        '''
        This function validates the not NULL constraints as returned by
        not_null_constraints(). It raises the DBUpdateError exception if
        validation fails.
        '''
        for property in self.not_null_constraints():
            # TODO: It is a bit awkward that the mapper configuration allow
            # directly setting the numeric _id columns. We should get rid of it
            # in the long run.
            if hasattr(self, property + '_id') and \
                getattr(self, property + '_id') is not None:
                continue
            if not hasattr(self, property) or getattr(self, property) is None:
                # str() might lead to races due to a 2nd flush
                self.in_validation = True
                message = self.validation_message % (property, str(self))
                self.in_validation = False
                raise DBUpdateError(message)

    @classmethod
    @session_wrapper
    def get(cls, primary_key,  session = None):
        '''
        This is a support function that allows getting an object by its primary
        key.

        Architecture.get(3[, session])

        instead of the more verbose

        session.query(Architecture).get(3)
        '''
        return session.query(cls).get(primary_key)

    def session(self, replace = False):
        '''
        Returns the current session that is associated with the object. May
        return None is object is in detached state.
        '''

        return object_session(self)

    def clone(self, session = None):
        """
        Clones the current object in a new session and returns the new clone. A
        fresh session is created if the optional session parameter is not
        provided. The function will fail if a session is provided and has
        unflushed changes.

        RATIONALE: SQLAlchemy's session is not thread safe. This method clones
        an existing object to allow several threads to work with their own
        instances of an ORMObject.

        WARNING: Only persistent (committed) objects can be cloned. Changes
        made to the original object that are not committed yet will get lost.
        The session of the new object will always be rolled back to avoid
        resource leaks.
        """

        if self.session() is None:
            raise RuntimeError( \
                'Method clone() failed for detached object:\n%s' % self)
        self.session().flush()
        mapper = object_mapper(self)
        primary_key = mapper.primary_key_from_instance(self)
        object_class = self.__class__
        if session is None:
            session = DBConn().session()
        elif len(session.new) + len(session.dirty) + len(session.deleted) > 0:
            raise RuntimeError( \
                'Method clone() failed due to unflushed changes in session.')
        new_object = session.query(object_class).get(primary_key)
        session.rollback()
        if new_object is None:
            raise RuntimeError( \
                'Method clone() failed for non-persistent object:\n%s' % self)
        return new_object

__all__.append('ORMObject')

################################################################################

class Validator(MapperExtension):
    '''
    This class calls the validate() method for each instance for the
    'before_update' and 'before_insert' events. A global object validator is
    used for configuring the individual mappers.
    '''

    def before_update(self, mapper, connection, instance):
        instance.validate()
        return EXT_CONTINUE

    def before_insert(self, mapper, connection, instance):
        instance.validate()
        return EXT_CONTINUE

validator = Validator()

################################################################################

class ACL(ORMObject):
    def __repr__(self):
        return "<ACL {0}>".format(self.name)

__all__.append('ACL')

class ACLPerSource(ORMObject):
    def __repr__(self):
        return "<ACLPerSource acl={0} fingerprint={1} source={2} reason={3}>".format(self.acl.name, self.fingerprint.fingerprint, self.source, self.reason)

__all__.append('ACLPerSource')

################################################################################

class Architecture(ORMObject):
    def __init__(self, arch_string = None, description = None):
        self.arch_string = arch_string
        self.description = description

    def __eq__(self, val):
        if isinstance(val, str):
            return (self.arch_string== val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            return (self.arch_string != val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def properties(self):
        return ['arch_string', 'arch_id', 'suites_count']

    def not_null_constraints(self):
        return ['arch_string']

__all__.append('Architecture')

@session_wrapper
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

    q = session.query(Architecture).filter_by(arch_string=architecture)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_architecture')

################################################################################

class Archive(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Archive %s>' % self.archive_name

__all__.append('Archive')

@session_wrapper
def get_archive(archive, session=None):
    """
    returns database id for given C{archive}.

    @type archive: string
    @param archive: the name of the arhive

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Archive
    @return: Archive object for the given name (None if not present)

    """
    archive = archive.lower()

    q = session.query(Archive).filter_by(archive_name=archive)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_archive')

################################################################################

class ArchiveFile(object):
    def __init__(self, archive=None, component=None, file=None):
        self.archive = archive
        self.component = component
        self.file = file
    @property
    def path(self):
        return os.path.join(self.archive.path, 'pool', self.component.component_name, self.file.filename)

__all__.append('ArchiveFile')

################################################################################

class BinContents(ORMObject):
    def __init__(self, file = None, binary = None):
        self.file = file
        self.binary = binary

    def properties(self):
        return ['file', 'binary']

__all__.append('BinContents')

################################################################################

class DBBinary(ORMObject):
    def __init__(self, package = None, source = None, version = None, \
        maintainer = None, architecture = None, poolfile = None, \
        binarytype = 'deb', fingerprint=None):
        self.package = package
        self.source = source
        self.version = version
        self.maintainer = maintainer
        self.architecture = architecture
        self.poolfile = poolfile
        self.binarytype = binarytype
        self.fingerprint = fingerprint

    @property
    def pkid(self):
        return self.binary_id

    def properties(self):
        return ['package', 'version', 'maintainer', 'source', 'architecture', \
            'poolfile', 'binarytype', 'fingerprint', 'install_date', \
            'suites_count', 'binary_id', 'contents_count', 'extra_sources']

    def not_null_constraints(self):
        return ['package', 'version', 'maintainer', 'source',  'poolfile', \
            'binarytype']

    metadata = association_proxy('key', 'value')

    def scan_contents(self):
        '''
        Yields the contents of the package. Only regular files are yielded and
        the path names are normalized after converting them from either utf-8
        or iso8859-1 encoding. It yields the string ' <EMPTY PACKAGE>' if the
        package does not contain any regular file.
        '''
        fullpath = self.poolfile.fullpath
        dpkg_cmd = ('dpkg-deb', '--fsys-tarfile', fullpath)
        dpkg = daklib.daksubprocess.Popen(dpkg_cmd, stdout=subprocess.PIPE)
        tar = TarFile.open(fileobj = dpkg.stdout, mode = 'r|')
        for member in tar.getmembers():
            if not member.isdir():
                name = normpath(member.name)
                # enforce proper utf-8 encoding
                try:
                    name.decode('utf-8')
                except UnicodeDecodeError:
                    name = name.decode('iso8859-1').encode('utf-8')
                yield name
        tar.close()
        dpkg.stdout.close()
        dpkg.wait()

    def read_control(self):
        '''
        Reads the control information from a binary.

        @rtype: text
        @return: stanza text of the control section.
        '''
        import utils
        fullpath = self.poolfile.fullpath
        deb_file = open(fullpath, 'r')
        stanza = utils.deb_extract_control(deb_file)
        deb_file.close()

        return stanza

    def read_control_fields(self):
        '''
        Reads the control information from a binary and return
        as a dictionary.

        @rtype: dict
        @return: fields of the control section as a dictionary.
        '''
        stanza = self.read_control()
        return apt_pkg.TagSection(stanza)

__all__.append('DBBinary')

@session_wrapper
def get_suites_binary_in(package, session=None):
    """
    Returns list of Suite objects which given C{package} name is in

    @type package: str
    @param package: DBBinary package name to search for

    @rtype: list
    @return: list of Suite objects for the given package
    """

    return session.query(Suite).filter(Suite.binaries.any(DBBinary.package == package)).all()

__all__.append('get_suites_binary_in')

@session_wrapper
def get_component_by_package_suite(package, suite_list, arch_list=[], session=None):
    '''
    Returns the component name of the newest binary package in suite_list or
    None if no package is found. The result can be optionally filtered by a list
    of architecture names.

    @type package: str
    @param package: DBBinary package name to search for

    @type suite_list: list of str
    @param suite_list: list of suite_name items

    @type arch_list: list of str
    @param arch_list: optional list of arch_string items that defaults to []

    @rtype: str or NoneType
    @return: name of component or None
    '''

    q = session.query(DBBinary).filter_by(package = package). \
        join(DBBinary.suites).filter(Suite.suite_name.in_(suite_list))
    if len(arch_list) > 0:
        q = q.join(DBBinary.architecture). \
            filter(Architecture.arch_string.in_(arch_list))
    binary = q.order_by(desc(DBBinary.version)).first()
    if binary is None:
        return None
    else:
        return binary.poolfile.component.component_name

__all__.append('get_component_by_package_suite')

################################################################################

class BuildQueue(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BuildQueue %s>' % self.queue_name

__all__.append('BuildQueue')

################################################################################

class Component(ORMObject):
    def __init__(self, component_name = None):
        self.component_name = component_name

    def __eq__(self, val):
        if isinstance(val, str):
            return (self.component_name == val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            return (self.component_name != val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def properties(self):
        return ['component_name', 'component_id', 'description', \
            'meets_dfsg', 'overrides_count']

    def not_null_constraints(self):
        return ['component_name']


__all__.append('Component')

@session_wrapper
def get_component(component, session=None):
    """
    Returns database id for given C{component}.

    @type component: string
    @param component: The name of the override type

    @rtype: int
    @return: the database id for the given component

    """
    component = component.lower()

    q = session.query(Component).filter_by(component_name=component)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_component')

@session_wrapper
def get_mapped_component(component_name, session=None):
    """get component after mappings

    Evaluate component mappings from ComponentMappings in dak.conf for the
    given component name.

    @todo: ansgar wants to get rid of this. It's currently only used for
           the security archive

    @type  component_name: str
    @param component_name: component name

    @param session: database session

    @rtype:  L{daklib.dbconn.Component} or C{None}
    @return: component after applying maps or C{None}
    """
    cnf = Config()
    for m in cnf.value_list("ComponentMappings"):
        (src, dst) = m.split()
        if component_name == src:
            component_name = dst
    component = session.query(Component).filter_by(component_name=component_name).first()
    return component

__all__.append('get_mapped_component')

@session_wrapper
def get_component_names(session=None):
    """
    Returns list of strings of component names.

    @rtype: list
    @return: list of strings of component names
    """

    return [ x.component_name for x in session.query(Component).all() ]

__all__.append('get_component_names')

################################################################################

class DBConfig(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBConfig %s>' % self.name

__all__.append('DBConfig')

################################################################################

@session_wrapper
def get_or_set_contents_file_id(filename, session=None):
    """
    Returns database id for given filename.

    If no matching file is found, a row is inserted.

    @type filename: string
    @param filename: The filename
    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).  If not passed, a commit will be performed at
    the end of the function, otherwise the caller is responsible for commiting.

    @rtype: int
    @return: the database id for the given component
    """

    q = session.query(ContentFilename).filter_by(filename=filename)

    try:
        ret = q.one().cafilename_id
    except NoResultFound:
        cf = ContentFilename()
        cf.filename = filename
        session.add(cf)
        session.commit_or_flush()
        ret = cf.cafilename_id

    return ret

__all__.append('get_or_set_contents_file_id')

@session_wrapper
def get_contents(suite, overridetype, section=None, session=None):
    """
    Returns contents for a suite / overridetype combination, limiting
    to a section if not None.

    @type suite: Suite
    @param suite: Suite object

    @type overridetype: OverrideType
    @param overridetype: OverrideType object

    @type section: Section
    @param section: Optional section object to limit results to

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: ResultsProxy
    @return: ResultsProxy object set up to return tuples of (filename, section,
    package, arch_id)
    """

    # find me all of the contents for a given suite
    contents_q = """SELECT (p.path||'/'||n.file) AS fn,
                            s.section,
                            b.package,
                            b.architecture
                   FROM content_associations c join content_file_paths p ON (c.filepath=p.id)
                   JOIN content_file_names n ON (c.filename=n.id)
                   JOIN binaries b ON (b.id=c.binary_pkg)
                   JOIN override o ON (o.package=b.package)
                   JOIN section s ON (s.id=o.section)
                   WHERE o.suite = :suiteid AND o.type = :overridetypeid
                   AND b.type=:overridetypename"""

    vals = {'suiteid': suite.suite_id,
            'overridetypeid': overridetype.overridetype_id,
            'overridetypename': overridetype.overridetype}

    if section is not None:
        contents_q += " AND s.id = :sectionid"
        vals['sectionid'] = section.section_id

    contents_q += " ORDER BY fn"

    return session.execute(contents_q, vals)

__all__.append('get_contents')

################################################################################

class ContentFilepath(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ContentFilepath %s>' % self.filepath

__all__.append('ContentFilepath')

@session_wrapper
def get_or_set_contents_path_id(filepath, session=None):
    """
    Returns database id for given path.

    If no matching file is found, a row is inserted.

    @type filepath: string
    @param filepath: The filepath

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).  If not passed, a commit will be performed at
    the end of the function, otherwise the caller is responsible for commiting.

    @rtype: int
    @return: the database id for the given path
    """

    q = session.query(ContentFilepath).filter_by(filepath=filepath)

    try:
        ret = q.one().cafilepath_id
    except NoResultFound:
        cf = ContentFilepath()
        cf.filepath = filepath
        session.add(cf)
        session.commit_or_flush()
        ret = cf.cafilepath_id

    return ret

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
    will be performed at the end of the function, otherwise the caller is
    responsible for commiting.

    @return: True upon success
    """

    privatetrans = False
    if session is None:
        session = DBConn().session()
        privatetrans = True

    try:
        # Insert paths
        def generate_path_dicts():
            for fullpath in fullpaths:
                if fullpath.startswith( './' ):
                    fullpath = fullpath[2:]

                yield {'filename':fullpath, 'id': binary_id }

        for d in generate_path_dicts():
            session.execute( "INSERT INTO bin_contents ( file, binary_id ) VALUES ( :filename, :id )",
                         d )

        session.commit()
        if privatetrans:
            session.close()
        return True

    except:
        traceback.print_exc()

        # Only rollback if we set up the session ourself
        if privatetrans:
            session.rollback()
            session.close()

        return False

__all__.append('insert_content_paths')

################################################################################

class DSCFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DSCFile %s>' % self.dscfile_id

__all__.append('DSCFile')

@session_wrapper
def get_dscfiles(dscfile_id=None, source_id=None, poolfile_id=None, session=None):
    """
    Returns a list of DSCFiles which may be empty

    @type dscfile_id: int (optional)
    @param dscfile_id: the dscfile_id of the DSCFiles to find

    @type source_id: int (optional)
    @param source_id: the source id related to the DSCFiles to find

    @type poolfile_id: int (optional)
    @param poolfile_id: the poolfile id related to the DSCFiles to find

    @rtype: list
    @return: Possibly empty list of DSCFiles
    """

    q = session.query(DSCFile)

    if dscfile_id is not None:
        q = q.filter_by(dscfile_id=dscfile_id)

    if source_id is not None:
        q = q.filter_by(source_id=source_id)

    if poolfile_id is not None:
        q = q.filter_by(poolfile_id=poolfile_id)

    return q.all()

__all__.append('get_dscfiles')

################################################################################

class ExternalOverride(ORMObject):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ExternalOverride %s = %s: %s>' % (self.package, self.key, self.value)

__all__.append('ExternalOverride')

################################################################################

class PoolFile(ORMObject):
    def __init__(self, filename = None, filesize = -1, \
        md5sum = None):
        self.filename = filename
        self.filesize = filesize
        self.md5sum = md5sum

    @property
    def fullpath(self):
        session = DBConn().session().object_session(self)
        af = session.query(ArchiveFile).join(Archive) \
                    .filter(ArchiveFile.file == self) \
                    .order_by(Archive.tainted.desc()).first()
        return af.path

    @property
    def component(self):
        session = DBConn().session().object_session(self)
        component_id = session.query(ArchiveFile.component_id).filter(ArchiveFile.file == self) \
                              .group_by(ArchiveFile.component_id).one()
        return session.query(Component).get(component_id)

    @property
    def basename(self):
        return os.path.basename(self.filename)

    def is_valid(self, filesize = -1, md5sum = None):
        return self.filesize == long(filesize) and self.md5sum == md5sum

    def properties(self):
        return ['filename', 'file_id', 'filesize', 'md5sum', 'sha1sum', \
            'sha256sum', 'source', 'binary', 'last_used']

    def not_null_constraints(self):
        return ['filename', 'md5sum']

    def identical_to(self, filename):
        """
        compare size and hash with the given file

        @rtype: bool
        @return: true if the given file has the same size and hash as this object; false otherwise
        """
        st = os.stat(filename)
        if self.filesize != st.st_size:
            return False

        f = open(filename, "r")
        sha256sum = apt_pkg.sha256sum(f)
        if sha256sum != self.sha256sum:
            return False

        return True

__all__.append('PoolFile')

@session_wrapper
def get_poolfile_like_name(filename, session=None):
    """
    Returns an array of PoolFile objects which are like the given name

    @type filename: string
    @param filename: the filename of the file to check against the DB

    @rtype: array
    @return: array of PoolFile objects
    """

    # TODO: There must be a way of properly using bind parameters with %FOO%
    q = session.query(PoolFile).filter(PoolFile.filename.like('%%/%s' % filename))

    return q.all()

__all__.append('get_poolfile_like_name')

################################################################################

class Fingerprint(ORMObject):
    def __init__(self, fingerprint = None):
        self.fingerprint = fingerprint

    def properties(self):
        return ['fingerprint', 'fingerprint_id', 'keyring', 'uid', \
            'binary_reject']

    def not_null_constraints(self):
        return ['fingerprint']

__all__.append('Fingerprint')

@session_wrapper
def get_fingerprint(fpr, session=None):
    """
    Returns Fingerprint object for given fpr.

    @type fpr: string
    @param fpr: The fpr to find / add

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).

    @rtype: Fingerprint
    @return: the Fingerprint object for the given fpr or None
    """

    q = session.query(Fingerprint).filter_by(fingerprint=fpr)

    try:
        ret = q.one()
    except NoResultFound:
        ret = None

    return ret

__all__.append('get_fingerprint')

@session_wrapper
def get_or_set_fingerprint(fpr, session=None):
    """
    Returns Fingerprint object for given fpr.

    If no matching fpr is found, a row is inserted.

    @type fpr: string
    @param fpr: The fpr to find / add

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).  If not passed, a commit will be performed at
    the end of the function, otherwise the caller is responsible for commiting.
    A flush will be performed either way.

    @rtype: Fingerprint
    @return: the Fingerprint object for the given fpr
    """

    q = session.query(Fingerprint).filter_by(fingerprint=fpr)

    try:
        ret = q.one()
    except NoResultFound:
        fingerprint = Fingerprint()
        fingerprint.fingerprint = fpr
        session.add(fingerprint)
        session.commit_or_flush()
        ret = fingerprint

    return ret

__all__.append('get_or_set_fingerprint')

################################################################################

# Helper routine for Keyring class
def get_ldap_name(entry):
    name = []
    for k in ["cn", "mn", "sn"]:
        ret = entry.get(k)
        if ret and ret[0] != "" and ret[0] != "-":
            name.append(ret[0])
    return " ".join(name)

################################################################################

class Keyring(object):
    gpg_invocation = "gpg --no-default-keyring --keyring %s" +\
                     " --with-colons --fingerprint --fingerprint"

    keys = {}
    fpr_lookup = {}

    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Keyring %s>' % self.keyring_name

    def de_escape_gpg_str(self, txt):
        esclist = re.split(r'(\\x..)', txt)
        for x in range(1,len(esclist),2):
            esclist[x] = "%c" % (int(esclist[x][2:],16))
        return "".join(esclist)

    def parse_address(self, uid):
        """parses uid and returns a tuple of real name and email address"""
        import email.Utils
        (name, address) = email.Utils.parseaddr(uid)
        name = re.sub(r"\s*[(].*[)]", "", name)
        name = self.de_escape_gpg_str(name)
        if name == "":
            name = uid
        return (name, address)

    def load_keys(self, keyring):
        if not self.keyring_id:
            raise Exception('Must be initialized with database information')

        k = os.popen(self.gpg_invocation % keyring, "r")
        key = None
        need_fingerprint = False

        for line in k:
            field = line.split(":")
            if field[0] == "pub":
                key = field[4]
                self.keys[key] = {}
                (name, addr) = self.parse_address(field[9])
                if "@" in addr:
                    self.keys[key]["email"] = addr
                    self.keys[key]["name"] = name
                need_fingerprint = True
            elif key and field[0] == "uid":
                (name, addr) = self.parse_address(field[9])
                if "email" not in self.keys[key] and "@" in addr:
                    self.keys[key]["email"] = addr
                    self.keys[key]["name"] = name
            elif need_fingerprint and field[0] == "fpr":
                self.keys[key]["fingerprints"] = [field[9]]
                self.fpr_lookup[field[9]] = key
                need_fingerprint = False

    def import_users_from_ldap(self, session):
        import ldap
        cnf = Config()

        LDAPDn = cnf["Import-LDAP-Fingerprints::LDAPDn"]
        LDAPServer = cnf["Import-LDAP-Fingerprints::LDAPServer"]
        ca_cert_file = cnf.get('Import-LDAP-Fingerprints::CACertFile')

        l = ldap.open(LDAPServer)

        if ca_cert_file:
            # TODO: This should request a new context and use
            # connection-specific options (i.e. "l.set_option(...)")

            # Request a new TLS context. If there was already one, libldap
            # would not change the TLS options (like which CAs to trust).
            #l.set_option(ldap.OPT_X_TLS_NEWCTX, True)
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_HARD)
            #ldap.set_option(ldap.OPT_X_TLS_CACERTDIR, None)
            ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, ca_cert_file)
            l.start_tls_s()

        l.simple_bind_s("","")
        Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
               "(&(keyfingerprint=*)(gidnumber=%s))" % (cnf["Import-Users-From-Passwd::ValidGID"]),
               ["uid", "keyfingerprint", "cn", "mn", "sn"])

        ldap_fin_uid_id = {}

        byuid = {}
        byname = {}

        for i in Attrs:
            entry = i[1]
            uid = entry["uid"][0]
            name = get_ldap_name(entry)
            fingerprints = entry["keyFingerPrint"]
            keyid = None
            for f in fingerprints:
                key = self.fpr_lookup.get(f, None)
                if key not in self.keys:
                    continue
                self.keys[key]["uid"] = uid

                if keyid != None:
                    continue
                keyid = get_or_set_uid(uid, session).uid_id
                byuid[keyid] = (uid, name)
                byname[uid] = (keyid, name)

        return (byname, byuid)

    def generate_users_from_keyring(self, format, session):
        byuid = {}
        byname = {}
        any_invalid = False
        for x in self.keys.keys():
            if "email" not in self.keys[x]:
                any_invalid = True
                self.keys[x]["uid"] = format % "invalid-uid"
            else:
                uid = format % self.keys[x]["email"]
                keyid = get_or_set_uid(uid, session).uid_id
                byuid[keyid] = (uid, self.keys[x]["name"])
                byname[uid] = (keyid, self.keys[x]["name"])
                self.keys[x]["uid"] = uid

        if any_invalid:
            uid = format % "invalid-uid"
            keyid = get_or_set_uid(uid, session).uid_id
            byuid[keyid] = (uid, "ungeneratable user id")
            byname[uid] = (keyid, "ungeneratable user id")

        return (byname, byuid)

__all__.append('Keyring')

@session_wrapper
def get_keyring(keyring, session=None):
    """
    If C{keyring} does not have an entry in the C{keyrings} table yet, return None
    If C{keyring} already has an entry, simply return the existing Keyring

    @type keyring: string
    @param keyring: the keyring name

    @rtype: Keyring
    @return: the Keyring object for this keyring
    """

    q = session.query(Keyring).filter_by(keyring_name=keyring)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_keyring')

@session_wrapper
def get_active_keyring_paths(session=None):
    """
    @rtype: list
    @return: list of active keyring paths
    """
    return [ x.keyring_name for x in session.query(Keyring).filter(Keyring.active == True).order_by(desc(Keyring.priority)).all() ]

__all__.append('get_active_keyring_paths')

@session_wrapper
def get_primary_keyring_path(session=None):
    """
    Get the full path to the highest priority active keyring

    @rtype: str or None
    @return: path to the active keyring with the highest priority or None if no
             keyring is configured
    """
    keyrings = get_active_keyring_paths()

    if len(keyrings) > 0:
        return keyrings[0]
    else:
        return None

__all__.append('get_primary_keyring_path')

################################################################################

class DBChange(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBChange %s>' % self.changesname

__all__.append('DBChange')

@session_wrapper
def get_dbchange(filename, session=None):
    """
    returns DBChange object for given C{filename}.

    @type filename: string
    @param filename: the name of the file

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: DBChange
    @return:  DBChange object for the given filename (C{None} if not present)

    """
    q = session.query(DBChange).filter_by(changesname=filename)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_dbchange')

################################################################################

class Maintainer(ORMObject):
    def __init__(self, name = None):
        self.name = name

    def properties(self):
        return ['name', 'maintainer_id']

    def not_null_constraints(self):
        return ['name']

    def get_split_maintainer(self):
        if not hasattr(self, 'name') or self.name is None:
            return ('', '', '', '')

        return fix_maintainer(self.name.strip())

__all__.append('Maintainer')

@session_wrapper
def get_or_set_maintainer(name, session=None):
    """
    Returns Maintainer object for given maintainer name.

    If no matching maintainer name is found, a row is inserted.

    @type name: string
    @param name: The maintainer name to add

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).  If not passed, a commit will be performed at
    the end of the function, otherwise the caller is responsible for commiting.
    A flush will be performed either way.

    @rtype: Maintainer
    @return: the Maintainer object for the given maintainer
    """

    q = session.query(Maintainer).filter_by(name=name)
    try:
        ret = q.one()
    except NoResultFound:
        maintainer = Maintainer()
        maintainer.name = name
        session.add(maintainer)
        session.commit_or_flush()
        ret = maintainer

    return ret

__all__.append('get_or_set_maintainer')

@session_wrapper
def get_maintainer(maintainer_id, session=None):
    """
    Return the name of the maintainer behind C{maintainer_id} or None if that
    maintainer_id is invalid.

    @type maintainer_id: int
    @param maintainer_id: the id of the maintainer

    @rtype: Maintainer
    @return: the Maintainer with this C{maintainer_id}
    """

    return session.query(Maintainer).get(maintainer_id)

__all__.append('get_maintainer')

################################################################################

class NewComment(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '''<NewComment for '%s %s' (%s)>''' % (self.package, self.version, self.comment_id)

__all__.append('NewComment')

@session_wrapper
def has_new_comment(policy_queue, package, version, session=None):
    """
    Returns true if the given combination of C{package}, C{version} has a comment.

    @type package: string
    @param package: name of the package

    @type version: string
    @param version: package version

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: boolean
    @return: true/false
    """

    q = session.query(NewComment).filter_by(policy_queue=policy_queue)
    q = q.filter_by(package=package)
    q = q.filter_by(version=version)

    return bool(q.count() > 0)

__all__.append('has_new_comment')

@session_wrapper
def get_new_comments(policy_queue, package=None, version=None, comment_id=None, session=None):
    """
    Returns (possibly empty) list of NewComment objects for the given
    parameters

    @type package: string (optional)
    @param package: name of the package

    @type version: string (optional)
    @param version: package version

    @type comment_id: int (optional)
    @param comment_id: An id of a comment

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: A (possibly empty) list of NewComment objects will be returned
    """

    q = session.query(NewComment).filter_by(policy_queue=policy_queue)
    if package is not None: q = q.filter_by(package=package)
    if version is not None: q = q.filter_by(version=version)
    if comment_id is not None: q = q.filter_by(comment_id=comment_id)

    return q.all()

__all__.append('get_new_comments')

################################################################################

class Override(ORMObject):
    def __init__(self, package = None, suite = None, component = None, overridetype = None, \
        section = None, priority = None):
        self.package = package
        self.suite = suite
        self.component = component
        self.overridetype = overridetype
        self.section = section
        self.priority = priority

    def properties(self):
        return ['package', 'suite', 'component', 'overridetype', 'section', \
            'priority']

    def not_null_constraints(self):
        return ['package', 'suite', 'component', 'overridetype', 'section']

__all__.append('Override')

@session_wrapper
def get_override(package, suite=None, component=None, overridetype=None, session=None):
    """
    Returns Override object for the given parameters

    @type package: string
    @param package: The name of the package

    @type suite: string, list or None
    @param suite: The name of the suite (or suites if a list) to limit to.  If
                  None, don't limit.  Defaults to None.

    @type component: string, list or None
    @param component: The name of the component (or components if a list) to
                      limit to.  If None, don't limit.  Defaults to None.

    @type overridetype: string, list or None
    @param overridetype: The name of the overridetype (or overridetypes if a list) to
                         limit to.  If None, don't limit.  Defaults to None.

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: A (possibly empty) list of Override objects will be returned
    """

    q = session.query(Override)
    q = q.filter_by(package=package)

    if suite is not None:
        if not isinstance(suite, list): suite = [suite]
        q = q.join(Suite).filter(Suite.suite_name.in_(suite))

    if component is not None:
        if not isinstance(component, list): component = [component]
        q = q.join(Component).filter(Component.component_name.in_(component))

    if overridetype is not None:
        if not isinstance(overridetype, list): overridetype = [overridetype]
        q = q.join(OverrideType).filter(OverrideType.overridetype.in_(overridetype))

    return q.all()

__all__.append('get_override')


################################################################################

class OverrideType(ORMObject):
    def __init__(self, overridetype = None):
        self.overridetype = overridetype

    def properties(self):
        return ['overridetype', 'overridetype_id', 'overrides_count']

    def not_null_constraints(self):
        return ['overridetype']

__all__.append('OverrideType')

@session_wrapper
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

    q = session.query(OverrideType).filter_by(overridetype=override_type)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_override_type')

################################################################################

class PolicyQueue(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<PolicyQueue %s>' % self.queue_name

__all__.append('PolicyQueue')

@session_wrapper
def get_policy_queue(queuename, session=None):
    """
    Returns PolicyQueue object for given C{queue name}

    @type queuename: string
    @param queuename: The name of the queue

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: PolicyQueue
    @return: PolicyQueue object for the given queue
    """

    q = session.query(PolicyQueue).filter_by(queue_name=queuename)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_policy_queue')

################################################################################

class PolicyQueueUpload(object):
    def __cmp__(self, other):
        ret = cmp(self.changes.source, other.changes.source)
        if ret == 0:
            ret = apt_pkg.version_compare(self.changes.version, other.changes.version)
        if ret == 0:
            if self.source is not None and other.source is None:
                ret = -1
            elif self.source is None and other.source is not None:
                ret = 1
        if ret == 0:
            ret = cmp(self.changes.changesname, other.changes.changesname)
        return ret

__all__.append('PolicyQueueUpload')

################################################################################

class PolicyQueueByhandFile(object):
    pass

__all__.append('PolicyQueueByhandFile')

################################################################################

class Priority(ORMObject):
    def __init__(self, priority = None, level = None):
        self.priority = priority
        self.level = level

    def properties(self):
        return ['priority', 'priority_id', 'level', 'overrides_count']

    def not_null_constraints(self):
        return ['priority', 'level']

    def __eq__(self, val):
        if isinstance(val, str):
            return (self.priority == val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            return (self.priority != val)
        # This signals to use the normal comparison operator
        return NotImplemented

__all__.append('Priority')

@session_wrapper
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

    q = session.query(Priority).filter_by(priority=priority)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_priority')

@session_wrapper
def get_priorities(session=None):
    """
    Returns dictionary of priority names -> id mappings

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: dictionary
    @return: dictionary of priority names -> id mappings
    """

    ret = {}
    q = session.query(Priority)
    for x in q.all():
        ret[x.priority] = x.priority_id

    return ret

__all__.append('get_priorities')

################################################################################

class Section(ORMObject):
    def __init__(self, section = None):
        self.section = section

    def properties(self):
        return ['section', 'section_id', 'overrides_count']

    def not_null_constraints(self):
        return ['section']

    def __eq__(self, val):
        if isinstance(val, str):
            return (self.section == val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            return (self.section != val)
        # This signals to use the normal comparison operator
        return NotImplemented

__all__.append('Section')

@session_wrapper
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

    q = session.query(Section).filter_by(section=section)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_section')

@session_wrapper
def get_sections(session=None):
    """
    Returns dictionary of section names -> id mappings

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: dictionary
    @return: dictionary of section names -> id mappings
    """

    ret = {}
    q = session.query(Section)
    for x in q.all():
        ret[x.section] = x.section_id

    return ret

__all__.append('get_sections')

################################################################################

class SignatureHistory(ORMObject):
    @classmethod
    def from_signed_file(cls, signed_file):
        """signature history entry from signed file

        @type  signed_file: L{daklib.gpg.SignedFile}
        @param signed_file: signed file

        @rtype: L{SignatureHistory}
        """
        self = cls()
        self.fingerprint = signed_file.primary_fingerprint
        self.signature_timestamp = signed_file.signature_timestamp
        self.contents_sha1 = signed_file.contents_sha1()
        return self

__all__.append('SignatureHistory')

################################################################################

class SrcContents(ORMObject):
    def __init__(self, file = None, source = None):
        self.file = file
        self.source = source

    def properties(self):
        return ['file', 'source']

__all__.append('SrcContents')

################################################################################

from debian.debfile import Deb822

# Temporary Deb822 subclass to fix bugs with : handling; see #597249
class Dak822(Deb822):
    def _internal_parser(self, sequence, fields=None):
        # The key is non-whitespace, non-colon characters before any colon.
        key_part = r"^(?P<key>[^: \t\n\r\f\v]+)\s*:\s*"
        single = re.compile(key_part + r"(?P<data>\S.*?)\s*$")
        multi = re.compile(key_part + r"$")
        multidata = re.compile(r"^\s(?P<data>.+?)\s*$")

        wanted_field = lambda f: fields is None or f in fields

        if isinstance(sequence, basestring):
            sequence = sequence.splitlines()

        curkey = None
        content = ""
        for line in self.gpg_stripped_paragraph(sequence):
            m = single.match(line)
            if m:
                if curkey:
                    self[curkey] = content

                if not wanted_field(m.group('key')):
                    curkey = None
                    continue

                curkey = m.group('key')
                content = m.group('data')
                continue

            m = multi.match(line)
            if m:
                if curkey:
                    self[curkey] = content

                if not wanted_field(m.group('key')):
                    curkey = None
                    continue

                curkey = m.group('key')
                content = ""
                continue

            m = multidata.match(line)
            if m:
                content += '\n' + line # XXX not m.group('data')?
                continue

        if curkey:
            self[curkey] = content


class DBSource(ORMObject):
    def __init__(self, source = None, version = None, maintainer = None, \
        changedby = None, poolfile = None, install_date = None, fingerprint = None):
        self.source = source
        self.version = version
        self.maintainer = maintainer
        self.changedby = changedby
        self.poolfile = poolfile
        self.install_date = install_date
        self.fingerprint = fingerprint

    @property
    def pkid(self):
        return self.source_id

    def properties(self):
        return ['source', 'source_id', 'maintainer', 'changedby', \
            'fingerprint', 'poolfile', 'version', 'suites_count', \
            'install_date', 'binaries_count', 'uploaders_count']

    def not_null_constraints(self):
        return ['source', 'version', 'install_date', 'maintainer', \
            'changedby', 'poolfile']

    def read_control_fields(self):
        '''
        Reads the control information from a dsc

        @rtype: tuple
        @return: fields is the dsc information in a dictionary form
        '''
        fullpath = self.poolfile.fullpath
        fields = Dak822(open(self.poolfile.fullpath, 'r'))
        return fields

    metadata = association_proxy('key', 'value')

    def scan_contents(self):
        '''
        Returns a set of names for non directories. The path names are
        normalized after converting them from either utf-8 or iso8859-1
        encoding.
        '''
        fullpath = self.poolfile.fullpath
        from daklib.contents import UnpackedSource
        unpacked = UnpackedSource(fullpath)
        fileset = set()
        for name in unpacked.get_all_filenames():
            # enforce proper utf-8 encoding
            try:
                name.decode('utf-8')
            except UnicodeDecodeError:
                name = name.decode('iso8859-1').encode('utf-8')
            fileset.add(name)
        return fileset

__all__.append('DBSource')

@session_wrapper
def source_exists(source, source_version, suites = ["any"], session=None):
    """
    Ensure that source exists somewhere in the archive for the binary
    upload being processed.
      1. exact match     => 1.0-3
      2. bin-only NMU    => 1.0-3+b1 , 1.0-3.1+b1

    @type source: string
    @param source: source name

    @type source_version: string
    @param source_version: expected source version

    @type suites: list
    @param suites: list of suites to check in, default I{any}

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: int
    @return: returns 1 if a source with expected version is found, otherwise 0

    """

    cnf = Config()
    ret = True

    from daklib.regexes import re_bin_only_nmu
    orig_source_version = re_bin_only_nmu.sub('', source_version)

    for suite in suites:
        q = session.query(DBSource).filter_by(source=source). \
            filter(DBSource.version.in_([source_version, orig_source_version]))
        if suite != "any":
            # source must exist in 'suite' or a suite that is enhanced by 'suite'
            s = get_suite(suite, session)
            if s:
                enhances_vcs = session.query(VersionCheck).filter(VersionCheck.suite==s).filter_by(check='Enhances')
                considered_suites = [ vc.reference for vc in enhances_vcs ]
                considered_suites.append(s)

                q = q.filter(DBSource.suites.any(Suite.suite_id.in_([s.suite_id for s in considered_suites])))

        if q.count() > 0:
            continue

        # No source found so return not ok
        ret = False

    return ret

__all__.append('source_exists')

@session_wrapper
def get_suites_source_in(source, session=None):
    """
    Returns list of Suite objects which given C{source} name is in

    @type source: str
    @param source: DBSource package name to search for

    @rtype: list
    @return: list of Suite objects for the given source
    """

    return session.query(Suite).filter(Suite.sources.any(source=source)).all()

__all__.append('get_suites_source_in')

@session_wrapper
def get_sources_from_name(source, version=None, dm_upload_allowed=None, session=None):
    """
    Returns list of DBSource objects for given C{source} name and other parameters

    @type source: str
    @param source: DBSource package name to search for

    @type version: str or None
    @param version: DBSource version name to search for or None if not applicable

    @type dm_upload_allowed: bool
    @param dm_upload_allowed: If None, no effect.  If True or False, only
    return packages with that dm_upload_allowed setting

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of DBSource objects for the given name (may be empty)
    """

    q = session.query(DBSource).filter_by(source=source)

    if version is not None:
        q = q.filter_by(version=version)

    if dm_upload_allowed is not None:
        q = q.filter_by(dm_upload_allowed=dm_upload_allowed)

    return q.all()

__all__.append('get_sources_from_name')

# FIXME: This function fails badly if it finds more than 1 source package and
# its implementation is trivial enough to be inlined.
@session_wrapper
def get_source_in_suite(source, suite, session=None):
    """
    Returns a DBSource object for a combination of C{source} and C{suite}.

      - B{source} - source package name, eg. I{mailfilter}, I{bbdb}, I{glibc}
      - B{suite} - a suite name, eg. I{unstable}

    @type source: string
    @param source: source package name

    @type suite: string
    @param suite: the suite name

    @rtype: string
    @return: the version for I{source} in I{suite}

    """

    q = get_suite(suite, session).get_sources(source)
    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_source_in_suite')

@session_wrapper
def import_metadata_into_db(obj, session=None):
    """
    This routine works on either DBBinary or DBSource objects and imports
    their metadata into the database
    """
    fields = obj.read_control_fields()
    for k in fields.keys():
        try:
            # Try raw ASCII
            val = str(fields[k])
        except UnicodeEncodeError:
            # Fall back to UTF-8
            try:
                val = fields[k].encode('utf-8')
            except UnicodeEncodeError:
                # Finally try iso8859-1
                val = fields[k].encode('iso8859-1')
                # Otherwise we allow the exception to percolate up and we cause
                # a reject as someone is playing silly buggers

        obj.metadata[get_or_set_metadatakey(k, session)] = val

    session.commit_or_flush()

__all__.append('import_metadata_into_db')

################################################################################

class SrcFormat(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcFormat %s>' % (self.format_name)

__all__.append('SrcFormat')

################################################################################

SUITE_FIELDS = [ ('SuiteName', 'suite_name'),
                 ('SuiteID', 'suite_id'),
                 ('Version', 'version'),
                 ('Origin', 'origin'),
                 ('Label', 'label'),
                 ('Description', 'description'),
                 ('Untouchable', 'untouchable'),
                 ('Announce', 'announce'),
                 ('Codename', 'codename'),
                 ('OverrideCodename', 'overridecodename'),
                 ('ValidTime', 'validtime'),
                 ('Priority', 'priority'),
                 ('NotAutomatic', 'notautomatic'),
                 ('CopyChanges', 'copychanges'),
                 ('OverrideSuite', 'overridesuite')]

# Why the heck don't we have any UNIQUE constraints in table suite?
# TODO: Add UNIQUE constraints for appropriate columns.
class Suite(ORMObject):
    def __init__(self, suite_name = None, version = None):
        self.suite_name = suite_name
        self.version = version

    def properties(self):
        return ['suite_name', 'version', 'sources_count', 'binaries_count', \
            'overrides_count']

    def not_null_constraints(self):
        return ['suite_name']

    def __eq__(self, val):
        if isinstance(val, str):
            return (self.suite_name == val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            return (self.suite_name != val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def details(self):
        ret = []
        for disp, field in SUITE_FIELDS:
            val = getattr(self, field, None)
            if val is not None:
                ret.append("%s: %s" % (disp, val))

        return "\n".join(ret)

    def get_architectures(self, skipsrc=False, skipall=False):
        """
        Returns list of Architecture objects

        @type skipsrc: boolean
        @param skipsrc: Whether to skip returning the 'source' architecture entry
        (Default False)

        @type skipall: boolean
        @param skipall: Whether to skip returning the 'all' architecture entry
        (Default False)

        @rtype: list
        @return: list of Architecture objects for the given name (may be empty)
        """

        q = object_session(self).query(Architecture).with_parent(self)
        if skipsrc:
            q = q.filter(Architecture.arch_string != 'source')
        if skipall:
            q = q.filter(Architecture.arch_string != 'all')
        return q.order_by(Architecture.arch_string).all()

    def get_sources(self, source):
        """
        Returns a query object representing DBSource that is part of C{suite}.

          - B{source} - source package name, eg. I{mailfilter}, I{bbdb}, I{glibc}

        @type source: string
        @param source: source package name

        @rtype: sqlalchemy.orm.query.Query
        @return: a query of DBSource

        """

        session = object_session(self)
        return session.query(DBSource).filter_by(source = source). \
            with_parent(self)

    def get_overridesuite(self):
        if self.overridesuite is None:
            return self
        else:
            return object_session(self).query(Suite).filter_by(suite_name=self.overridesuite).one()

    @property
    def path(self):
        return os.path.join(self.archive.path, 'dists', self.suite_name)

__all__.append('Suite')

@session_wrapper
def get_suite(suite, session=None):
    """
    Returns Suite object for given C{suite name}.

    @type suite: string
    @param suite: The name of the suite

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Suite
    @return: Suite object for the requested suite name (None if not present)
    """

    q = session.query(Suite).filter_by(suite_name=suite)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_suite')

################################################################################

@session_wrapper
def get_suite_architectures(suite, skipsrc=False, skipall=False, session=None):
    """
    Returns list of Architecture objects for given C{suite} name. The list is
    empty if suite does not exist.

    @type suite: str
    @param suite: Suite name to search for

    @type skipsrc: boolean
    @param skipsrc: Whether to skip returning the 'source' architecture entry
    (Default False)

    @type skipall: boolean
    @param skipall: Whether to skip returning the 'all' architecture entry
    (Default False)

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of Architecture objects for the given name (may be empty)
    """

    try:
        return get_suite(suite, session).get_architectures(skipsrc, skipall)
    except AttributeError:
        return []

__all__.append('get_suite_architectures')

################################################################################

class Uid(ORMObject):
    def __init__(self, uid = None, name = None):
        self.uid = uid
        self.name = name

    def __eq__(self, val):
        if isinstance(val, str):
            return (self.uid == val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            return (self.uid != val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def properties(self):
        return ['uid', 'name', 'fingerprint']

    def not_null_constraints(self):
        return ['uid']

__all__.append('Uid')

@session_wrapper
def get_or_set_uid(uidname, session=None):
    """
    Returns uid object for given uidname.

    If no matching uidname is found, a row is inserted.

    @type uidname: string
    @param uidname: The uid to add

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).  If not passed, a commit will be performed at
    the end of the function, otherwise the caller is responsible for commiting.

    @rtype: Uid
    @return: the uid object for the given uidname
    """

    q = session.query(Uid).filter_by(uid=uidname)

    try:
        ret = q.one()
    except NoResultFound:
        uid = Uid()
        uid.uid = uidname
        session.add(uid)
        session.commit_or_flush()
        ret = uid

    return ret

__all__.append('get_or_set_uid')

@session_wrapper
def get_uid_from_fingerprint(fpr, session=None):
    q = session.query(Uid)
    q = q.join(Fingerprint).filter_by(fingerprint=fpr)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_uid_from_fingerprint')

################################################################################

class MetadataKey(ORMObject):
    def __init__(self, key = None):
        self.key = key

    def properties(self):
        return ['key']

    def not_null_constraints(self):
        return ['key']

__all__.append('MetadataKey')

@session_wrapper
def get_or_set_metadatakey(keyname, session=None):
    """
    Returns MetadataKey object for given uidname.

    If no matching keyname is found, a row is inserted.

    @type uidname: string
    @param uidname: The keyname to add

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).  If not passed, a commit will be performed at
    the end of the function, otherwise the caller is responsible for commiting.

    @rtype: MetadataKey
    @return: the metadatakey object for the given keyname
    """

    q = session.query(MetadataKey).filter_by(key=keyname)

    try:
        ret = q.one()
    except NoResultFound:
        ret = MetadataKey(keyname)
        session.add(ret)
        session.commit_or_flush()

    return ret

__all__.append('get_or_set_metadatakey')

################################################################################

class BinaryMetadata(ORMObject):
    def __init__(self, key = None, value = None, binary = None):
        self.key = key
        self.value = value
        self.binary = binary

    def properties(self):
        return ['binary', 'key', 'value']

    def not_null_constraints(self):
        return ['value']

__all__.append('BinaryMetadata')

################################################################################

class SourceMetadata(ORMObject):
    def __init__(self, key = None, value = None, source = None):
        self.key = key
        self.value = value
        self.source = source

    def properties(self):
        return ['source', 'key', 'value']

    def not_null_constraints(self):
        return ['value']

__all__.append('SourceMetadata')

################################################################################

class VersionCheck(ORMObject):
    def __init__(self, *args, **kwargs):
	pass

    def properties(self):
        #return ['suite_id', 'check', 'reference_id']
        return ['check']

    def not_null_constraints(self):
        return ['suite', 'check', 'reference']

__all__.append('VersionCheck')

@session_wrapper
def get_version_checks(suite_name, check = None, session = None):
    suite = get_suite(suite_name, session)
    if not suite:
        # Make sure that what we return is iterable so that list comprehensions
        # involving this don't cause a traceback
        return []
    q = session.query(VersionCheck).filter_by(suite=suite)
    if check:
        q = q.filter_by(check=check)
    return q.all()

__all__.append('get_version_checks')

################################################################################

class DBConn(object):
    """
    database module init.
    """
    __shared_state = {}

    def __init__(self, *args, **kwargs):
        self.__dict__ = self.__shared_state

        if not getattr(self, 'initialised', False):
            self.initialised = True
            self.debug = kwargs.has_key('debug')
            self.__createconn()

    def __setuptables(self):
        tables = (
            'acl',
            'acl_architecture_map',
            'acl_fingerprint_map',
            'acl_per_source',
            'architecture',
            'archive',
            'bin_associations',
            'bin_contents',
            'binaries',
            'binaries_metadata',
            'build_queue',
            'changelogs_text',
            'changes',
            'component',
            'component_suite',
            'config',
            'dsc_files',
            'external_overrides',
            'extra_src_references',
            'files',
            'files_archive_map',
            'fingerprint',
            'keyrings',
            'maintainer',
            'metadata_keys',
            'new_comments',
            # TODO: the maintainer column in table override should be removed.
            'override',
            'override_type',
            'policy_queue',
            'policy_queue_upload',
            'policy_queue_upload_binaries_map',
            'policy_queue_byhand_file',
            'priority',
            'section',
            'signature_history',
            'source',
            'source_metadata',
            'src_associations',
            'src_contents',
            'src_format',
            'src_uploaders',
            'suite',
            'suite_acl_map',
            'suite_architectures',
            'suite_build_queue_copy',
            'suite_src_formats',
            'uid',
            'version_check',
        )

        views = (
            'almost_obsolete_all_associations',
            'almost_obsolete_src_associations',
            'any_associations_source',
            'bin_associations_binaries',
            'binaries_suite_arch',
            'changelogs',
            'file_arch_suite',
            'newest_all_associations',
            'newest_any_associations',
            'newest_source',
            'newest_src_association',
            'obsolete_all_associations',
            'obsolete_any_associations',
            'obsolete_any_by_all_associations',
            'obsolete_src_associations',
            'source_suite',
            'src_associations_bin',
            'src_associations_src',
            'suite_arch_by_name',
        )

        for table_name in tables:
            table = Table(table_name, self.db_meta, \
                autoload=True, useexisting=True)
            setattr(self, 'tbl_%s' % table_name, table)

        for view_name in views:
            view = Table(view_name, self.db_meta, autoload=True)
            setattr(self, 'view_%s' % view_name, view)

    def __setupmappers(self):
        mapper(Architecture, self.tbl_architecture,
            properties = dict(arch_id = self.tbl_architecture.c.id,
               suites = relation(Suite, secondary=self.tbl_suite_architectures,
                   order_by=self.tbl_suite.c.suite_name,
                   backref=backref('architectures', order_by=self.tbl_architecture.c.arch_string))),
            extension = validator)

        mapper(ACL, self.tbl_acl,
               properties = dict(
                architectures = relation(Architecture, secondary=self.tbl_acl_architecture_map, collection_class=set),
                fingerprints = relation(Fingerprint, secondary=self.tbl_acl_fingerprint_map, collection_class=set),
                match_keyring = relation(Keyring, primaryjoin=(self.tbl_acl.c.match_keyring_id == self.tbl_keyrings.c.id)),
                per_source = relation(ACLPerSource, collection_class=set),
                ))

        mapper(ACLPerSource, self.tbl_acl_per_source,
               properties = dict(
                acl = relation(ACL),
                fingerprint = relation(Fingerprint, primaryjoin=(self.tbl_acl_per_source.c.fingerprint_id == self.tbl_fingerprint.c.id)),
                created_by = relation(Fingerprint, primaryjoin=(self.tbl_acl_per_source.c.created_by_id == self.tbl_fingerprint.c.id)),
                ))

        mapper(Archive, self.tbl_archive,
               properties = dict(archive_id = self.tbl_archive.c.id,
                                 archive_name = self.tbl_archive.c.name))

        mapper(ArchiveFile, self.tbl_files_archive_map,
               properties = dict(archive = relation(Archive, backref='files'),
                                 component = relation(Component),
                                 file = relation(PoolFile, backref='archives')))

        mapper(BuildQueue, self.tbl_build_queue,
               properties = dict(queue_id = self.tbl_build_queue.c.id,
                                 suite = relation(Suite, primaryjoin=(self.tbl_build_queue.c.suite_id==self.tbl_suite.c.id))))

        mapper(DBBinary, self.tbl_binaries,
               properties = dict(binary_id = self.tbl_binaries.c.id,
                                 package = self.tbl_binaries.c.package,
                                 version = self.tbl_binaries.c.version,
                                 maintainer_id = self.tbl_binaries.c.maintainer,
                                 maintainer = relation(Maintainer),
                                 source_id = self.tbl_binaries.c.source,
                                 source = relation(DBSource, backref='binaries'),
                                 arch_id = self.tbl_binaries.c.architecture,
                                 architecture = relation(Architecture),
                                 poolfile_id = self.tbl_binaries.c.file,
                                 poolfile = relation(PoolFile),
                                 binarytype = self.tbl_binaries.c.type,
                                 fingerprint_id = self.tbl_binaries.c.sig_fpr,
                                 fingerprint = relation(Fingerprint),
                                 install_date = self.tbl_binaries.c.install_date,
                                 suites = relation(Suite, secondary=self.tbl_bin_associations,
                                     backref=backref('binaries', lazy='dynamic')),
                                 extra_sources = relation(DBSource, secondary=self.tbl_extra_src_references,
                                     backref=backref('extra_binary_references', lazy='dynamic')),
                                 key = relation(BinaryMetadata, cascade='all',
                                     collection_class=attribute_mapped_collection('key'))),
                extension = validator)

        mapper(Component, self.tbl_component,
               properties = dict(component_id = self.tbl_component.c.id,
                                 component_name = self.tbl_component.c.name),
               extension = validator)

        mapper(DBConfig, self.tbl_config,
               properties = dict(config_id = self.tbl_config.c.id))

        mapper(DSCFile, self.tbl_dsc_files,
               properties = dict(dscfile_id = self.tbl_dsc_files.c.id,
                                 source_id = self.tbl_dsc_files.c.source,
                                 source = relation(DBSource),
                                 poolfile_id = self.tbl_dsc_files.c.file,
                                 poolfile = relation(PoolFile)))

        mapper(ExternalOverride, self.tbl_external_overrides,
                properties = dict(
                    suite_id = self.tbl_external_overrides.c.suite,
                    suite = relation(Suite),
                    component_id = self.tbl_external_overrides.c.component,
                    component = relation(Component)))

        mapper(PoolFile, self.tbl_files,
               properties = dict(file_id = self.tbl_files.c.id,
                                 filesize = self.tbl_files.c.size),
                extension = validator)

        mapper(Fingerprint, self.tbl_fingerprint,
               properties = dict(fingerprint_id = self.tbl_fingerprint.c.id,
                                 uid_id = self.tbl_fingerprint.c.uid,
                                 uid = relation(Uid),
                                 keyring_id = self.tbl_fingerprint.c.keyring,
                                 keyring = relation(Keyring),
                                 acl = relation(ACL)),
               extension = validator)

        mapper(Keyring, self.tbl_keyrings,
               properties = dict(keyring_name = self.tbl_keyrings.c.name,
                                 keyring_id = self.tbl_keyrings.c.id,
                                 acl = relation(ACL, primaryjoin=(self.tbl_keyrings.c.acl_id == self.tbl_acl.c.id)))),

        mapper(DBChange, self.tbl_changes,
               properties = dict(change_id = self.tbl_changes.c.id,
                                 seen = self.tbl_changes.c.seen,
                                 source = self.tbl_changes.c.source,
                                 binaries = self.tbl_changes.c.binaries,
                                 architecture = self.tbl_changes.c.architecture,
                                 distribution = self.tbl_changes.c.distribution,
                                 urgency = self.tbl_changes.c.urgency,
                                 maintainer = self.tbl_changes.c.maintainer,
                                 changedby = self.tbl_changes.c.changedby,
                                 date = self.tbl_changes.c.date,
                                 version = self.tbl_changes.c.version))

        mapper(Maintainer, self.tbl_maintainer,
               properties = dict(maintainer_id = self.tbl_maintainer.c.id,
                   maintains_sources = relation(DBSource, backref='maintainer',
                       primaryjoin=(self.tbl_maintainer.c.id==self.tbl_source.c.maintainer)),
                   changed_sources = relation(DBSource, backref='changedby',
                       primaryjoin=(self.tbl_maintainer.c.id==self.tbl_source.c.changedby))),
                extension = validator)

        mapper(NewComment, self.tbl_new_comments,
               properties = dict(comment_id = self.tbl_new_comments.c.id,
                                 policy_queue = relation(PolicyQueue)))

        mapper(Override, self.tbl_override,
               properties = dict(suite_id = self.tbl_override.c.suite,
                                 suite = relation(Suite, \
                                    backref=backref('overrides', lazy='dynamic')),
                                 package = self.tbl_override.c.package,
                                 component_id = self.tbl_override.c.component,
                                 component = relation(Component, \
                                    backref=backref('overrides', lazy='dynamic')),
                                 priority_id = self.tbl_override.c.priority,
                                 priority = relation(Priority, \
                                    backref=backref('overrides', lazy='dynamic')),
                                 section_id = self.tbl_override.c.section,
                                 section = relation(Section, \
                                    backref=backref('overrides', lazy='dynamic')),
                                 overridetype_id = self.tbl_override.c.type,
                                 overridetype = relation(OverrideType, \
                                    backref=backref('overrides', lazy='dynamic'))))

        mapper(OverrideType, self.tbl_override_type,
               properties = dict(overridetype = self.tbl_override_type.c.type,
                                 overridetype_id = self.tbl_override_type.c.id))

        mapper(PolicyQueue, self.tbl_policy_queue,
               properties = dict(policy_queue_id = self.tbl_policy_queue.c.id,
                                 suite = relation(Suite, primaryjoin=(self.tbl_policy_queue.c.suite_id == self.tbl_suite.c.id))))

        mapper(PolicyQueueUpload, self.tbl_policy_queue_upload,
               properties = dict(
                   changes = relation(DBChange),
                   policy_queue = relation(PolicyQueue, backref='uploads'),
                   target_suite = relation(Suite),
                   source = relation(DBSource),
                   binaries = relation(DBBinary, secondary=self.tbl_policy_queue_upload_binaries_map),
                ))

        mapper(PolicyQueueByhandFile, self.tbl_policy_queue_byhand_file,
               properties = dict(
                   upload = relation(PolicyQueueUpload, backref='byhand'),
                   )
               )

        mapper(Priority, self.tbl_priority,
               properties = dict(priority_id = self.tbl_priority.c.id))

        mapper(Section, self.tbl_section,
               properties = dict(section_id = self.tbl_section.c.id,
                                 section=self.tbl_section.c.section))

        mapper(SignatureHistory, self.tbl_signature_history)

        mapper(DBSource, self.tbl_source,
               properties = dict(source_id = self.tbl_source.c.id,
                                 version = self.tbl_source.c.version,
                                 maintainer_id = self.tbl_source.c.maintainer,
                                 poolfile_id = self.tbl_source.c.file,
                                 poolfile = relation(PoolFile),
                                 fingerprint_id = self.tbl_source.c.sig_fpr,
                                 fingerprint = relation(Fingerprint),
                                 changedby_id = self.tbl_source.c.changedby,
                                 srcfiles = relation(DSCFile,
                                                     primaryjoin=(self.tbl_source.c.id==self.tbl_dsc_files.c.source)),
                                 suites = relation(Suite, secondary=self.tbl_src_associations,
                                     backref=backref('sources', lazy='dynamic')),
                                 uploaders = relation(Maintainer,
                                     secondary=self.tbl_src_uploaders),
                                 key = relation(SourceMetadata, cascade='all',
                                     collection_class=attribute_mapped_collection('key'))),
               extension = validator)

        mapper(SrcFormat, self.tbl_src_format,
               properties = dict(src_format_id = self.tbl_src_format.c.id,
                                 format_name = self.tbl_src_format.c.format_name))

        mapper(Suite, self.tbl_suite,
               properties = dict(suite_id = self.tbl_suite.c.id,
                                 policy_queue = relation(PolicyQueue, primaryjoin=(self.tbl_suite.c.policy_queue_id == self.tbl_policy_queue.c.id)),
                                 new_queue = relation(PolicyQueue, primaryjoin=(self.tbl_suite.c.new_queue_id == self.tbl_policy_queue.c.id)),
                                 copy_queues = relation(BuildQueue,
                                     secondary=self.tbl_suite_build_queue_copy),
                                 srcformats = relation(SrcFormat, secondary=self.tbl_suite_src_formats,
                                     backref=backref('suites', lazy='dynamic')),
                                 archive = relation(Archive, backref='suites'),
                                 acls = relation(ACL, secondary=self.tbl_suite_acl_map, collection_class=set),
                                 components = relation(Component, secondary=self.tbl_component_suite,
                                                   order_by=self.tbl_component.c.ordering,
                                                   backref=backref('suites'))),
                extension = validator)

        mapper(Uid, self.tbl_uid,
               properties = dict(uid_id = self.tbl_uid.c.id,
                                 fingerprint = relation(Fingerprint)),
               extension = validator)

        mapper(BinContents, self.tbl_bin_contents,
            properties = dict(
                binary = relation(DBBinary,
                    backref=backref('contents', lazy='dynamic', cascade='all')),
                file = self.tbl_bin_contents.c.file))

        mapper(SrcContents, self.tbl_src_contents,
            properties = dict(
                source = relation(DBSource,
                    backref=backref('contents', lazy='dynamic', cascade='all')),
                file = self.tbl_src_contents.c.file))

        mapper(MetadataKey, self.tbl_metadata_keys,
            properties = dict(
                key_id = self.tbl_metadata_keys.c.key_id,
                key = self.tbl_metadata_keys.c.key))

        mapper(BinaryMetadata, self.tbl_binaries_metadata,
            properties = dict(
                binary_id = self.tbl_binaries_metadata.c.bin_id,
                binary = relation(DBBinary),
                key_id = self.tbl_binaries_metadata.c.key_id,
                key = relation(MetadataKey),
                value = self.tbl_binaries_metadata.c.value))

        mapper(SourceMetadata, self.tbl_source_metadata,
            properties = dict(
                source_id = self.tbl_source_metadata.c.src_id,
                source = relation(DBSource),
                key_id = self.tbl_source_metadata.c.key_id,
                key = relation(MetadataKey),
                value = self.tbl_source_metadata.c.value))

	mapper(VersionCheck, self.tbl_version_check,
	    properties = dict(
		suite_id = self.tbl_version_check.c.suite,
		suite = relation(Suite, primaryjoin=self.tbl_version_check.c.suite==self.tbl_suite.c.id),
		reference_id = self.tbl_version_check.c.reference,
		reference = relation(Suite, primaryjoin=self.tbl_version_check.c.reference==self.tbl_suite.c.id, lazy='joined')))

    ## Connection functions
    def __createconn(self):
        from config import Config
        cnf = Config()
        if cnf.has_key("DB::Service"):
            connstr = "postgresql://service=%s" % cnf["DB::Service"]
        elif cnf.has_key("DB::Host"):
            # TCP/IP
            connstr = "postgresql://%s" % cnf["DB::Host"]
            if cnf.has_key("DB::Port") and cnf["DB::Port"] != "-1":
                connstr += ":%s" % cnf["DB::Port"]
            connstr += "/%s" % cnf["DB::Name"]
        else:
            # Unix Socket
            connstr = "postgresql:///%s" % cnf["DB::Name"]
            if cnf.has_key("DB::Port") and cnf["DB::Port"] != "-1":
                connstr += "?port=%s" % cnf["DB::Port"]

        engine_args = { 'echo': self.debug }
        if cnf.has_key('DB::PoolSize'):
            engine_args['pool_size'] = int(cnf['DB::PoolSize'])
        if cnf.has_key('DB::MaxOverflow'):
            engine_args['max_overflow'] = int(cnf['DB::MaxOverflow'])
        if sa_major_version != '0.5' and cnf.has_key('DB::Unicode') and \
            cnf['DB::Unicode'] == 'false':
            engine_args['use_native_unicode'] = False

        # Monkey patch a new dialect in in order to support service= syntax
        import sqlalchemy.dialects.postgresql
        from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
        class PGDialect_psycopg2_dak(PGDialect_psycopg2):
            def create_connect_args(self, url):
                if str(url).startswith('postgresql://service='):
                    # Eww
                    servicename = str(url)[21:]
                    return (['service=%s' % servicename], {})
                else:
                    return PGDialect_psycopg2.create_connect_args(self, url)

        sqlalchemy.dialects.postgresql.base.dialect = PGDialect_psycopg2_dak

        try:
            self.db_pg   = create_engine(connstr, **engine_args)
            self.db_meta = MetaData()
            self.db_meta.bind = self.db_pg
            self.db_smaker = sessionmaker(bind=self.db_pg,
                                          autoflush=True,
                                          autocommit=False)

            self.__setuptables()
            self.__setupmappers()

        except OperationalError as e:
            import utils
            utils.fubar("Cannot connect to database (%s)" % str(e))

        self.pid = os.getpid()

    def session(self, work_mem = 0):
        '''
        Returns a new session object. If a work_mem parameter is provided a new
        transaction is started and the work_mem parameter is set for this
        transaction. The work_mem parameter is measured in MB. A default value
        will be used if the parameter is not set.
        '''
        # reinitialize DBConn in new processes
        if self.pid != os.getpid():
            clear_mappers()
            self.__createconn()
        session = self.db_smaker()
        if work_mem > 0:
            session.execute("SET LOCAL work_mem TO '%d MB'" % work_mem)
        return session

__all__.append('DBConn')
