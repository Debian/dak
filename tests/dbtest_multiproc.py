#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn

from multiprocessing import Pool
from time import sleep
import unittest

def read_number():
    session = DBConn().session()
    result = session.query('foo').from_statement('select 7 as foo').scalar()
    sleep(0.1)
    session.close()
    return result

class MultiProcTestCase(DBDakTestCase):
    """
    This TestCase checks that DBConn works with multiprocessing.
    """

    def save_result(self, result):
        self.result += result

    def test_seven(self):
        '''
        Test apply_async() with a database session.
        '''
        self.result = 0
        pool = Pool()
        pool.apply_async(read_number, (), callback = self.save_result)
        pool.apply_async(read_number, (), callback = self.save_result)
        pool.apply_async(read_number, (), callback = self.save_result)
        pool.apply_async(read_number, (), callback = self.save_result)
        pool.apply_async(read_number, (), callback = self.save_result)
        pool.close()
        pool.join()
        self.assertEqual(5 * 7, self.result)

if __name__ == '__main__':
    unittest.main()
