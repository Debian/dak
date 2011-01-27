#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import *
from daklib.cruft import *

import unittest

class CruftTestCase(DBDakTestCase):
    """
    This class checks various functions of cruft-report.
    """

    def setUp(self):
        super(CruftTestCase, self).setUp()
        self.setup_binaries()
        # flush to make sure that the setup is correct
        self.session.flush()

    def test_newer_version(self):
        'tests newer_version()'

        list = newer_version('squeeze', 'sid', self.session)
        self.assertEqual([], list)
        self.file['sl_3.03-17.dsc'] = PoolFile(filename = 'main/s/sl/sl_3.03-17.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.source['sl_3.03-17'] = DBSource(source = 'sl', version = '3.03-17', \
            maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['sl_3.03-17.dsc'], install_date = self.now())
        self.source['sl_3.03-17'].suites.append(self.suite['squeeze'])
        list = newer_version('squeeze', 'sid', self.session)
        self.assertEqual([('sl', '3.03-16', '3.03-17')], list)

if __name__ == '__main__':
    unittest.main()
