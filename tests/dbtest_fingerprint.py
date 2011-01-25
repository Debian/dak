#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Fingerprint, Uid
from daklib.dak_exceptions import DBUpdateError

from sqlalchemy.exc import IntegrityError
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

    Furthermore it checks various constraints like not null and unique.

    TODO: the not null constraints should be enforced by the constructor in
    dbconn.py. Should we check the exact format of the fingerprint?
    """

    def test_relation(self):
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

    def fingerprint_no_fingerprint(self):
        self.session.add(Fingerprint())
        self.session.flush()

    def fingerprint_duplicate_fingerprint(self):
        self.session.add(Fingerprint(fingerprint = 'affe0815'))
        self.session.add(Fingerprint(fingerprint = 'affe0815'))
        self.session.flush()

    def uid_no_uid(self):
        self.session.add(Uid(name = 'foobar'))
        self.session.flush()

    def uid_duplicate_uid(self):
        self.session.add(Uid(uid = 'duplicate'))
        self.session.add(Uid(uid = 'duplicate'))
        self.session.flush()

    def test_exceptions(self):
        self.assertRaises(DBUpdateError, self.fingerprint_no_fingerprint)
        self.session.rollback()
        self.assertRaises(IntegrityError, self.fingerprint_duplicate_fingerprint)
        self.session.rollback()
        self.assertRaises(DBUpdateError, self.uid_no_uid)
        self.session.rollback()
        self.assertRaises(IntegrityError, self.uid_duplicate_uid)
        self.session.rollback()

if __name__ == '__main__':
    unittest.main()
