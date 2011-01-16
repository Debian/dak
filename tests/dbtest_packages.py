#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Architecture, Suite, get_suite_architectures

import unittest

class PackageTestCase(DBDakTestCase):
    """
    PackageTestCase checks the handling of source and binary packages in dak's
    database.
    """

    def setup_architectures(self):
        "setup a hash of Architecture objects in self.arch"

        self.arch = {}
        for arch_string in ('source', 'all', 'i386', 'amd64', 'kfreebsd-i386'):
            self.arch[arch_string] = Architecture(arch_string)
        # hard code ids for source and all
        self.arch['source'].arch_id = 1
        self.arch['all'].arch_id = 2
        for _, architecture in self.arch.items():
            self.session.add(architecture)
            self.session.flush()
            self.session.refresh(architecture)

    def setup_suites(self):
        "setup a hash of Suite objects in self.suite"

        self.suite = {}
        for suite_name in ('lenny', 'squeeze', 'sid'):
            suite = Suite(suite_name = suite_name, version = '-')
            self.suite[suite_name] = suite
            self.session.add(suite)
            self.session.flush()
            self.session.refresh(suite)

    def setUp(self):
        super(PackageTestCase, self).setUp()
        self.setup_architectures()
        self.setup_suites()

    def connect_suite_architectures(self):
        """
        Gonnect all suites and all architectures except for kfreebsd-i386 which
        should not be in lenny.
        """

        for arch_string, architecture in self.arch.items():
            if arch_string != 'kfreebsd-i386':
                architecture.suites = self.suite.values()
            else:
                architecture.suites = [self.suite['squeeze'], self.suite['sid']]

    def test_suite_architecture(self):
        # check the id for architectures source and all
        self.assertEqual(1, self.arch['source'].arch_id)
        self.assertEqual(2, self.arch['all'].arch_id)
        # check the many to many relation between Suite and Architecture
        self.arch['source'].suites.append(self.suite['lenny'])
        self.assertEqual('source', self.suite['lenny'].architectures[0])
        self.arch['source'].suites = []
        self.assertEqual([], self.suite['lenny'].architectures)
        self.connect_suite_architectures()
        self.assertEqual(4, len(self.suite['lenny'].architectures))
        self.assertEqual(3, len(self.arch['i386'].suites))
        # check the function get_suite_architectures()
        architectures = get_suite_architectures('lenny', session = self.session)
        self.assertEqual(4, len(architectures))
        self.assertTrue(self.arch['source'] in architectures)
        self.assertTrue(self.arch['all'] in architectures)
        self.assertTrue(self.arch['kfreebsd-i386'] not in architectures)
        architectures = get_suite_architectures('sid', session = self.session)
        self.assertEqual(5, len(architectures))
        self.assertTrue(self.arch['kfreebsd-i386'] in architectures)
        architectures = get_suite_architectures('lenny', skipsrc = True, session = self.session)
        self.assertEqual(3, len(architectures))
        self.assertTrue(self.arch['source'] not in architectures)
        architectures = get_suite_architectures('lenny', skipall = True, session = self.session)
        self.assertEqual(3, len(architectures))
        self.assertTrue(self.arch['all'] not in architectures)

if __name__ == '__main__':
    unittest.main()
