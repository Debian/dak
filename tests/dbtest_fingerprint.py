#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Fingerprint

import unittest

class FingerprintTestCase(DBDakTestCase):
    def test_mini(self):
        fingerprint = Fingerprint()
        fingerprint.fingerprint = 'deadbeefdeadbeef'
        self.session.add(fingerprint)
        self.session.commit
        fingerprint = self.session.query(Fingerprint).one()
        self.assertEqual('deadbeefdeadbeef', fingerprint.fingerprint)

if __name__ == '__main__':
    unittest.main()
