#!/usr/bin/env python

from base_test import DakTestCase

from dak.copy_installer import InstallerCopier

import unittest

class ImportTestCase(DakTestCase):
    def test_arguments(self):
        '''test constructor arguments'''
        # version argument is required
        self.assertRaises(KeyError, InstallerCopier)

        copier = InstallerCopier(version = '20110106')
        self.assertEqual('20110106', copier.version)
        self.assertEqual('unstable', copier.source)
        self.assertEqual('testing', copier.dest)

        copier = InstallerCopier(version = '20110106', source = \
                'proposed-updates')
        self.assertEqual('proposed-updates', copier.source)

        copier = InstallerCopier(version = '20110106', dest = 'stable')
        self.assertEqual('stable', copier.dest)

    def test_dir_names(self):
        copier = InstallerCopier(version = '20110106')
        self.assertEqual('tests/fixtures/ftp/dists/unstable/main',
                copier.source_dir)
        self.assertEqual('tests/fixtures/ftp/dists/testing/main',
                copier.dest_dir)

    def missing_source(self):
        copier = InstallerCopier(version = '20110106', source = 'foo')

    def missing_dest(self):
        copier = InstallerCopier(version = '20110106', dest = 'bar')

    def test_suites(self):
        self.assertRaises(IOError, self.missing_source)
        self.assertRaises(IOError, self.missing_dest)

    def test_copy(self):
        copier = InstallerCopier(version = '20110106')
        self.assertEqual(['amd64'], copier.architectures)
        self.assertEqual(['i386'], copier.skip_architectures)
        self.assertEqual( \
            [('tests/fixtures/ftp/dists/unstable/main/installer-amd64/20110106', \
              'tests/fixtures/ftp/dists/testing/main/installer-amd64/20110106'),], \
            copier.trees_to_copy)
        self.assertEqual([('20110106', \
            'tests/fixtures/ftp/dists/testing/main/installer-amd64/current')], \
            copier.symlinks_to_create)
        self.assertEqual('''
Will copy installer version 20110106 from suite unstable to
testing.
Architectures to copy: amd64
Architectures to skip: i386''', copier.get_message())

if __name__ == '__main__':
    unittest.main()
