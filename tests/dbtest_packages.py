#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Architecture, Suite

import unittest

class PackageTestCase(DBDakTestCase):
    """
    xxx
    """

    def setup_architectures(self):
        "setup a hash of Architecture objects in self.arch"

        self.arch = {}
        for arch_string in ('source', 'all', 'i386', 'amd64'):
            self.arch[arch_string] = Architecture(arch_string)
        # hard code ids for source and all
        self.arch['source'].arch_id = 1
        self.arch['all'].arch_id = 2
        for _, architecture in self.arch.items():
            self.session.add(architecture)
            self.session.flush()
            self.session.refresh(architecture)

    def setUp(self):
        super(PackageTestCase, self).setUp()
        self.setup_architectures()

    def test_packages(self):
        self.assertEqual(1, self.arch['source'].arch_id)
        self.assertEqual(2, self.arch['all'].arch_id)

if __name__ == '__main__':
    unittest.main()
