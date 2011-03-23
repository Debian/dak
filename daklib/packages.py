#!/usr/bin/env python
"""
Helper code for packages generation.

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2011 Torsten Werner <twerner@debian.org>
@copyright: 2011 Mark Hymers <mhy@debian.org>
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
from subprocess import Popen, PIPE

import os.path

class PackagesScanner(object):
    '''
    PackagesScanner provides a threadsafe method scan() to scan the metadata of
    a DBBinary object.
    '''
    def __init__(self, binary_id):
        '''
        The argument binary_id is the id of the DBBinary object that
        should be scanned.
        '''
        self.binary_id = binary_id

    def scan(self, dummy_arg = None):
        '''
        This method does the actual scan and fills in the associated metadata
        property. It commits any changes to the database. The argument dummy_arg
        is ignored but needed by our threadpool implementation.
        '''
        session = DBConn().session()
        binary = session.query(DBBinary).get(self.binary_id)
        fileset = set(binary.read_control())
        print fileset
        #if len(fileset) == 0:
        #    fileset.add('EMPTY_PACKAGE')
        #for filename in fileset:
        #    binary.contents.append(BinContents(file = filename))
        #session.commit()
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
            pool.apply_async(scan_helper, (binary.binary_id, ))
        pool.close()
        pool.join()
        remaining = remaining()
        session.close()
        return { 'processed': processed, 'remaining': remaining }

def scan_helper(binary_id):
    '''
    This function runs in a subprocess.
    '''
    scanner = PackagesScanner(binary_id)
    scanner.scan()
