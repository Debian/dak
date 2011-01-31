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
        self.install_date = self.now()
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
            poolfile = self.file['sl_3.03-17.dsc'], install_date = self.install_date)
        self.source['sl_3.03-17'].suites.append(self.suite['squeeze'])
        list = newer_version('squeeze', 'sid', self.session)
        self.assertEqual([('sl', '3.03-16', '3.03-17')], list)

    def test_multiple_source(self):
        'tests functions related to report_multiple_source()'

        # test get_package_names()
        suite = get_suite('sid', self.session)
        self.assertEqual([('gnome-hello', ), ('hello', )], \
            get_package_names(suite).all())
        # test class NamedSource
        src = NamedSource(suite, 'hello')
        self.assertEqual('hello', src.source)
        self.assertEqual(['2.2-1', '2.2-2'], src.versions)
        self.assertEqual('hello(2.2-1, 2.2-2)', str(src))
        # test class DejavuBinary
        bin = DejavuBinary(suite, 'hello')
        self.assertEqual(False, bin.has_multiple_sources())
        # add another binary
        self.file['hello_2.2-3'] = PoolFile(filename = 'main/s/sl/hello_2.2-3_i386.deb', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.binary['hello_2.2-3_i386'] = DBBinary(package = 'hello', \
            source = self.source['sl_3.03-16'], version = '2.2-3', \
            maintainer = self.maintainer['maintainer'], \
            architecture = self.arch['i386'], \
            poolfile = self.file['hello_2.2-3'])
        self.session.add(self.binary['hello_2.2-3_i386'])
        bin = DejavuBinary(suite, 'hello')
        self.assertEqual(False, bin.has_multiple_sources())
        # add it to suite sid
        self.binary['hello_2.2-3_i386'].suites.append(self.suite['sid'])
        bin = DejavuBinary(suite, 'hello')
        self.assertEqual(True, bin.has_multiple_sources())
        self.assertEqual('hello built by: hello(2.2-1, 2.2-2), sl(3.03-16)', \
            str(bin))

if __name__ == '__main__':
    unittest.main()
