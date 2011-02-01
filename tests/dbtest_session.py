#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn, Uid

from sqlalchemy.exc import InvalidRequestError

import time
import unittest

class SessionTestCase(DBDakTestCase):
    """
    This TestCase checks the behaviour of SQLAlchemy's session object. It should
    make sure the SQLAlchemy always works as we expect it. And it might help
    dak beginners to get a grasp on how the session works.
    """

    def sleep(self):
        time.sleep(0.001)

    def test_timestamps(self):
        '''
        Test the basic transaction behaviour. The session is not configured for
        autocommit mode and that is why we always have an open transaction that
        ends with either rollback() or commit().
        '''

        # timestamps will always be the same in one transaction
        timestamp01 = self.now()
        self.sleep()
        timestamp02 = self.now()
        self.assertEqual(timestamp01, timestamp02)
        uid = Uid(uid = 'foobar')
        self.session.add(uid)
        self.session.flush()
        self.assertEqual(timestamp01, uid.created)
        # ... but different in multiple transactions
        self.session.rollback()
        timestamp03 = self.now()
        self.assertTrue(timestamp01 < timestamp03)
        uid = Uid(uid = 'foobar')
        self.session.add(uid)
        self.session.flush()
        self.assertTrue(timestamp01 < uid.created)

    def test_crud(self):
        '''
        Test INSERT, UPDATE, DELETE, ROLLBACK, and COMMIT behaviour of the
        session.
        '''

        # test INSERT
        uid = Uid(uid = 'foobar')
        self.assertTrue(uid not in self.session)
        self.session.add(uid)
        self.assertTrue(uid in self.session)
        self.assertTrue(uid in self.session.new)
        self.session.flush()
        self.assertTrue(uid in self.session)
        self.assertTrue(uid not in self.session.new)
        # test UPDATE
        uid.uid = 'foobar2'
        self.assertTrue(uid in self.session.dirty)
        self.session.flush()
        self.assertTrue(uid not in self.session.dirty)
        # test ROLLBACK
        self.session.rollback()
        self.assertTrue(uid not in self.session)
        # test COMMIT
        uid = Uid(uid = 'foobar')
        self.session.add(uid)
        self.assertTrue(uid in self.session.new)
        self.session.commit()
        self.assertTrue(uid in self.session)
        self.assertTrue(uid not in self.session.new)
        # test DELETE
        self.session.delete(uid)
        self.assertTrue(uid in self.session)
        self.assertTrue(uid in self.session.deleted)
        self.session.flush()
        self.assertTrue(uid not in self.session)
        self.assertTrue(uid not in self.session.deleted)

    def test_expunge(self):
        '''
        Test expunge() of objects from session and the object_session()
        function.
        '''

        # test expunge()
        uid = Uid(uid = 'foobar')
        self.session.add(uid)
        self.assertTrue(uid in self.session)
        self.session.expunge(uid)
        self.assertTrue(uid not in self.session)
        # test close()
        self.session.add(uid)
        self.assertTrue(uid in self.session)
        self.session.close()
        self.assertTrue(uid not in self.session)
        # make uid persistent
        self.session.add(uid)
        self.session.commit()
        self.assertTrue(uid in self.session)
        # test rollback() for persistent object
        self.session.rollback()
        self.assertTrue(uid in self.session)
        # test expunge() for persistent object
        self.session.expunge(uid)
        self.assertTrue(uid not in self.session)
        # test close() for persistent object
        self.session.add(uid)
        self.assertTrue(uid in self.session)
        self.session.close()
        self.assertTrue(uid not in self.session)

    def refresh(self):
        '''
        Refreshes self.uid and should raise an exception is self.uid is not
        persistent.
        '''
        self.session.refresh(self.uid)

    def test_refresh(self):
        '''
        Test the refresh() of an object.
        '''

        self.uid = Uid(uid = 'foobar')
        self.assertEqual(None, self.uid.uid_id)
        self.session.add(self.uid)
        self.assertEqual(None, self.uid.uid_id)
        self.session.flush()
        self.assertTrue(self.uid.uid_id is not None)
        self.session.rollback()
        self.assertRaises(InvalidRequestError, self.refresh)

    def test_session(self):
        '''
        Tests the ORMObject.session() method.
        '''

        uid = Uid(uid = 'foobar')
        self.session.add(uid)
        self.assertEqual(self.session, uid.session())

    def test_clone(self):
        '''
        Tests the ORMObject.clone() method.
        '''

        uid1 = Uid(uid = 'foobar')
        # no session yet
        self.assertRaises(RuntimeError, uid1.clone)
        self.session.add(uid1)
        # object not persistent yet
        self.assertRaises(RuntimeError, uid1.clone)
        self.session.commit()
        # test without session parameter
        uid2 = uid1.clone()
        self.assertTrue(uid1 is not uid2)
        self.assertEqual(uid1.uid, uid2.uid)
        self.assertTrue(uid2 not in uid1.session())
        self.assertTrue(uid1 not in uid2.session())
        # test with explicit session parameter
        new_session = DBConn().session()
        uid3 = uid1.clone(session = new_session)
        self.assertEqual(uid1.uid, uid3.uid)
        self.assertTrue(uid3 in new_session)
        # test for ressource leaks with mass cloning
        for _ in xrange(1, 1000):
            uid1.clone()

    def classes_to_clean(self):
        # We need to clean all Uid objects in case some test fails.
        return (Uid,)

if __name__ == '__main__':
    unittest.main()
