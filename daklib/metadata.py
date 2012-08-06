#!/usr/bin/env python
"""
Helper code for packages and sources generation.

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

class MetadataScanner(object):
    '''
    MetadataScanner provides a threadsafe method scan() to scan the metadata of
    a DBSource or DBBinary object depending on what is passed as dbclass'''

    def __init__(self, dbclass, pkid, verbose=True):
        '''
        The argument binary_id is the id of the DBBinary object that

        should be scanned.
        '''
        self.verbose = True
        self.dbclass = dbclass
        self.pkid = pkid

    def scan(self, dummy_arg = None):
        '''
        This method does the actual scan and fills in the associated metadata
        property. It commits any changes to the database. The argument dummy_arg
        is ignored but needed by our threadpool implementation.
        '''
        obj = None
        fullpath = 'UNKNOWN PATH'

        session = DBConn().session()
        try:
            obj = session.query(self.dbclass).get(self.pkid)
            fullpath = obj.poolfile.fullpath
            import_metadata_into_db(obj, session=session)
            if self.verbose:
                print "Imported %s (%s)" % (self.pkid, fullpath)
            session.commit()
        except Exception as e:
            print "Failed to import %s [id=%s; fullpath=%s]" % (self.dbclass.__name__, self.pkid, fullpath)
            print "Exception: ", e
            session.rollback()

        session.close()

    @classmethod
    def scan_all(class_, scantype='source', limit = None):
        '''
        The class method scan_all() scans all sources using multiple threads.
        The number of sources to be scanned can be limited with the limit
        argument. Returns the number of processed and remaining files as a
        dict.
        '''
        session = DBConn().session()
        if scantype == 'source':
            dbclass = DBSource
            query = session.query(DBSource).filter(~DBSource.source_id.in_(session.query(SourceMetadata.source_id.distinct())))
            t = 'sources'
        else:
            # Otherwise binary
            dbclass = DBBinary
            query = session.query(DBBinary).filter(~DBBinary.binary_id.in_(session.query(BinaryMetadata.binary_id.distinct())))
            t = 'binaries'

        remaining = query.count
        if limit is not None:
            query = query.limit(limit)
        processed = query.count()
        pool = Pool(processes=10)
        for obj in query.yield_per(100):
            pool.apply_async(scan_helper, (dbclass, obj.pkid, ))
        pool.close()
        pool.join()
        remaining = remaining()
        session.close()
        return { 'processed': processed, 'remaining': remaining , 'type': t}

def scan_helper(dbclass, source_id):
    '''
    This function runs in a subprocess.
    '''
    scanner = MetadataScanner(dbclass, source_id)
    scanner.scan()
