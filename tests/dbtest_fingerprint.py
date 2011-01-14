#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Fingerprint, Uid

import unittest

class FingerprintTestCase(DBDakTestCase):
    """
    The FingerprintTestCase tests the relation between Fingerprint and Uid
    objects.
    1. It creates a fresh Fingerprint object.
    2. It assigns a fresh Uid object to the Fingerprint object.
    3. It fetches the Uid object from the database.
    4. It checks that the original fingerprint is assigned to the freshly
       fetched Uid object.
    """

    def test_mini(self):
        fingerprint = Fingerprint(fingerprint = 'deadbeefdeadbeef')
        self.session.add(fingerprint)
        query = self.session.query(Fingerprint)
        self.assertEqual(1, query.count())
        self.assertEqual('deadbeefdeadbeef', query.one().fingerprint)
        fingerprint.uid = Uid(uid = 'ftp-master@debian.org', name = 'ftpteam')
        uid = self.session.query(Uid).one()
        self.assertEqual('ftp-master@debian.org', uid.uid)
        self.assertEqual('ftpteam', uid.name)
        self.assertEqual(1, len(uid.fingerprint))
        self.assertEqual('deadbeefdeadbeef', uid.fingerprint[0].fingerprint)

if __name__ == '__main__':
    unittest.main()
