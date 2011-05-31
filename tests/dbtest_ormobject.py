#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Architecture, Suite
from daklib.dak_exceptions import DBUpdateError

try:
    # python >= 2.6
    import json
except:
    # python <= 2.5
    import simplejson as json

import re
import unittest

class ORMObjectTestCase(DBDakTestCase):
    """
    The ORMObjectTestCase tests the behaviour of the ORMObject.
    """

    def test_strings(self):
        'tests json(), __repr__(), and __str__()'
        architecture = Architecture(arch_string = 'i386')
        # test json()
        data = json.loads(architecture.json())
        self.assertEqual('i386', data['arch_string'])
        # test repr()
        self.assertEqual('<Architecture i386>', repr(architecture))
        # test str()
        self.assertTrue(re.match('<Architecture {.*}>', str(architecture)))
        self.assertTrue(re.search('"arch_string": "i386"', str(architecture)))
        sid = Suite(suite_name = 'sid')
        squeeze = Suite(suite_name = 'squeeze')
        architecture.suites = [sid, squeeze]
        self.assertTrue(re.search('"suites_count": 2', str(architecture)))

    def test_validation(self):
        suite = Suite()
        self.session.add(suite)
        self.assertRaises(DBUpdateError, self.session.flush)

if __name__ == '__main__':
    unittest.main()
