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

from inspect import getargspec

from sqlalchemy import create_engine, Table, MetaData, select
from sqlalchemy.orm import sessionmaker, mapper, relation

# Don't remove this, we re-export the exceptions to scripts which import us
from sqlalchemy.exc import *
from sqlalchemy.orm.exc import NoResultFound

# Only import Config until Queue stuff is changed to store its config
# in the database
from config import Config
from singleton import Singleton
from textutils import fix_maintainer

################################################################################

__all__ = ['IntegrityError', 'SQLAlchemyError']

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

################################################################################

class Architecture(object):
    def __init__(self, *args, **kwargs):
        pass

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

    def __repr__(self):
        return '<Architecture %s>' % self.arch_string

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

@session_wrapper
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

    q = session.query(Suite)
    q = q.join(SuiteArchitecture)
    q = q.join(Architecture).filter_by(arch_string=architecture).order_by('suite_name')

    ret = q.all()

    return ret

__all__.append('get_architecture_suites')

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

@session_wrapper
def get_suites_binary_in(package, session=None):
    """
    Returns list of Suite objects which given C{package} name is in

    @type source: str
    @param source: DBBinary package name to search for

    @rtype: list
    @return: list of Suite objects for the given package
    """

    return session.query(Suite).join(BinAssociation).join(DBBinary).filter_by(package=package).all()

__all__.append('get_suites_binary_in')

@session_wrapper
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

    q = session.query(DBBinary).filter_by(binary_id=id)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_binary_from_id')

@session_wrapper
def get_binaries_from_name(package, version=None, architecture=None, session=None):
    """
    Returns list of DBBinary objects for given C{package} name

    @type package: str
    @param package: DBBinary package name to search for

    @type version: str or None
    @param version: Version to search for (or None)

    @type package: str, list or None
    @param package: Architectures to limit to (or None if no limit)

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of DBBinary objects for the given name (may be empty)
    """

    q = session.query(DBBinary).filter_by(package=package)

    if version is not None:
        q = q.filter_by(version=version)

    if architecture is not None:
        if not isinstance(architecture, list):
            architecture = [architecture]
        q = q.join(Architecture).filter(Architecture.arch_string.in_(architecture))

    ret = q.all()

    return ret

__all__.append('get_binaries_from_name')

@session_wrapper
def get_binaries_from_source_id(source_id, session=None):
    """
    Returns list of DBBinary objects for given C{source_id}

    @type source_id: int
    @param source_id: source_id to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of DBBinary objects for the given name (may be empty)
    """

    return session.query(DBBinary).filter_by(source_id=source_id).all()

__all__.append('get_binaries_from_source_id')

@session_wrapper
def get_binary_from_name_suite(package, suitename, session=None):
    ### For dak examine-package
    ### XXX: Doesn't use object API yet

    sql = """SELECT DISTINCT(b.package), b.version, c.name, su.suite_name
             FROM binaries b, files fi, location l, component c, bin_associations ba, suite su
             WHERE b.package=:package
               AND b.file = fi.id
               AND fi.location = l.id
               AND l.component = c.id
               AND ba.bin=b.id
               AND ba.suite = su.id
               AND su.suite_name=:suitename
          ORDER BY b.version DESC"""

    return session.execute(sql, {'package': package, 'suitename': suitename})

__all__.append('get_binary_from_name_suite')

@session_wrapper
def get_binary_components(package, suitename, arch, session=None):
    # Check for packages that have moved from one component to another
    query = """SELECT c.name FROM binaries b, bin_associations ba, suite s, location l, component c, architecture a, files f
    WHERE b.package=:package AND s.suite_name=:suitename
      AND (a.arch_string = :arch OR a.arch_string = 'all')
      AND ba.bin = b.id AND ba.suite = s.id AND b.architecture = a.id
      AND f.location = l.id
      AND l.component = c.id
      AND b.file = f.id"""

    vals = {'package': package, 'suitename': suitename, 'arch': arch}

    return session.execute(query, vals)

__all__.append('get_binary_components')

################################################################################

class Component(object):
    def __init__(self, *args, **kwargs):
        pass

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

    def __repr__(self):
        return '<Component %s>' % self.component_name


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

    @type filename: string
    @param filename: The filepath
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
        pathcache = {}
        for fullpath in fullpaths:
            # Get the necessary IDs ...
            (path, file) = os.path.split(fullpath)

            filepath_id = get_or_set_contents_path_id(path, session)
            filename_id = get_or_set_contents_file_id(file, session)

            pathcache[fullpath] = (filepath_id, filename_id)

        for fullpath, dat in pathcache.items():
            ca = ContentAssociation()
            ca.binary_id = binary_id
            ca.filepath_id = dat[0]
            ca.filename_id = dat[1]
            session.add(ca)

        # Only commit if we set up the session ourself
        if privatetrans:
            session.commit()
            session.close()
        else:
            session.flush()

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

class PoolFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<PoolFile %s>' % self.filename

__all__.append('PoolFile')

@session_wrapper
def check_poolfile(filename, filesize, md5sum, location_id, session=None):
    """
    Returns a tuple:
     (ValidFileFound [boolean or None], PoolFile object or None)

    @type filename: string
    @param filename: the filename of the file to check against the DB

    @type filesize: int
    @param filesize: the size of the file to check against the DB

    @type md5sum: string
    @param md5sum: the md5sum of the file to check against the DB

    @type location_id: int
    @param location_id: the id of the location to look in

    @rtype: tuple
    @return: Tuple of length 2.
             If more than one file found with that name:
                    (None,  None)
             If valid pool file found: (True, PoolFile object)
             If valid pool file not found:
                    (False, None) if no file found
                    (False, PoolFile object) if file found with size/md5sum mismatch
    """

    q = session.query(PoolFile).filter_by(filename=filename)
    q = q.join(Location).filter_by(location_id=location_id)

    ret = None

    if q.count() > 1:
        ret = (None, None)
    elif q.count() < 1:
        ret = (False, None)
    else:
        obj = q.one()
        if obj.md5sum != md5sum or obj.filesize != filesize:
            ret = (False, obj)

    if ret is None:
        ret = (True, obj)

    return ret

__all__.append('check_poolfile')

@session_wrapper
def get_poolfile_by_id(file_id, session=None):
    """
    Returns a PoolFile objects or None for the given id

    @type file_id: int
    @param file_id: the id of the file to look for

    @rtype: PoolFile or None
    @return: either the PoolFile object or None
    """

    q = session.query(PoolFile).filter_by(file_id=file_id)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_poolfile_by_id')


@session_wrapper
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

    q = session.query(PoolFile).filter_by(filename=filename)

    if location_id is not None:
        q = q.join(Location).filter_by(location_id=location_id)

    return q.all()

__all__.append('get_poolfile_by_name')

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
    q = session.query(PoolFile).filter(PoolFile.filename.like('%%%s%%' % filename))

    return q.all()

__all__.append('get_poolfile_like_name')

################################################################################

class Fingerprint(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Fingerprint %s>' % self.fingerprint

__all__.append('Fingerprint')

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

class Keyring(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Keyring %s>' % self.keyring_name

__all__.append('Keyring')

@session_wrapper
def get_or_set_keyring(keyring, session=None):
    """
    If C{keyring} does not have an entry in the C{keyrings} table yet, create one
    and return the new Keyring
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
        obj = Keyring(keyring_name=keyring)
        session.add(obj)
        session.commit_or_flush()
        return obj

__all__.append('get_or_set_keyring')

################################################################################

class Location(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Location %s (%s)>' % (self.path, self.location_id)

__all__.append('Location')

@session_wrapper
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

    q = session.query(Location).filter_by(path=location)

    if archive is not None:
        q = q.join(Archive).filter_by(archive_name=archive)

    if component is not None:
        q = q.join(Component).filter_by(component_name=component)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_location')

################################################################################

class Maintainer(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '''<Maintainer '%s' (%s)>''' % (self.name, self.maintainer_id)

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
def has_new_comment(package, version, session=None):
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

    q = session.query(NewComment)
    q = q.filter_by(package=package)
    q = q.filter_by(version=version)

    return bool(q.count() > 0)

__all__.append('has_new_comment')

@session_wrapper
def get_new_comments(package=None, version=None, comment_id=None, session=None):
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

    q = session.query(NewComment)
    if package is not None: q = q.filter_by(package=package)
    if version is not None: q = q.filter_by(version=version)
    if comment_id is not None: q = q.filter_by(comment_id=comment_id)

    return q.all()

__all__.append('get_new_comments')

################################################################################

class Override(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Override %s (%s)>' % (self.package, self.suite_id)

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

class OverrideType(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<OverrideType %s>' % self.overridetype

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
        pathcache = {}
        for fullpath in fullpaths:
            (path, file) = os.path.split(fullpath)

            if path.startswith( "./" ):
                path = path[2:]

            filepath_id = get_or_set_contents_path_id(path, session)
            filename_id = get_or_set_contents_file_id(file, session)

            pathcache[fullpath] = (filepath_id, filename_id)

        for fullpath, dat in pathcache.items():
            pca = PendingContentAssociation()
            pca.package = package['Package']
            pca.version = package['Version']
            pca.filepath_id = dat[0]
            pca.filename_id = dat[1]
            pca.architecture = arch_id
            session.add(pca)

        # Only commit if we set up the session ourself
        if privatetrans:
            session.commit()
            session.close()
        else:
            session.flush()

        return True
    except Exception, e:
        traceback.print_exc()

        # Only rollback if we set up the session ourself
        if privatetrans:
            session.rollback()
            session.close()

        return False

__all__.append('insert_pending_content_paths')

################################################################################

class Priority(object):
    def __init__(self, *args, **kwargs):
        pass

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

    def __repr__(self):
        return '<Priority %s (%s)>' % (self.priority, self.priority_id)

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

class Queue(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Queue %s>' % self.queue_name

    def autobuild_upload(self, changes, srcpath, session=None):
        """
        Update queue_build database table used for incoming autobuild support.

        @type changes: Changes
        @param changes: changes object for the upload to process

        @type srcpath: string
        @param srcpath: path for the queue file entries/link destinations

        @type session: SQLAlchemy session
        @param session: Optional SQLAlchemy session.  If this is passed, the
        caller is responsible for ensuring a transaction has begun and
        committing the results or rolling back based on the result code.  If
        not passed, a commit will be performed at the end of the function,
        otherwise the caller is responsible for commiting.

        @rtype: NoneType or string
        @return: None if the operation failed, a string describing the error if not
        """

        privatetrans = False
        if session is None:
            session = DBConn().session()
            privatetrans = True

        # TODO: Remove by moving queue config into the database
        conf = Config()

        for suitename in changes.changes["distribution"].keys():
            # TODO: Move into database as:
            #       buildqueuedir TEXT DEFAULT NULL (i.e. NULL is no build)
            #       buildqueuecopy BOOLEAN NOT NULL DEFAULT FALSE (i.e. default is symlink)
            #       This also gets rid of the SecurityQueueBuild hack below
            if suitename not in conf.ValueList("Dinstall::QueueBuildSuites"):
                continue

            # Find suite object
            s = get_suite(suitename, session)
            if s is None:
                return "INTERNAL ERROR: Could not find suite %s" % suitename

            # TODO: Get from database as above
            dest_dir = conf["Dir::QueueBuild"]

            # TODO: Move into database as above
            if conf.FindB("Dinstall::SecurityQueueBuild"):
                dest_dir = os.path.join(dest_dir, suitename)

            for file_entry in changes.files.keys():
                src = os.path.join(srcpath, file_entry)
                dest = os.path.join(dest_dir, file_entry)

                # TODO: Move into database as above
                if conf.FindB("Dinstall::SecurityQueueBuild"):
                    # Copy it since the original won't be readable by www-data
                    import utils
                    utils.copy(src, dest)
                else:
                    # Create a symlink to it
                    os.symlink(src, dest)

                qb = QueueBuild()
                qb.suite_id = s.suite_id
                qb.queue_id = self.queue_id
                qb.filename = dest
                qb.in_queue = True

                session.add(qb)

            # If the .orig tarballs are in the pool, create a symlink to
            # them (if one doesn't already exist)
            for dsc_file in changes.dsc_files.keys():
                # Skip all files except orig tarballs
                if not re_is_orig_source.match(dsc_file):
                    continue
                # Skip orig files not identified in the pool
                if not (changes.orig_files.has_key(dsc_file) and
                        changes.orig_files[dsc_file].has_key("id")):
                    continue
                orig_file_id = changes.orig_files[dsc_file]["id"]
                dest = os.path.join(dest_dir, dsc_file)

                # If it doesn't exist, create a symlink
                if not os.path.exists(dest):
                    q = session.execute("SELECT l.path, f.filename FROM location l, files f WHERE f.id = :id and f.location = l.id",
                                        {'id': orig_file_id})
                    res = q.fetchone()
                    if not res:
                        return "[INTERNAL ERROR] Couldn't find id %s in files table." % (orig_file_id)

                    src = os.path.join(res[0], res[1])
                    os.symlink(src, dest)

                    # Add it to the list of packages for later processing by apt-ftparchive
                    qb = QueueBuild()
                    qb.suite_id = s.suite_id
                    qb.queue_id = self.queue_id
                    qb.filename = dest
                    qb.in_queue = True
                    session.add(qb)

                # If it does, update things to ensure it's not removed prematurely
                else:
                    qb = get_queue_build(dest, s.suite_id, session)
                    if qb is None:
                        qb.in_queue = True
                        qb.last_used = None
                        session.add(qb)

        if privatetrans:
            session.commit()
            session.close()

        return None

__all__.append('Queue')

@session_wrapper
def get_queue(queuename, session=None):
    """
    Returns Queue object for given C{queue name}.

    @type queuename: string
    @param queuename: The name of the queue

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Queue
    @return: Queue object for the given queue
    """

    q = session.query(Queue).filter_by(queue_name=queuename)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_queue')

################################################################################

class QueueBuild(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<QueueBuild %s (%s)>' % (self.filename, self.queue_id)

__all__.append('QueueBuild')

@session_wrapper
def get_queue_build(filename, suite, session=None):
    """
    Returns QueueBuild object for given C{filename} and C{suite}.

    @type filename: string
    @param filename: The name of the file

    @type suiteid: int or str
    @param suiteid: Suite name or ID

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: Queue
    @return: Queue object for the given queue
    """

    if isinstance(suite, int):
        q = session.query(QueueBuild).filter_by(filename=filename).filter_by(suite_id=suite)
    else:
        q = session.query(QueueBuild).filter_by(filename=filename)
        q = q.join(Suite).filter_by(suite_name=suite)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_queue_build')

################################################################################

class Section(object):
    def __init__(self, *args, **kwargs):
        pass

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

    def __repr__(self):
        return '<Section %s>' % self.section

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

class DBSource(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBSource %s (%s)>' % (self.source, self.version)

__all__.append('DBSource')

@session_wrapper
def source_exists(source, source_version, suites = ["any"], session=None):
    """
    Ensure that source exists somewhere in the archive for the binary
    upload being processed.
      1. exact match     => 1.0-3
      2. bin-only NMU    => 1.0-3+b1 , 1.0-3.1+b1

    @type package: string
    @param package: package source name

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
    ret = 1

    for suite in suites:
        q = session.query(DBSource).filter_by(source=source)
        if suite != "any":
            # source must exist in suite X, or in some other suite that's
            # mapped to X, recursively... silent-maps are counted too,
            # unreleased-maps aren't.
            maps = cnf.ValueList("SuiteMappings")[:]
            maps.reverse()
            maps = [ m.split() for m in maps ]
            maps = [ (x[1], x[2]) for x in maps
                            if x[0] == "map" or x[0] == "silent-map" ]
            s = [suite]
            for x in maps:
                if x[1] in s and x[0] not in s:
                    s.append(x[0])

            q = q.join(SrcAssociation).join(Suite)
            q = q.filter(Suite.suite_name.in_(s))

        # Reduce the query results to a list of version numbers
        ql = [ j.version for j in q.all() ]

        # Try (1)
        if source_version in ql:
            continue

        # Try (2)
        from daklib.regexes import re_bin_only_nmu
        orig_source_version = re_bin_only_nmu.sub('', source_version)
        if orig_source_version in ql:
            continue

        # No source found so return not ok
        ret = 0

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

    return session.query(Suite).join(SrcAssociation).join(DBSource).filter_by(source=source).all()

__all__.append('get_suites_source_in')

@session_wrapper
def get_sources_from_name(source, version=None, dm_upload_allowed=None, session=None):
    """
    Returns list of DBSource objects for given C{source} name and other parameters

    @type source: str
    @param source: DBSource package name to search for

    @type source: str or None
    @param source: DBSource version name to search for or None if not applicable

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

@session_wrapper
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

    q = session.query(SrcAssociation)
    q = q.join('source').filter_by(source=source)
    q = q.join('suite').filter_by(suite_name=suite)

    try:
        return q.one().source
    except NoResultFound:
        return None

__all__.append('get_source_in_suite')

################################################################################

class SrcAssociation(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcAssociation %s (%s, %s)>' % (self.sa_id, self.source, self.suite)

__all__.append('SrcAssociation')

################################################################################

class SrcFormat(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcFormat %s>' % (self.format_name)

__all__.append('SrcFormat')

################################################################################

class SrcUploader(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SrcUploader %s>' % self.uploader_id

__all__.append('SrcUploader')

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
                 ('CopyDotDak', 'copydotdak'),
                 ('CommentsDir', 'commentsdir'),
                 ('OverrideSuite', 'overridesuite'),
                 ('ChangelogBase', 'changelogbase')]


class Suite(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<Suite %s>' % self.suite_name

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

__all__.append('Suite')

@session_wrapper
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

    q = session.query(SuiteArchitecture)
    q = q.join(Architecture).filter_by(arch_string=architecture)
    q = q.join(Suite).filter_by(suite_name=suite)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_suite_architecture')

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

class SuiteArchitecture(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SuiteArchitecture (%s, %s)>' % (self.suite_id, self.arch_id)

__all__.append('SuiteArchitecture')

@session_wrapper
def get_suite_architectures(suite, skipsrc=False, skipall=False, session=None):
    """
    Returns list of Architecture objects for given C{suite} name

    @type source: str
    @param source: Suite name to search for

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

    q = session.query(Architecture)
    q = q.join(SuiteArchitecture)
    q = q.join(Suite).filter_by(suite_name=suite)

    if skipsrc:
        q = q.filter(Architecture.arch_string != 'source')

    if skipall:
        q = q.filter(Architecture.arch_string != 'all')

    q = q.order_by('arch_string')

    return q.all()

__all__.append('get_suite_architectures')

################################################################################

class SuiteSrcFormat(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SuiteSrcFormat (%s, %s)>' % (self.suite_id, self.src_format_id)

__all__.append('SuiteSrcFormat')

@session_wrapper
def get_suite_src_formats(suite, session=None):
    """
    Returns list of allowed SrcFormat for C{suite}.

    @type suite: str
    @param suite: Suite name to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: the list of allowed source formats for I{suite}
    """

    q = session.query(SrcFormat)
    q = q.join(SuiteSrcFormat)
    q = q.join(Suite).filter_by(suite_name=suite)
    q = q.order_by('format_name')

    return q.all()

__all__.append('get_suite_src_formats')

################################################################################

class Uid(object):
    def __init__(self, *args, **kwargs):
        pass

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

    def __repr__(self):
        return '<Uid %s (%s)>' % (self.uid, self.name)

__all__.append('Uid')

@session_wrapper
def add_database_user(uidname, session=None):
    """
    Adds a database user

    @type uidname: string
    @param uidname: The uid of the user to add

    @type session: SQLAlchemy
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied).  If not passed, a commit will be performed at
    the end of the function, otherwise the caller is responsible for commiting.

    @rtype: Uid
    @return: the uid object for the given uidname
    """

    session.execute("CREATE USER :uid", {'uid': uidname})
    session.commit_or_flush()

__all__.append('add_database_user')

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
        self.tbl_new_comments = Table('new_comments', self.db_meta, autoload=True)
        self.tbl_override = Table('override', self.db_meta, autoload=True)
        self.tbl_override_type = Table('override_type', self.db_meta, autoload=True)
        self.tbl_pending_content_associations = Table('pending_content_associations', self.db_meta, autoload=True)
        self.tbl_priority = Table('priority', self.db_meta, autoload=True)
        self.tbl_queue = Table('queue', self.db_meta, autoload=True)
        self.tbl_queue_build = Table('queue_build', self.db_meta, autoload=True)
        self.tbl_section = Table('section', self.db_meta, autoload=True)
        self.tbl_source = Table('source', self.db_meta, autoload=True)
        self.tbl_src_associations = Table('src_associations', self.db_meta, autoload=True)
        self.tbl_src_format = Table('src_format', self.db_meta, autoload=True)
        self.tbl_src_uploaders = Table('src_uploaders', self.db_meta, autoload=True)
        self.tbl_suite = Table('suite', self.db_meta, autoload=True)
        self.tbl_suite_architectures = Table('suite_architectures', self.db_meta, autoload=True)
        self.tbl_suite_src_formats = Table('suite_src_formats', self.db_meta, autoload=True)
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

        mapper(NewComment, self.tbl_new_comments,
               properties = dict(comment_id = self.tbl_new_comments.c.id))

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
                                 queue = relation(Queue, backref='queuebuild')))

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

        mapper(SrcFormat, self.tbl_src_format,
               properties = dict(src_format_id = self.tbl_src_format.c.id,
                                 format_name = self.tbl_src_format.c.format_name))

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

        mapper(SuiteSrcFormat, self.tbl_suite_src_formats,
               properties = dict(suite_id = self.tbl_suite_src_formats.c.suite,
                                 suite = relation(Suite, backref='suitesrcformats'),
                                 src_format_id = self.tbl_suite_src_formats.c.src_format,
                                 src_format = relation(SrcFormat)))

        mapper(Uid, self.tbl_uid,
               properties = dict(uid_id = self.tbl_uid.c.id,
                                 fingerprint = relation(Fingerprint)))

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


