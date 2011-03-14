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
from daklib.threadpool import ThreadPool
from multiprocessing import Pool

from sqlalchemy import desc, or_
from sqlalchemy.exc import IntegrityError
from subprocess import Popen, PIPE, call

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

select bc.file, o.section || '/' || b.package as package
    from newest_binaries b, bin_contents bc, unique_override o
    where b.id = bc.binary_id and o.package = b.package
    order by bc.file, b.package'''

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

select bc.file, o.section || '/' || b.package as package
    from newest_binaries b, bin_contents bc, unique_override o
    where b.id = bc.binary_id and o.package = b.package
    order by bc.file, b.package'''

        return self.session.query("file", "package").from_statement(sql). \
            params(params)

    def formatline(self, filename, package_list):
        '''
        Returns a formatted string for the filename argument.
        '''
        package_list = ','.join(package_list)
        return "%-55s %s\n" % (filename, package_list)

    def fetch(self):
        '''
        Yields a new line of the Contents-$arch.gz file in filename order.
        '''
        last_filename = None
        package_list = []
        for filename, package in self.query().yield_per(100):
            if filename != last_filename:
                if last_filename is not None:
                    yield self.formatline(last_filename, package_list)
                last_filename = filename
                package_list = []
            package_list.append(package)
        if last_filename is not None:
            yield self.formatline(last_filename, package_list)
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
        os.remove(final_filename)
        os.rename(temp_filename, final_filename)
        os.chmod(final_filename, 0664)

    @classmethod
    def write_all(class_, suite_names = [], force = False):
        '''
        Writes all Contents files for suites in list suite_names which defaults
        to all 'touchable' suites if not specified explicitely. Untouchable
        suites will be included if the force argument is set to True.
        '''
        session = DBConn().session()
        suite_query = session.query(Suite)
        if len(suite_names) > 0:
            suite_query = suite_query.filter(Suite.suite_name.in_(suite_names))
        if not force:
            suite_query = suite_query.filter_by(untouchable = False)
        pool = Pool()
        for suite in suite_query:
            for architecture in suite.get_architectures(skipsrc = True, skipall = True):
                # handle 'deb' packages
                command = ['dak', 'contents', '-s', suite.suite_name, \
                    'generate_helper', architecture.arch_string, 'deb']
                pool.apply_async(call, (command, ))
                # handle 'udeb' packages for 'main' and 'non-free'
                command = ['dak', 'contents', '-s', suite.suite_name, \
                    'generate_helper', architecture.arch_string, 'udeb', 'main']
                pool.apply_async(call, (command, ))
                command = ['dak', 'contents', '-s', suite.suite_name, \
                    'generate_helper', architecture.arch_string, 'udeb', 'non-free']
                pool.apply_async(call, (command, ))
        pool.close()
        pool.join()
        session.close()


class ContentsScanner(object):
    '''
    ContentsScanner provides a threadsafe method scan() to scan the contents of
    a DBBinary object.
    '''
    def __init__(self, binary):
        '''
        The argument binary is the actual DBBinary object that should be
        scanned.
        '''
        self.binary_id = binary.binary_id

    def scan(self, dummy_arg = None):
        '''
        This method does the actual scan and fills in the associated BinContents
        property. It commits any changes to the database. The argument dummy_arg
        is ignored but needed by our threadpool implementation.
        '''
        session = DBConn().session()
        binary = session.query(DBBinary).get(self.binary_id)
        empty_package = True
        for filename in binary.scan_contents():
            binary.contents.append(BinContents(file = filename))
            empty_package = False
        if empty_package:
            binary.contents.append(BinContents(file = 'EMPTY_PACKAGE'))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            binary.contents.append(BinContents(file = 'DUPLICATE_FILENAMES'))
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
        threadpool = ThreadPool()
        for binary in query.yield_per(100):
            threadpool.queueTask(ContentsScanner(binary).scan)
        threadpool.joinAll()
        remaining = remaining()
        session.close()
        return { 'processed': processed, 'remaining': remaining }
