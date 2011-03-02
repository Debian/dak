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

from sqlalchemy import desc, or_
from subprocess import Popen, PIPE

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
        self.suite = suite.clone()
        self.session = self.suite.session()
        self.architecture = architecture.clone(self.session)
        self.overridetype = overridetype.clone(self.session)
        if component is not None:
            self.component = component.clone(self.session)
        else:
            self.component = None

    def query(self):
        '''
        Returns a query object that is doing most of the work.
        '''
        params = {
            'suite':    self.suite.suite_id,
            'arch_all': get_architecture('all', self.session).arch_id,
            'arch':     self.architecture.arch_id,
            'type_id':  self.overridetype.overridetype_id,
            'type':     self.overridetype.overridetype,
        }

        if self.component is not None:
            params['component'] = component.component_id
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
        where o.suite = :suite and o.type = :type_id and o.section = s.id and
        o.component = :component)

select bc.file, substring(o.section from position('/' in o.section) + 1) || '/' || b.package as package
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
        where o.suite = :suite and o.type = :type_id and o.section = s.id
        order by o.package, s.section, o.modified desc)

select bc.file, substring(o.section from position('/' in o.section) + 1) || '/' || b.package as package
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
        return "%-60s%s\n" % (filename, package_list)

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
            return "%(root)s%(suite)s/Contents-%(architecture)s.gz" % values
        values['component'] = self.component.component_name
        return "%(root)s%(suite)s/%(component)s/Contents-%(architecture)s.gz" % values

    def write_file(self):
        '''
        Write the output file.
        '''
        command = ['gzip', '--rsyncable']
        output_file = open(self.output_filename(), 'w')
        pipe = Popen(command, stdin = PIPE, stdout = output_file).stdin
        for item in self.fetch():
            pipe.write(item)
        pipe.close()
        output_file.close()


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
        for filename in binary.scan_contents():
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
        threadpool = ThreadPool()
        for binary in query.yield_per(100):
            threadpool.queueTask(ContentsScanner(binary).scan)
        threadpool.joinAll()
        remaining = remaining()
        session.close()
        return { 'processed': processed, 'remaining': remaining }
