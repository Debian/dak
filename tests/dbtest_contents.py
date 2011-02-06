#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn, BinContents

from sqlalchemy.exc import FlushError, IntegrityError
import unittest

class ContentsTestCase(DBDakTestCase):
    """
    This TestCase checks the behaviour of contents generation.
    """

    def test_duplicates1(self):
        '''
        Test the BinContents class for duplication problems.
        '''
        self.setup_binaries()
        contents1 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        self.session.flush()
        # test duplicates
        contents2 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents2)
        self.assertRaises(FlushError, self.session.flush)

    def test_duplicates2(self):
        '''
        Test the BinContents class for more duplication problems.
        '''
        self.setup_binaries()
        contents1 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        contents2 = BinContents(file = 'usr/bin/gruezi', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents2)
        self.session.flush()
        # test duplicates
        contents2.file = 'usr/bin/hello'
        self.assertRaises(IntegrityError, self.session.flush)

    def test_duplicates3(self):
        '''
        Test the BinContents class even more.
        '''
        self.setup_binaries()
        contents1 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['hello_2.2-1_i386'])
        self.session.add(contents1)
        # same file in different binary packages should be okay
        contents2 = BinContents(file = 'usr/bin/hello', \
            binary = self.binary['gnome-hello_2.2-1_i386'])
        self.session.add(contents2)
        self.session.flush()

if __name__ == '__main__':
    unittest.main()
