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

import os
import re
import psycopg2
import traceback
import commands
from datetime import datetime, timedelta
from errno import ENOENT
from tempfile import mkstemp, mkdtemp

from inspect import getargspec

import sqlalchemy
from sqlalchemy import create_engine, Table, MetaData, Column, Integer
from sqlalchemy.orm import sessionmaker, mapper, relation, object_session, backref
from sqlalchemy import types as sqltypes

# Don't remove this, we re-export the exceptions to scripts which import us
from sqlalchemy.exc import *
from sqlalchemy.orm.exc import NoResultFound

# Only import Config until Queue stuff is changed to store its config
# in the database
from config import Config
from textutils import fix_maintainer
from dak_exceptions import NoSourceFieldError

# suppress some deprecation warnings in squeeze related to sqlalchemy
import warnings
warnings.filterwarnings('ignore', \
    "The SQLAlchemy PostgreSQL dialect has been renamed from 'postgres' to 'postgresql'.*", \
    SADeprecationWarning)
# TODO: sqlalchemy needs some extra configuration to correctly reflect
# the ind_deb_contents_* indexes - we ignore the warnings at the moment
warnings.filterwarnings("ignore", 'Predicate of partial index', SAWarning)


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
if sa_major_version in ["0.5", "0.6"]:
    from sqlalchemy.databases import postgres
    postgres.ischema_names['debversion'] = DebVersion
else:
    raise Exception("dak only ported to SQLA versions 0.5 and 0.6.  See daklib/dbconn.py")

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

class Architecture(object):
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

# TODO: should be removed because the implementation is too trivial
@session_wrapper
def get_architecture_suites(architecture, session=None):
    """
    Returns list of Suite objects for given C{architecture} name

    @type architecture: str
    @param architecture: Architecture name to search for

    @type session: Session
    @param session: Optional SQL session object (a temporary one will be
    generated if not supplied)

    @rtype: list
    @return: list of Suite objects for the given name (may be empty)
    """

    return get_architecture(architecture, session).suites

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

class BinContents(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BinContents (%s, %s)>' % (self.binary, self.filename)

__all__.append('BinContents')

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

    @type package: str
    @param package: DBBinary package name to search for

    @rtype: list
    @return: list of Suite objects for the given package
    """

    return session.query(Suite).join(BinAssociation).join(DBBinary).filter_by(package=package).all()

__all__.append('get_suites_binary_in')

@session_wrapper
def get_binary_from_id(binary_id, session=None):
    """
    Returns DBBinary object for given C{id}

    @type binary_id: int
    @param binary_id: Id of the required binary

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: DBBinary
    @return: DBBinary object for the given binary (None if not present)
    """

    q = session.query(DBBinary).filter_by(binary_id=binary_id)

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

    @type architecture: str, list or None
    @param architecture: Architectures to limit to (or None if no limit)

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
             WHERE b.package='%(package)s'
               AND b.file = fi.id
               AND fi.location = l.id
               AND l.component = c.id
               AND ba.bin=b.id
               AND ba.suite = su.id
               AND su.suite_name %(suitename)s
          ORDER BY b.version DESC"""

    return session.execute(sql % {'package': package, 'suitename': suitename})

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

class BinaryACL(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BinaryACL %s>' % self.binary_acl_id

__all__.append('BinaryACL')

################################################################################

class BinaryACLMap(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BinaryACLMap %s>' % self.binary_acl_map_id

__all__.append('BinaryACLMap')

################################################################################

MINIMAL_APT_CONF="""
Dir
{
   ArchiveDir "%(archivepath)s";
   OverrideDir "%(overridedir)s";
   CacheDir "%(cachedir)s";
};

Default
{
   Packages::Compress ". bzip2 gzip";
   Sources::Compress ". bzip2 gzip";
   DeLinkLimit 0;
   FileMode 0664;
}

bindirectory "incoming"
{
   Packages "Packages";
   Contents " ";

   BinOverride "override.sid.all3";
   BinCacheDB "packages-accepted.db";

   FileList "%(filelist)s";

   PathPrefix "";
   Packages::Extensions ".deb .udeb";
};

bindirectory "incoming/"
{
   Sources "Sources";
   BinOverride "override.sid.all3";
   SrcOverride "override.sid.all3.src";
   FileList "%(filelist)s";
};
"""

class BuildQueue(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BuildQueue %s>' % self.queue_name

    def write_metadata(self, starttime, force=False):
        # Do we write out metafiles?
        if not (force or self.generate_metadata):
            return

        session = DBConn().session().object_session(self)

        fl_fd = fl_name = ac_fd = ac_name = None
        tempdir = None
        arches = " ".join([ a.arch_string for a in session.query(Architecture).all() if a.arch_string != 'source' ])
        startdir = os.getcwd()

        try:
            # Grab files we want to include
            newer = session.query(BuildQueueFile).filter_by(build_queue_id = self.queue_id).filter(BuildQueueFile.lastused + timedelta(seconds=self.stay_of_execution) > starttime).all()
            # Write file list with newer files
            (fl_fd, fl_name) = mkstemp()
            for n in newer:
                os.write(fl_fd, '%s\n' % n.fullpath)
            os.close(fl_fd)

            cnf = Config()

            # Write minimal apt.conf
            # TODO: Remove hardcoding from template
            (ac_fd, ac_name) = mkstemp()
            os.write(ac_fd, MINIMAL_APT_CONF % {'archivepath': self.path,
                                                'filelist': fl_name,
                                                'cachedir': cnf["Dir::Cache"],
                                                'overridedir': cnf["Dir::Override"],
                                                })
            os.close(ac_fd)

            # Run apt-ftparchive generate
            os.chdir(os.path.dirname(ac_name))
            os.system('apt-ftparchive -qq -o APT::FTPArchive::Contents=off generate %s' % os.path.basename(ac_name))

            # Run apt-ftparchive release
            # TODO: Eww - fix this
            bname = os.path.basename(self.path)
            os.chdir(self.path)
            os.chdir('..')

            # We have to remove the Release file otherwise it'll be included in the
            # new one
            try:
                os.unlink(os.path.join(bname, 'Release'))
            except OSError:
                pass

            os.system("""apt-ftparchive -qq -o APT::FTPArchive::Release::Origin="%s" -o APT::FTPArchive::Release::Label="%s" -o APT::FTPArchive::Release::Description="%s" -o APT::FTPArchive::Release::Architectures="%s" release %s > Release""" % (self.origin, self.label, self.releasedescription, arches, bname))

            # Crude hack with open and append, but this whole section is and should be redone.
            if self.notautomatic:
                release=open("Release", "a")
                release.write("NotAutomatic: yes")
                release.close()

            # Sign if necessary
            if self.signingkey:
                keyring = "--secret-keyring \"%s\"" % cnf["Dinstall::SigningKeyring"]
                if cnf.has_key("Dinstall::SigningPubKeyring"):
                    keyring += " --keyring \"%s\"" % cnf["Dinstall::SigningPubKeyring"]

                os.system("gpg %s --no-options --batch --no-tty --armour --default-key %s --detach-sign -o Release.gpg Release""" % (keyring, self.signingkey))

            # Move the files if we got this far
            os.rename('Release', os.path.join(bname, 'Release'))
            if self.signingkey:
                os.rename('Release.gpg', os.path.join(bname, 'Release.gpg'))

        # Clean up any left behind files
        finally:
            os.chdir(startdir)
            if fl_fd:
                try:
                    os.close(fl_fd)
                except OSError:
                    pass

            if fl_name:
                try:
                    os.unlink(fl_name)
                except OSError:
                    pass

            if ac_fd:
                try:
                    os.close(ac_fd)
                except OSError:
                    pass

            if ac_name:
                try:
                    os.unlink(ac_name)
                except OSError:
                    pass

    def clean_and_update(self, starttime, Logger, dryrun=False):
        """WARNING: This routine commits for you"""
        session = DBConn().session().object_session(self)

        if self.generate_metadata and not dryrun:
            self.write_metadata(starttime)

        # Grab files older than our execution time
        older = session.query(BuildQueueFile).filter_by(build_queue_id = self.queue_id).filter(BuildQueueFile.lastused + timedelta(seconds=self.stay_of_execution) <= starttime).all()

        for o in older:
            killdb = False
            try:
                if dryrun:
                    Logger.log(["I: Would have removed %s from the queue" % o.fullpath])
                else:
                    Logger.log(["I: Removing %s from the queue" % o.fullpath])
                    os.unlink(o.fullpath)
                    killdb = True
            except OSError, e:
                # If it wasn't there, don't worry
                if e.errno == ENOENT:
                    killdb = True
                else:
                    # TODO: Replace with proper logging call
                    Logger.log(["E: Could not remove %s" % o.fullpath])

            if killdb:
                session.delete(o)

        session.commit()

        for f in os.listdir(self.path):
            if f.startswith('Packages') or f.startswith('Source') or f.startswith('Release') or f.startswith('advisory'):
                continue

            try:
                r = session.query(BuildQueueFile).filter_by(build_queue_id = self.queue_id).filter_by(filename = f).one()
            except NoResultFound:
                fp = os.path.join(self.path, f)
                if dryrun:
                    Logger.log(["I: Would remove unused link %s" % fp])
                else:
                    Logger.log(["I: Removing unused link %s" % fp])
                    try:
                        os.unlink(fp)
                    except OSError:
                        Logger.log(["E: Failed to unlink unreferenced file %s" % r.fullpath])

    def add_file_from_pool(self, poolfile):
        """Copies a file into the pool.  Assumes that the PoolFile object is
        attached to the same SQLAlchemy session as the Queue object is.

        The caller is responsible for committing after calling this function."""
        poolfile_basename = poolfile.filename[poolfile.filename.rindex(os.sep)+1:]

        # Check if we have a file of this name or this ID already
        for f in self.queuefiles:
            if f.fileid is not None and f.fileid == poolfile.file_id or \
               f.poolfile.filename == poolfile_basename:
                   # In this case, update the BuildQueueFile entry so we
                   # don't remove it too early
                   f.lastused = datetime.now()
                   DBConn().session().object_session(poolfile).add(f)
                   return f

        # Prepare BuildQueueFile object
        qf = BuildQueueFile()
        qf.build_queue_id = self.queue_id
        qf.lastused = datetime.now()
        qf.filename = poolfile_basename

        targetpath = poolfile.fullpath
        queuepath = os.path.join(self.path, poolfile_basename)

        try:
            if self.copy_files:
                # We need to copy instead of symlink
                import utils
                utils.copy(targetpath, queuepath)
                # NULL in the fileid field implies a copy
                qf.fileid = None
            else:
                os.symlink(targetpath, queuepath)
                qf.fileid = poolfile.file_id
        except OSError:
            return None

        # Get the same session as the PoolFile is using and add the qf to it
        DBConn().session().object_session(poolfile).add(qf)

        return qf


__all__.append('BuildQueue')

@session_wrapper
def get_build_queue(queuename, session=None):
    """
    Returns BuildQueue object for given C{queue name}, creating it if it does not
    exist.

    @type queuename: string
    @param queuename: The name of the queue

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: BuildQueue
    @return: BuildQueue object for the given queue
    """

    q = session.query(BuildQueue).filter_by(queue_name=queuename)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_build_queue')

################################################################################

class BuildQueueFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<BuildQueueFile %s (%s)>' % (self.filename, self.build_queue_id)

    @property
    def fullpath(self):
        return os.path.join(self.buildqueue.path, self.filename)


__all__.append('BuildQueueFile')

################################################################################

class ChangePendingBinary(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ChangePendingBinary %s>' % self.change_pending_binary_id

__all__.append('ChangePendingBinary')

################################################################################

class ChangePendingFile(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ChangePendingFile %s>' % self.change_pending_file_id

__all__.append('ChangePendingFile')

################################################################################

class ChangePendingSource(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<ChangePendingSource %s>' % self.change_pending_source_id

__all__.append('ChangePendingSource')

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

class PoolFile(object):
    def __init__(self, filename = None, location = None, filesize = -1, \
        md5sum = None):
        self.filename = filename
        self.location = location
        self.filesize = filesize
        self.md5sum = md5sum

    def __repr__(self):
        return '<PoolFile %s>' % self.filename

    @property
    def fullpath(self):
        return os.path.join(self.location.path, self.filename)

    def is_valid(self, filesize = -1, md5sum = None):\
        return self.filesize == filesize and self.md5sum == md5sum

__all__.append('PoolFile')

@session_wrapper
def check_poolfile(filename, filesize, md5sum, location_id, session=None):
    """
    Returns a tuple:
    (ValidFileFound [boolean], PoolFile object or None)

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
                 - If valid pool file found: (C{True}, C{PoolFile object})
                 - If valid pool file not found:
                     - (C{False}, C{None}) if no file found
                     - (C{False}, C{PoolFile object}) if file found with size/md5sum mismatch
    """

    poolfile = session.query(Location).get(location_id). \
        files.filter_by(filename=filename).first()
    valid = False
    if poolfile and poolfile.is_valid(filesize = filesize, md5sum = md5sum):
        valid = True

    return (valid, poolfile)

__all__.append('check_poolfile')

# TODO: the implementation can trivially be inlined at the place where the
# function is called
@session_wrapper
def get_poolfile_by_id(file_id, session=None):
    """
    Returns a PoolFile objects or None for the given id

    @type file_id: int
    @param file_id: the id of the file to look for

    @rtype: PoolFile or None
    @return: either the PoolFile object or None
    """

    return session.query(PoolFile).get(file_id)

__all__.append('get_poolfile_by_id')

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

@session_wrapper
def add_poolfile(filename, datadict, location_id, session=None):
    """
    Add a new file to the pool

    @type filename: string
    @param filename: filename

    @type datadict: dict
    @param datadict: dict with needed data

    @type location_id: int
    @param location_id: database id of the location

    @rtype: PoolFile
    @return: the PoolFile object created
    """
    poolfile = PoolFile()
    poolfile.filename = filename
    poolfile.filesize = datadict["size"]
    poolfile.md5sum = datadict["md5sum"]
    poolfile.sha1sum = datadict["sha1sum"]
    poolfile.sha256sum = datadict["sha256sum"]
    poolfile.location_id = location_id

    session.add(poolfile)
    # Flush to get a file id (NB: This is not a commit)
    session.flush()

    return poolfile

__all__.append('add_poolfile')

################################################################################

class Fingerprint(object):
    def __init__(self, fingerprint = None):
        self.fingerprint = fingerprint

    def __repr__(self):
        return '<Fingerprint %s>' % self.fingerprint

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
        signingkey = False

        for line in k.xreadlines():
            field = line.split(":")
            if field[0] == "pub":
                key = field[4]
                self.keys[key] = {}
                (name, addr) = self.parse_address(field[9])
                if "@" in addr:
                    self.keys[key]["email"] = addr
                    self.keys[key]["name"] = name
                self.keys[key]["fingerprints"] = []
                signingkey = True
            elif key and field[0] == "sub" and len(field) >= 12:
                signingkey = ("s" in field[11])
            elif key and field[0] == "uid":
                (name, addr) = self.parse_address(field[9])
                if "email" not in self.keys[key] and "@" in addr:
                    self.keys[key]["email"] = addr
                    self.keys[key]["name"] = name
            elif signingkey and field[0] == "fpr":
                self.keys[key]["fingerprints"].append(field[9])
                self.fpr_lookup[field[9]] = key

    def import_users_from_ldap(self, session):
        import ldap
        cnf = Config()

        LDAPDn = cnf["Import-LDAP-Fingerprints::LDAPDn"]
        LDAPServer = cnf["Import-LDAP-Fingerprints::LDAPServer"]

        l = ldap.open(LDAPServer)
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

################################################################################

class KeyringACLMap(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<KeyringACLMap %s>' % self.keyring_acl_map_id

__all__.append('KeyringACLMap')

################################################################################

class DBChange(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DBChange %s>' % self.changesname

    def clean_from_queue(self):
        session = DBConn().session().object_session(self)

        # Remove changes_pool_files entries
        self.poolfiles = []

        # Remove changes_pending_files references
        self.files = []

        # Clear out of queue
        self.in_queue = None
        self.approved_for_id = None

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

class Location(object):
    def __init__(self, path = None):
        self.path = path
        # the column 'type' should go away, see comment at mapper
        self.archive_type = 'pool'

    def __repr__(self):
        return '<Location %s (%s)>' % (self.path, self.location_id)

__all__.append('Location')

@session_wrapper
def get_location(location, component=None, archive=None, session=None):
    """
    Returns Location object for the given combination of location, component
    and archive

    @type location: string
    @param location: the path of the location, e.g. I{/srv/ftp-master.debian.org/ftp/pool/}

    @type component: string
    @param component: the component name (if None, no restriction applied)

    @type archive: string
    @param archive: the archive name (if None, no restriction applied)

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
    def __init__(self, name = None):
        self.name = name

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

class DebContents(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<DebConetnts %s: %s>' % (self.package.package,self.file)

__all__.append('DebContents')


class UdebContents(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<UdebConetnts %s: %s>' % (self.package.package,self.file)

__all__.append('UdebContents')

class PendingBinContents(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<PendingBinContents %s>' % self.contents_id

__all__.append('PendingBinContents')

def insert_pending_content_paths(package,
                                 is_udeb,
                                 fullpaths,
                                 session=None):
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
        q = session.query(PendingBinContents)
        q = q.filter_by(package=package['Package'])
        q = q.filter_by(version=package['Version'])
        q = q.filter_by(architecture=arch_id)
        q.delete()

        for fullpath in fullpaths:

            if fullpath.startswith( "./" ):
                fullpath = fullpath[2:]

            pca = PendingBinContents()
            pca.package = package['Package']
            pca.version = package['Version']
            pca.file = fullpath
            pca.architecture = arch_id

            if isudeb:
                pca.type = 8 # gross
            else:
                pca.type = 7 # also gross
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

@session_wrapper
def get_policy_queue_from_path(pathname, session=None):
    """
    Returns PolicyQueue object for given C{path name}

    @type queuename: string
    @param queuename: The path

    @type session: Session
    @param session: Optional SQLA session object (a temporary one will be
    generated if not supplied)

    @rtype: PolicyQueue
    @return: PolicyQueue object for the given queue
    """

    q = session.query(PolicyQueue).filter_by(path=pathname)

    try:
        return q.one()
    except NoResultFound:
        return None

__all__.append('get_policy_queue_from_path')

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
    def __init__(self, source = None, version = None, maintainer = None, \
        changedby = None, poolfile = None, install_date = None):
        self.source = source
        self.version = version
        self.maintainer = maintainer
        self.changedby = changedby
        self.poolfile = poolfile
        self.install_date = install_date

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

################################################################################

@session_wrapper
def add_dsc_to_db(u, filename, session=None):
    entry = u.pkg.files[filename]
    source = DBSource()
    pfs = []

    source.source = u.pkg.dsc["source"]
    source.version = u.pkg.dsc["version"] # NB: not files[file]["version"], that has no epoch
    source.maintainer_id = get_or_set_maintainer(u.pkg.dsc["maintainer"], session).maintainer_id
    source.changedby_id = get_or_set_maintainer(u.pkg.changes["changed-by"], session).maintainer_id
    source.fingerprint_id = get_or_set_fingerprint(u.pkg.changes["fingerprint"], session).fingerprint_id
    source.install_date = datetime.now().date()

    dsc_component = entry["component"]
    dsc_location_id = entry["location id"]

    source.dm_upload_allowed = (u.pkg.dsc.get("dm-upload-allowed", '') == "yes")

    # Set up a new poolfile if necessary
    if not entry.has_key("files id") or not entry["files id"]:
        filename = entry["pool name"] + filename
        poolfile = add_poolfile(filename, entry, dsc_location_id, session)
        session.flush()
        pfs.append(poolfile)
        entry["files id"] = poolfile.file_id

    source.poolfile_id = entry["files id"]
    session.add(source)

    suite_names = u.pkg.changes["distribution"].keys()
    source.suites = session.query(Suite). \
        filter(Suite.suite_name.in_(suite_names)).all()

    # Add the source files to the DB (files and dsc_files)
    dscfile = DSCFile()
    dscfile.source_id = source.source_id
    dscfile.poolfile_id = entry["files id"]
    session.add(dscfile)

    for dsc_file, dentry in u.pkg.dsc_files.items():
        df = DSCFile()
        df.source_id = source.source_id

        # If the .orig tarball is already in the pool, it's
        # files id is stored in dsc_files by check_dsc().
        files_id = dentry.get("files id", None)

        # Find the entry in the files hash
        # TODO: Bail out here properly
        dfentry = None
        for f, e in u.pkg.files.items():
            if f == dsc_file:
                dfentry = e
                break

        if files_id is None:
            filename = dfentry["pool name"] + dsc_file

            (found, obj) = check_poolfile(filename, dentry["size"], dentry["md5sum"], dsc_location_id)
            # FIXME: needs to check for -1/-2 and or handle exception
            if found and obj is not None:
                files_id = obj.file_id
                pfs.append(obj)

            # If still not found, add it
            if files_id is None:
                # HACK: Force sha1sum etc into dentry
                dentry["sha1sum"] = dfentry["sha1sum"]
                dentry["sha256sum"] = dfentry["sha256sum"]
                poolfile = add_poolfile(filename, dentry, dsc_location_id, session)
                pfs.append(poolfile)
                files_id = poolfile.file_id
        else:
            poolfile = get_poolfile_by_id(files_id, session)
            if poolfile is None:
                utils.fubar("INTERNAL ERROR. Found no poolfile with id %d" % files_id)
            pfs.append(poolfile)

        df.poolfile_id = files_id
        session.add(df)

    # Add the src_uploaders to the DB
    uploader_ids = [source.maintainer_id]
    if u.pkg.dsc.has_key("uploaders"):
        for up in u.pkg.dsc["uploaders"].replace(">, ", ">\t").split("\t"):
            up = up.strip()
            uploader_ids.append(get_or_set_maintainer(up, session).maintainer_id)

    added_ids = {}
    for up_id in uploader_ids:
        if added_ids.has_key(up_id):
            import utils
            utils.warn("Already saw uploader %s for source %s" % (up_id, source.source))
            continue

        added_ids[up_id]=1

        su = SrcUploader()
        su.maintainer_id = up_id
        su.source_id = source.source_id
        session.add(su)

    session.flush()

    return source, dsc_component, dsc_location_id, pfs

__all__.append('add_dsc_to_db')

@session_wrapper
def add_deb_to_db(u, filename, session=None):
    """
    Contrary to what you might expect, this routine deals with both
    debs and udebs.  That info is in 'dbtype', whilst 'type' is
    'deb' for both of them
    """
    cnf = Config()
    entry = u.pkg.files[filename]

    bin = DBBinary()
    bin.package = entry["package"]
    bin.version = entry["version"]
    bin.maintainer_id = get_or_set_maintainer(entry["maintainer"], session).maintainer_id
    bin.fingerprint_id = get_or_set_fingerprint(u.pkg.changes["fingerprint"], session).fingerprint_id
    bin.arch_id = get_architecture(entry["architecture"], session).arch_id
    bin.binarytype = entry["dbtype"]

    # Find poolfile id
    filename = entry["pool name"] + filename
    fullpath = os.path.join(cnf["Dir::Pool"], filename)
    if not entry.get("location id", None):
        entry["location id"] = get_location(cnf["Dir::Pool"], entry["component"], session=session).location_id

    if entry.get("files id", None):
        poolfile = get_poolfile_by_id(bin.poolfile_id)
        bin.poolfile_id = entry["files id"]
    else:
        poolfile = add_poolfile(filename, entry, entry["location id"], session)
        bin.poolfile_id = entry["files id"] = poolfile.file_id

    # Find source id
    bin_sources = get_sources_from_name(entry["source package"], entry["source version"], session=session)
    if len(bin_sources) != 1:
        raise NoSourceFieldError, "Unable to find a unique source id for %s (%s), %s, file %s, type %s, signed by %s" % \
                                  (bin.package, bin.version, entry["architecture"],
                                   filename, bin.binarytype, u.pkg.changes["fingerprint"])

    bin.source_id = bin_sources[0].source_id

    # Add and flush object so it has an ID
    session.add(bin)
    session.flush()

    # Add BinAssociations
    for suite_name in u.pkg.changes["distribution"].keys():
        ba = BinAssociation()
        ba.binary_id = bin.binary_id
        ba.suite_id = get_suite(suite_name).suite_id
        session.add(ba)

    session.flush()

    # Deal with contents - disabled for now
    #contents = copy_temporary_contents(bin.package, bin.version, bin.architecture.arch_string, os.path.basename(filename), None, session)
    #if not contents:
    #    print "REJECT\nCould not determine contents of package %s" % bin.package
    #    session.rollback()
    #    raise MissingContents, "No contents stored for package %s, and couldn't determine contents of %s" % (bin.package, filename)

    return poolfile

__all__.append('add_deb_to_db')

################################################################################

class SourceACL(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<SourceACL %s>' % self.source_acl_id

__all__.append('SourceACL')

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
                 ('OverrideSuite', 'overridesuite')]

# Why the heck don't we have any UNIQUE constraints in table suite?
# TODO: Add UNIQUE constraints for appropriate columns.
class Suite(object):
    def __init__(self, suite_name = None, version = None):
        self.suite_name = suite_name
        self.version = version

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

        q = object_session(self).query(Architecture). \
            filter(Architecture.suites.contains(self))
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
            filter(DBSource.suites.contains(self))

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

# TODO: should be removed because the implementation is too trivial
@session_wrapper
def get_suite_architectures(suite, skipsrc=False, skipall=False, session=None):
    """
    Returns list of Architecture objects for given C{suite} name

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

    return get_suite(suite, session).get_architectures(skipsrc, skipall)

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

    def __repr__(self):
        return '<Uid %s (%s)>' % (self.uid, self.name)

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

class UploadBlock(object):
    def __init__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return '<UploadBlock %s (%s)>' % (self.source, self.upload_block_id)

__all__.append('UploadBlock')

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
        tables_with_primary = (
            'architecture',
            'archive',
            'bin_associations',
            'binaries',
            'binary_acl',
            'binary_acl_map',
            'build_queue',
            'changelogs_text',
            'component',
            'config',
            'changes_pending_binaries',
            'changes_pending_files',
            'changes_pending_source',
            'dsc_files',
            'files',
            'fingerprint',
            'keyrings',
            'keyring_acl_map',
            'location',
            'maintainer',
            'new_comments',
            'override_type',
            'pending_bin_contents',
            'policy_queue',
            'priority',
            'section',
            'source',
            'source_acl',
            'src_associations',
            'src_format',
            'src_uploaders',
            'suite',
            'uid',
            'upload_blocks',
            # The following tables have primary keys but sqlalchemy
            # version 0.5 fails to reflect them correctly with database
            # versions before upgrade #41.
            #'changes',
            #'build_queue_files',
        )

        tables_no_primary = (
            'bin_contents',
            'changes_pending_files_map',
            'changes_pending_source_files',
            'changes_pool_files',
            'deb_contents',
            'override',
            'suite_architectures',
            'suite_src_formats',
            'suite_build_queue_copy',
            'udeb_contents',
            # see the comment above
            'changes',
            'build_queue_files',
        )

        views = (
            'almost_obsolete_all_associations',
            'almost_obsolete_src_associations',
            'any_associations_source',
            'bin_assoc_by_arch',
            'bin_associations_binaries',
            'binaries_suite_arch',
            'binfiles_suite_component_arch',
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

        # Sqlalchemy version 0.5 fails to reflect the SERIAL type
        # correctly and that is why we have to use a workaround. It can
        # be removed as soon as we switch to version 0.6.
        for table_name in tables_with_primary:
            table = Table(table_name, self.db_meta, \
                Column('id', Integer, primary_key = True), \
                autoload=True, useexisting=True)
            setattr(self, 'tbl_%s' % table_name, table)

        for table_name in tables_no_primary:
            table = Table(table_name, self.db_meta, autoload=True)
            setattr(self, 'tbl_%s' % table_name, table)

        for view_name in views:
            view = Table(view_name, self.db_meta, autoload=True)
            setattr(self, 'view_%s' % view_name, view)

    def __setupmappers(self):
        mapper(Architecture, self.tbl_architecture,
           properties = dict(arch_id = self.tbl_architecture.c.id,
               suites = relation(Suite, secondary=self.tbl_suite_architectures,
                   order_by='suite_name',
                   backref=backref('architectures', order_by='arch_string'))))

        mapper(Archive, self.tbl_archive,
               properties = dict(archive_id = self.tbl_archive.c.id,
                                 archive_name = self.tbl_archive.c.name))

        mapper(BinAssociation, self.tbl_bin_associations,
               properties = dict(ba_id = self.tbl_bin_associations.c.id,
                                 suite_id = self.tbl_bin_associations.c.suite,
                                 suite = relation(Suite),
                                 binary_id = self.tbl_bin_associations.c.bin,
                                 binary = relation(DBBinary)))

        mapper(PendingBinContents, self.tbl_pending_bin_contents,
               properties = dict(contents_id =self.tbl_pending_bin_contents.c.id,
                                 filename = self.tbl_pending_bin_contents.c.filename,
                                 package = self.tbl_pending_bin_contents.c.package,
                                 version = self.tbl_pending_bin_contents.c.version,
                                 arch = self.tbl_pending_bin_contents.c.arch,
                                 otype = self.tbl_pending_bin_contents.c.type))

        mapper(DebContents, self.tbl_deb_contents,
               properties = dict(binary_id=self.tbl_deb_contents.c.binary_id,
                                 package=self.tbl_deb_contents.c.package,
                                 suite=self.tbl_deb_contents.c.suite,
                                 arch=self.tbl_deb_contents.c.arch,
                                 section=self.tbl_deb_contents.c.section,
                                 filename=self.tbl_deb_contents.c.filename))

        mapper(UdebContents, self.tbl_udeb_contents,
               properties = dict(binary_id=self.tbl_udeb_contents.c.binary_id,
                                 package=self.tbl_udeb_contents.c.package,
                                 suite=self.tbl_udeb_contents.c.suite,
                                 arch=self.tbl_udeb_contents.c.arch,
                                 section=self.tbl_udeb_contents.c.section,
                                 filename=self.tbl_udeb_contents.c.filename))

        mapper(BuildQueue, self.tbl_build_queue,
               properties = dict(queue_id = self.tbl_build_queue.c.id))

        mapper(BuildQueueFile, self.tbl_build_queue_files,
               properties = dict(buildqueue = relation(BuildQueue, backref='queuefiles'),
                                 poolfile = relation(PoolFile, backref='buildqueueinstances')))

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

        mapper(BinaryACL, self.tbl_binary_acl,
               properties = dict(binary_acl_id = self.tbl_binary_acl.c.id))

        mapper(BinaryACLMap, self.tbl_binary_acl_map,
               properties = dict(binary_acl_map_id = self.tbl_binary_acl_map.c.id,
                                 fingerprint = relation(Fingerprint, backref="binary_acl_map"),
                                 architecture = relation(Architecture)))

        mapper(Component, self.tbl_component,
               properties = dict(component_id = self.tbl_component.c.id,
                                 component_name = self.tbl_component.c.name))

        mapper(DBConfig, self.tbl_config,
               properties = dict(config_id = self.tbl_config.c.id))

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
                                 location = relation(Location,
                                     # using lazy='dynamic' in the back
                                     # reference because we have A LOT of
                                     # files in one location
                                     backref=backref('files', lazy='dynamic'))))

        mapper(Fingerprint, self.tbl_fingerprint,
               properties = dict(fingerprint_id = self.tbl_fingerprint.c.id,
                                 uid_id = self.tbl_fingerprint.c.uid,
                                 uid = relation(Uid),
                                 keyring_id = self.tbl_fingerprint.c.keyring,
                                 keyring = relation(Keyring),
                                 source_acl = relation(SourceACL),
                                 binary_acl = relation(BinaryACL)))

        mapper(Keyring, self.tbl_keyrings,
               properties = dict(keyring_name = self.tbl_keyrings.c.name,
                                 keyring_id = self.tbl_keyrings.c.id))

        mapper(DBChange, self.tbl_changes,
               properties = dict(change_id = self.tbl_changes.c.id,
                                 poolfiles = relation(PoolFile,
                                                      secondary=self.tbl_changes_pool_files,
                                                      backref="changeslinks"),
                                 seen = self.tbl_changes.c.seen,
                                 source = self.tbl_changes.c.source,
                                 binaries = self.tbl_changes.c.binaries,
                                 architecture = self.tbl_changes.c.architecture,
                                 distribution = self.tbl_changes.c.distribution,
                                 urgency = self.tbl_changes.c.urgency,
                                 maintainer = self.tbl_changes.c.maintainer,
                                 changedby = self.tbl_changes.c.changedby,
                                 date = self.tbl_changes.c.date,
                                 version = self.tbl_changes.c.version,
                                 files = relation(ChangePendingFile,
                                                  secondary=self.tbl_changes_pending_files_map,
                                                  backref="changesfile"),
                                 in_queue_id = self.tbl_changes.c.in_queue,
                                 in_queue = relation(PolicyQueue,
                                                     primaryjoin=(self.tbl_changes.c.in_queue==self.tbl_policy_queue.c.id)),
                                 approved_for_id = self.tbl_changes.c.approved_for))

        mapper(ChangePendingBinary, self.tbl_changes_pending_binaries,
               properties = dict(change_pending_binary_id = self.tbl_changes_pending_binaries.c.id))

        mapper(ChangePendingFile, self.tbl_changes_pending_files,
               properties = dict(change_pending_file_id = self.tbl_changes_pending_files.c.id,
                                 filename = self.tbl_changes_pending_files.c.filename,
                                 size = self.tbl_changes_pending_files.c.size,
                                 md5sum = self.tbl_changes_pending_files.c.md5sum,
                                 sha1sum = self.tbl_changes_pending_files.c.sha1sum,
                                 sha256sum = self.tbl_changes_pending_files.c.sha256sum))

        mapper(ChangePendingSource, self.tbl_changes_pending_source,
               properties = dict(change_pending_source_id = self.tbl_changes_pending_source.c.id,
                                 change = relation(DBChange),
                                 maintainer = relation(Maintainer,
                                                       primaryjoin=(self.tbl_changes_pending_source.c.maintainer_id==self.tbl_maintainer.c.id)),
                                 changedby = relation(Maintainer,
                                                      primaryjoin=(self.tbl_changes_pending_source.c.changedby_id==self.tbl_maintainer.c.id)),
                                 fingerprint = relation(Fingerprint),
                                 source_files = relation(ChangePendingFile,
                                                         secondary=self.tbl_changes_pending_source_files,
                                                         backref="pending_sources")))


        mapper(KeyringACLMap, self.tbl_keyring_acl_map,
               properties = dict(keyring_acl_map_id = self.tbl_keyring_acl_map.c.id,
                                 keyring = relation(Keyring, backref="keyring_acl_map"),
                                 architecture = relation(Architecture)))

        mapper(Location, self.tbl_location,
               properties = dict(location_id = self.tbl_location.c.id,
                                 component_id = self.tbl_location.c.component,
                                 component = relation(Component),
                                 archive_id = self.tbl_location.c.archive,
                                 archive = relation(Archive),
                                 # FIXME: the 'type' column is old cruft and
                                 # should be removed in the future.
                                 archive_type = self.tbl_location.c.type))

        mapper(Maintainer, self.tbl_maintainer,
               properties = dict(maintainer_id = self.tbl_maintainer.c.id,
                   maintains_sources = relation(DBSource, backref='maintainer',
                       primaryjoin=(self.tbl_maintainer.c.id==self.tbl_source.c.maintainer)),
                   changed_sources = relation(DBSource, backref='changedby',
                       primaryjoin=(self.tbl_maintainer.c.id==self.tbl_source.c.changedby))))

        mapper(NewComment, self.tbl_new_comments,
               properties = dict(comment_id = self.tbl_new_comments.c.id))

        mapper(Override, self.tbl_override,
               properties = dict(suite_id = self.tbl_override.c.suite,
                                 suite = relation(Suite),
                                 package = self.tbl_override.c.package,
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

        mapper(PolicyQueue, self.tbl_policy_queue,
               properties = dict(policy_queue_id = self.tbl_policy_queue.c.id))

        mapper(Priority, self.tbl_priority,
               properties = dict(priority_id = self.tbl_priority.c.id))

        mapper(Section, self.tbl_section,
               properties = dict(section_id = self.tbl_section.c.id,
                                 section=self.tbl_section.c.section))

        mapper(DBSource, self.tbl_source,
               properties = dict(source_id = self.tbl_source.c.id,
                                 version = self.tbl_source.c.version,
                                 maintainer_id = self.tbl_source.c.maintainer,
                                 poolfile_id = self.tbl_source.c.file,
                                 poolfile = relation(PoolFile, backref=backref('source', uselist = False)),
                                 fingerprint_id = self.tbl_source.c.sig_fpr,
                                 fingerprint = relation(Fingerprint),
                                 changedby_id = self.tbl_source.c.changedby,
                                 srcfiles = relation(DSCFile,
                                                     primaryjoin=(self.tbl_source.c.id==self.tbl_dsc_files.c.source)),
                                 suites = relation(Suite, secondary=self.tbl_src_associations,
                                     backref='sources'),
                                 srcuploaders = relation(SrcUploader)))

        mapper(SourceACL, self.tbl_source_acl,
               properties = dict(source_acl_id = self.tbl_source_acl.c.id))

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
               properties = dict(suite_id = self.tbl_suite.c.id,
                                 policy_queue = relation(PolicyQueue),
                                 copy_queues = relation(BuildQueue, secondary=self.tbl_suite_build_queue_copy)))

        mapper(SuiteSrcFormat, self.tbl_suite_src_formats,
               properties = dict(suite_id = self.tbl_suite_src_formats.c.suite,
                                 suite = relation(Suite, backref='suitesrcformats'),
                                 src_format_id = self.tbl_suite_src_formats.c.src_format,
                                 src_format = relation(SrcFormat)))

        mapper(Uid, self.tbl_uid,
               properties = dict(uid_id = self.tbl_uid.c.id,
                                 fingerprint = relation(Fingerprint)))

        mapper(UploadBlock, self.tbl_upload_blocks,
               properties = dict(upload_block_id = self.tbl_upload_blocks.c.id,
                                 fingerprint = relation(Fingerprint, backref="uploadblocks"),
                                 uid = relation(Uid, backref="uploadblocks")))

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


