#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Architecture
from daklib.dak_exceptions import DBUpdateError

import unittest

class ValidatorTestCase(DBDakTestCase):
    """
    The ValidatorTestCase tests the validation mechanism.
    """

    def must_fail(self):
        ''''
        This function must fail with DBUpdateError because arch_string is not
        set. It rolls back the transaction before re-raising the exception.
        '''
        try:
            architecture = Architecture()
            self.session.add(architecture)
            self.session.flush()
        except:
            self.session.rollback()
            raise

    def test_validation(self):
        'tests validate()'
        self.assertRaises(DBUpdateError, self.must_fail)
        # should not fail
        architecture = Architecture('i386')
        self.session.add(architecture)
        self.session.flush()

if __name__ == '__main__':
    unittest.main()
