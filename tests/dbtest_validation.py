#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Architecture
from daklib.dak_exceptions import DBUpdateError

import unittest

class ValidatorTestCase(DBDakTestCase):
    """
    The ValidatorTestCase tests the validation mechanism.
    """

    def test_validation(self):
        'tests validate()'

        # before_insert validation should fail
        architecture = Architecture()
        self.session.add(architecture)
        self.assertRaises(DBUpdateError, self.session.flush)
        self.session.rollback()
        # should not fail
        architecture = Architecture('i386')
        self.session.add(architecture)
        self.session.flush()
        # before_update validation should fail
        architecture.arch_string = None
        self.assertRaises(DBUpdateError, self.session.flush)
        self.session.rollback()

if __name__ == '__main__':
    unittest.main()
