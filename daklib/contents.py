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

from multiprocessing import Pool
from shutil import rmtree
from subprocess import Popen, PIPE, check_call
from tempfile import mkdtemp

import os.path

class ContentsWriter(object):
    '''
    ContentsWriter writes the Contents-$arch.gz files.
    '''
    def __init__(self, suite, architecture, overridetype, component = None):
        '''
        The constructor clones its arguments into a new session object to make
        sure that the new ContentsWriter object can be executed in a different
        thread.
        '''
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
            'arch_all':      get_architecture('all', self.session).arch_id,
            'arch':          self.architecture.arch_id,
            'type_id':       self.overridetype.overridetype_id,
            'type':          self.overridetype.overridetype,
        }

        if self.component is not None:
            params['component'] = self.component.component_id
            sql = '''
create temp table newest_binaries (
    id integer primary key,
    package text);

create index newest_binaries_by_package on newest_binaries (package);

insert into newest_binaries (id, package)
    select distinct on (package) id, package from binaries
        where type = :type and
            (architecture = :arch_all or architecture = :arch) and
            id in (select bin from bin_associations where suite = :suite)
        order by package, version desc;

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

        else:
            sql = '''
create temp table newest_binaries (
    id integer primary key,
    package text);

create index newest_binaries_by_package on newest_binaries (package);

insert into newest_binaries (id, package)
    select distinct on (package) id, package from binaries
        where type = :type and
            (architecture = :arch_all or architecture = :arch) and
            id in (select bin from bin_associations where suite = :suite)
        order by package, version desc;

with

unique_override as
    (select distinct on (o.package, s.section) o.package, s.section
        from override o, section s
        where o.suite = :overridesuite and o.type = :type_id and o.section = s.id
        order by o.package, s.section, o.modified desc)

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

    def output_filename(self):
        '''
        Returns the name of the output file.
        '''
        values = {
            'root': Config()['Dir::Root'],
            'suite': self.suite.suite_name,
            'architecture': self.architecture.arch_string
        }
        if self.component is None:
            return "%(root)s/dists/%(suite)s/Contents-%(architecture)s.gz" % values
        values['component'] = self.component.component_name
        return "%(root)s/dists/%(suite)s/%(component)s/Contents-%(architecture)s.gz" % values

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
        command = ['gzip', '--rsyncable']
        final_filename = self.output_filename()
        temp_filename = final_filename + '.new'
        output_file = open(temp_filename, 'w')
        gzip = Popen(command, stdin = PIPE, stdout = output_file)
        gzip.stdin.write(self.get_header())
        for item in self.fetch():
            gzip.stdin.write(item)
        gzip.stdin.close()
        output_file.close()
        gzip.wait()
        try:
            os.remove(final_filename)
        except:
            pass
        os.rename(temp_filename, final_filename)
        os.chmod(final_filename, 0664)

    @classmethod
    def log_result(class_, result):
        '''
        Writes a result message to the logfile.
        '''
        class_.logger.log(result)

    @classmethod
    def write_all(class_, logger, suite_names = [], force = False):
        '''
        Writes all Contents files for suites in list suite_names which defaults
        to all 'touchable' suites if not specified explicitely. Untouchable
        suites will be included if the force argument is set to True.
        '''
        class_.logger = logger
        session = DBConn().session()
        suite_query = session.query(Suite)
        if len(suite_names) > 0:
            suite_query = suite_query.filter(Suite.suite_name.in_(suite_names))
        if not force:
            suite_query = suite_query.filter_by(untouchable = False)
        deb_id = get_override_type('deb', session).overridetype_id
        udeb_id = get_override_type('udeb', session).overridetype_id
        main_id = get_component('main', session).component_id
        non_free_id = get_component('non-free', session).component_id
        pool = Pool()
        for suite in suite_query:
            suite_id = suite.suite_id
            for architecture in suite.get_architectures(skipsrc = True, skipall = True):
                arch_id = architecture.arch_id
                # handle 'deb' packages
                pool.apply_async(generate_helper, (suite_id, arch_id, deb_id), \
                    callback = class_.log_result)
                # handle 'udeb' packages for 'main' and 'non-free'
                pool.apply_async(generate_helper, (suite_id, arch_id, udeb_id, main_id), \
                    callback = class_.log_result)
                pool.apply_async(generate_helper, (suite_id, arch_id, udeb_id, non_free_id), \
                    callback = class_.log_result)
        pool.close()
        pool.join()
        session.close()

def generate_helper(suite_id, arch_id, overridetype_id, component_id = None):
    '''
    This function is called in a new subprocess.
    '''
    session = DBConn().session()
    suite = Suite.get(suite_id, session)
    architecture = Architecture.get(arch_id, session)
    overridetype = OverrideType.get(overridetype_id, session)
    log_message = [suite.suite_name, architecture.arch_string, overridetype.overridetype]
    if component_id is None:
        component = None
    else:
        component = Component.get(component_id, session)
        log_message.append(component.component_name)
    contents_writer = ContentsWriter(suite, architecture, overridetype, component)
    contents_writer.write_file()
    return log_message


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
    def __init__(self, dscfilename):
        '''
        The dscfilename is a name of a DSC file that will be extracted.
        '''
        self.root_directory = os.path.join(mkdtemp(), 'root')
        command = ('dpkg-source', '--no-copy', '--no-check', '-x', dscfilename,
            self.root_directory)
        # dpkg-source does not have a --quiet option
        devnull = open(os.devnull, 'w')
        check_call(command, stdout = devnull, stderr = devnull)
        devnull.close()

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
    scanner = SourceContentsScanner(source_id)
    scanner.scan()

