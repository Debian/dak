#!/usr/bin/env python
"""
Helper code for contents generation.

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2011 Torsten Werner <twerner@debian.org>
@license: GNU General Public License version 2 or later
"""

################################################################################

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

from daklib.dbconn import *
from daklib.config import Config
from daklib.filewriter import BinaryContentsFileWriter, SourceContentsFileWriter

from multiprocessing import Pool
from shutil import rmtree
from tempfile import mkdtemp

import daklib.daksubprocess
import os.path

class BinaryContentsWriter(object):
    '''
    BinaryContentsWriter writes the Contents-$arch.gz files.
    '''
    def __init__(self, suite, architecture, overridetype, component):
        self.suite = suite
        self.architecture = architecture
        self.overridetype = overridetype
        self.component = component
        self.session = suite.session()

    def query(self):
        '''
        Returns a query object that is doing most of the work.
        '''
        overridesuite = self.suite
        if self.suite.overridesuite is not None:
            overridesuite = get_suite(self.suite.overridesuite, self.session)
        params = {
            'suite':         self.suite.suite_id,
            'overridesuite': overridesuite.suite_id,
            'component':     self.component.component_id,
            'arch_all':      get_architecture('all', self.session).arch_id,
            'arch':          self.architecture.arch_id,
            'type_id':       self.overridetype.overridetype_id,
            'type':          self.overridetype.overridetype,
        }

        sql_create_temp = '''
create temp table newest_binaries (
    id integer primary key,
    package text);

create index newest_binaries_by_package on newest_binaries (package);

insert into newest_binaries (id, package)
    select distinct on (package) id, package from binaries
        where type = :type and
            (architecture = :arch_all or architecture = :arch) and
            id in (select bin from bin_associations where suite = :suite)
        order by package, version desc;'''
        self.session.execute(sql_create_temp, params=params)

        sql = '''
with

unique_override as
    (select o.package, s.section
        from override o, section s
        where o.suite = :overridesuite and o.type = :type_id and o.section = s.id and
        o.component = :component)

select bc.file, string_agg(o.section || '/' || b.package, ',' order by b.package) as pkglist
    from newest_binaries b, bin_contents bc, unique_override o
    where b.id = bc.binary_id and o.package = b.package
    group by bc.file'''

        return self.session.query("file", "pkglist").from_statement(sql). \
            params(params)

    def formatline(self, filename, package_list):
        '''
        Returns a formatted string for the filename argument.
        '''
        return "%-55s %s\n" % (filename, package_list)

    def fetch(self):
        '''
        Yields a new line of the Contents-$arch.gz file in filename order.
        '''
        for filename, package_list in self.query().yield_per(100):
            yield self.formatline(filename, package_list)
        # end transaction to return connection to pool
        self.session.rollback()

    def get_list(self):
        '''
        Returns a list of lines for the Contents-$arch.gz file.
        '''
        return [item for item in self.fetch()]

    def writer(self):
        '''
        Returns a writer object.
        '''
        values = {
            'archive':      self.suite.archive.path,
            'suite':        self.suite.suite_name,
            'component':    self.component.component_name,
            'debtype':      self.overridetype.overridetype,
            'architecture': self.architecture.arch_string,
        }
        return BinaryContentsFileWriter(**values)

    def get_header(self):
        '''
        Returns the header for the Contents files as a string.
        '''
        header_file = None
        try:
            filename = os.path.join(Config()['Dir::Templates'], 'contents')
            header_file = open(filename)
            return header_file.read()
        finally:
            if header_file:
                header_file.close()

    def write_file(self):
        '''
        Write the output file.
        '''
        writer = self.writer()
        file = writer.open()
        file.write(self.get_header())
        for item in self.fetch():
            file.write(item)
        writer.close()


class SourceContentsWriter(object):
    '''
    SourceContentsWriter writes the Contents-source.gz files.
    '''
    def __init__(self, suite, component):
        self.suite = suite
        self.component = component
        self.session = suite.session()

    def query(self):
        '''
        Returns a query object that is doing most of the work.
        '''
        params = {
            'suite_id':     self.suite.suite_id,
            'component_id': self.component.component_id,
        }

        sql_create_temp = '''
create temp table newest_sources (
    id integer primary key,
    source text);

create index sources_binaries_by_source on newest_sources (source);

insert into newest_sources (id, source)
    select distinct on (source) s.id, s.source from source s
        join files_archive_map af on s.file = af.file_id
        where s.id in (select source from src_associations where suite = :suite_id)
            and af.component_id = :component_id
        order by source, version desc;'''
        self.session.execute(sql_create_temp, params=params)

        sql = '''
select sc.file, string_agg(s.source, ',' order by s.source) as pkglist
    from newest_sources s, src_contents sc
    where s.id = sc.source_id group by sc.file'''

        return self.session.query("file", "pkglist").from_statement(sql). \
            params(params)

    def formatline(self, filename, package_list):
        '''
        Returns a formatted string for the filename argument.
        '''
        return "%s\t%s\n" % (filename, package_list)

    def fetch(self):
        '''
        Yields a new line of the Contents-source.gz file in filename order.
        '''
        for filename, package_list in self.query().yield_per(100):
            yield self.formatline(filename, package_list)
        # end transaction to return connection to pool
        self.session.rollback()

    def get_list(self):
        '''
        Returns a list of lines for the Contents-source.gz file.
        '''
        return [item for item in self.fetch()]

    def writer(self):
        '''
        Returns a writer object.
        '''
        values = {
            'archive':   self.suite.archive.path,
            'suite':     self.suite.suite_name,
            'component': self.component.component_name
        }
        return SourceContentsFileWriter(**values)

    def write_file(self):
        '''
        Write the output file.
        '''
        writer = self.writer()
        file = writer.open()
        for item in self.fetch():
            file.write(item)
        writer.close()


def binary_helper(suite_id, arch_id, overridetype_id, component_id):
    '''
    This function is called in a new subprocess and multiprocessing wants a top
    level function.
    '''
    session = DBConn().session(work_mem = 1000)
    suite = Suite.get(suite_id, session)
    architecture = Architecture.get(arch_id, session)
    overridetype = OverrideType.get(overridetype_id, session)
    component = Component.get(component_id, session)
    log_message = [suite.suite_name, architecture.arch_string, \
        overridetype.overridetype, component.component_name]
    contents_writer = BinaryContentsWriter(suite, architecture, overridetype, component)
    contents_writer.write_file()
    session.close()
    return log_message

def source_helper(suite_id, component_id):
    '''
    This function is called in a new subprocess and multiprocessing wants a top
    level function.
    '''
    session = DBConn().session(work_mem = 1000)
    suite = Suite.get(suite_id, session)
    component = Component.get(component_id, session)
    log_message = [suite.suite_name, 'source', component.component_name]
    contents_writer = SourceContentsWriter(suite, component)
    contents_writer.write_file()
    session.close()
    return log_message

class ContentsWriter(object):
    '''
    Loop over all suites, architectures, overridetypes, and components to write
    all contents files.
    '''
    @classmethod
    def log_result(class_, result):
        '''
        Writes a result message to the logfile.
        '''
        class_.logger.log(result)

    @classmethod
    def write_all(class_, logger, archive_names = [], suite_names = [], component_names = [], force = False):
        '''
        Writes all Contents files for suites in list suite_names which defaults
        to all 'touchable' suites if not specified explicitely. Untouchable
        suites will be included if the force argument is set to True.
        '''
        class_.logger = logger
        session = DBConn().session()
        suite_query = session.query(Suite)
        if len(archive_names) > 0:
            suite_query = suite_query.join(Suite.archive).filter(Archive.archive_name.in_(archive_names))
        if len(suite_names) > 0:
            suite_query = suite_query.filter(Suite.suite_name.in_(suite_names))
        component_query = session.query(Component)
        if len(component_names) > 0:
            component_query = component_query.filter(Component.component_name.in_(component_names))
        if not force:
            suite_query = suite_query.filter(Suite.untouchable == False)
        deb_id = get_override_type('deb', session).overridetype_id
        udeb_id = get_override_type('udeb', session).overridetype_id
        pool = Pool()
        for suite in suite_query:
            suite_id = suite.suite_id
            for component in component_query:
                component_id = component.component_id
                # handle source packages
                pool.apply_async(source_helper, (suite_id, component_id),
                    callback = class_.log_result)
                for architecture in suite.get_architectures(skipsrc = True, skipall = True):
                    arch_id = architecture.arch_id
                    # handle 'deb' packages
                    pool.apply_async(binary_helper, (suite_id, arch_id, deb_id, component_id), \
                        callback = class_.log_result)
                    # handle 'udeb' packages
                    pool.apply_async(binary_helper, (suite_id, arch_id, udeb_id, component_id), \
                        callback = class_.log_result)
        pool.close()
        pool.join()
        session.close()


class BinaryContentsScanner(object):
    '''
    BinaryContentsScanner provides a threadsafe method scan() to scan the
    contents of a DBBinary object.
    '''
    def __init__(self, binary_id):
        '''
        The argument binary_id is the id of the DBBinary object that
        should be scanned.
        '''
        self.binary_id = binary_id

    def scan(self, dummy_arg = None):
        '''
        This method does the actual scan and fills in the associated BinContents
        property. It commits any changes to the database. The argument dummy_arg
        is ignored but needed by our threadpool implementation.
        '''
        session = DBConn().session()
        binary = session.query(DBBinary).get(self.binary_id)
        fileset = set(binary.scan_contents())
        if len(fileset) == 0:
            fileset.add('EMPTY_PACKAGE')
        for filename in fileset:
            binary.contents.append(BinContents(file = filename))
        session.commit()
        session.close()

    @classmethod
    def scan_all(class_, limit = None):
        '''
        The class method scan_all() scans all binaries using multiple threads.
        The number of binaries to be scanned can be limited with the limit
        argument. Returns the number of processed and remaining packages as a
        dict.
        '''
        session = DBConn().session()
        query = session.query(DBBinary).filter(DBBinary.contents == None)
        remaining = query.count
        if limit is not None:
            query = query.limit(limit)
        processed = query.count()
        pool = Pool()
        for binary in query.yield_per(100):
            pool.apply_async(binary_scan_helper, (binary.binary_id, ))
        pool.close()
        pool.join()
        remaining = remaining()
        session.close()
        return { 'processed': processed, 'remaining': remaining }

def binary_scan_helper(binary_id):
    '''
    This function runs in a subprocess.
    '''
    scanner = BinaryContentsScanner(binary_id)
    scanner.scan()

class UnpackedSource(object):
    '''
    UnpackedSource extracts a source package into a temporary location and
    gives you some convinient function for accessing it.
    '''
    def __init__(self, dscfilename, tmpbasedir=None):
        '''
        The dscfilename is a name of a DSC file that will be extracted.
        '''
        basedir = tmpbasedir if tmpbasedir else Config()['Dir::TempPath']
        temp_directory = mkdtemp(dir = basedir)
        self.root_directory = os.path.join(temp_directory, 'root')
        command = ('dpkg-source', '--no-copy', '--no-check', '-q', '-x',
            dscfilename, self.root_directory)
        daklib.daksubprocess.check_call(command)

    def get_root_directory(self):
        '''
        Returns the name of the package's root directory which is the directory
        where the debian subdirectory is located.
        '''
        return self.root_directory

    def get_changelog_file(self):
        '''
        Returns a file object for debian/changelog or None if no such file exists.
        '''
        changelog_name = os.path.join(self.root_directory, 'debian', 'changelog')
        try:
            return open(changelog_name)
        except IOError:
            return None

    def get_all_filenames(self):
        '''
        Returns an iterator over all filenames. The filenames will be relative
        to the root directory.
        '''
        skip = len(self.root_directory) + 1
        for root, _, files in os.walk(self.root_directory):
            for name in files:
                yield os.path.join(root[skip:], name)

    def cleanup(self):
        '''
        Removes all temporary files.
        '''
        if self.root_directory is None:
            return
        parent_directory = os.path.dirname(self.root_directory)
        rmtree(parent_directory)
        self.root_directory = None

    def __del__(self):
        '''
        Enforce cleanup.
        '''
        self.cleanup()


class SourceContentsScanner(object):
    '''
    SourceContentsScanner provides a method scan() to scan the contents of a
    DBSource object.
    '''
    def __init__(self, source_id):
        '''
        The argument source_id is the id of the DBSource object that
        should be scanned.
        '''
        self.source_id = source_id

    def scan(self):
        '''
        This method does the actual scan and fills in the associated SrcContents
        property. It commits any changes to the database.
        '''
        session = DBConn().session()
        source = session.query(DBSource).get(self.source_id)
        fileset = set(source.scan_contents())
        for filename in fileset:
            source.contents.append(SrcContents(file = filename))
        session.commit()
        session.close()

    @classmethod
    def scan_all(class_, limit = None):
        '''
        The class method scan_all() scans all source using multiple processes.
        The number of sources to be scanned can be limited with the limit
        argument. Returns the number of processed and remaining packages as a
        dict.
        '''
        session = DBConn().session()
        query = session.query(DBSource).filter(DBSource.contents == None)
        remaining = query.count
        if limit is not None:
            query = query.limit(limit)
        processed = query.count()
        pool = Pool()
        for source in query.yield_per(100):
            pool.apply_async(source_scan_helper, (source.source_id, ))
        pool.close()
        pool.join()
        remaining = remaining()
        session.close()
        return { 'processed': processed, 'remaining': remaining }

def source_scan_helper(source_id):
    '''
    This function runs in a subprocess.
    '''
    try:
        scanner = SourceContentsScanner(source_id)
        scanner.scan()
    except Exception as e:
        print e
