#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn, Uid

import time
import unittest

class TimestampTestCase(DBDakTestCase):
    """
    TimestampTestCase checks that the timestamps created and modified are
    working correctly.

    TODO: Should we check all tables?
    """

    def sleep(self):
        time.sleep(0.001)

    def test_timestamps(self):
        timestamp01 = self.now()
        self.session.rollback()
        self.sleep()
        uid = Uid(uid = 'ftp-master@debian.org')
        self.session.add(uid)
        self.session.commit()
        created01 = uid.created
        modified01 = uid.modified
        self.sleep()
        timestamp02 = self.now()
        self.session.rollback()
        self.assertTrue(timestamp01 < created01)
        self.assertTrue(timestamp01 < modified01)
        self.assertTrue(created01 < timestamp02)
        self.assertTrue(modified01 < timestamp02)
        self.sleep()
        uid.name = 'ftp team'
        self.session.commit()
        created02 = uid.created
        modified02 = uid.modified
        self.assertEqual(created01, created02)
        self.assertTrue(modified01 < modified02)
        self.sleep()
        self.session.rollback()
        timestamp03 = self.now()
        self.assertTrue(modified02 < timestamp03)

    def classes_to_clean(self):
        return (Uid,)

if __name__ == '__main__':
    unittest.main()
