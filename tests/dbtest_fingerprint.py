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
        query = self.session.query(Fingerprint)
        self.assertEqual(1, query.count())
        self.assertEqual('deadbeefdeadbeef', query.one().fingerprint)

    def tearDown(self):
        self.session.query(Fingerprint).delete()
        super(FingerprintTestCase, self).tearDown()

if __name__ == '__main__':
    unittest.main()
