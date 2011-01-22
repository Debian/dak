#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn, DebVersion

from sqlalchemy import Table, Column, Integer, func
from sqlalchemy.orm import mapper
import unittest

class Version(object):
    def __init__(self, version):
        self.version = version

    def __repr__(self):
        return "<Version('%s')>" % self.version

class DebVersionTestCase(DBDakTestCase):
    """
    The DebVersionTestCase tests both comparison (<=, ==, >, !=), the in_()
    method and aggregate functions (min, max) for the DebVersion type. To
    simplify the test it creates a separate table 'version' which is not used
    by dak itself.
    """

    def setUp(self):
        super(DebVersionTestCase, self).setUp()
        self.version_table = Table('version', self.metadata, \
            Column('id', Integer, primary_key = True), \
            Column('version', DebVersion), \
            )
        self.version_table.create(checkfirst = True)
        mapper(Version, self.version_table)

    def test_debversion(self):
        v = Version('0.5~')
        self.session.add(v)
        v = Version('0.5')
        self.session.add(v)
        v = Version('1.0')
        self.session.add(v)
        q = self.session.query(Version)
        self.assertEqual(3, q.count())
        self.assertEqual(2, q.filter(Version.version <= '0.5').count())
        self.assertEqual(1, q.filter(Version.version == '0.5').count())
        self.assertEqual(2, q.filter(Version.version > '0.5~').count())
        self.assertEqual(1, q.filter(Version.version > '0.5').count())
        self.assertEqual(0, q.filter(Version.version > '1.0').count())
        self.assertEqual(2, q.filter(Version.version != '1.0').count())
        self.assertEqual(2, q.filter(Version.version.in_(['0.5~', '1.0'])).count())
        q = self.session.query(func.min(Version.version))
        self.assertEqual('0.5~', q.scalar())
        q = self.session.query(func.max(Version.version))
        self.assertEqual('1.0', q.scalar())

    def tearDown(self):
        self.session.rollback()
        self.version_table.drop()
        super(DebVersionTestCase, self).tearDown()

if __name__ == '__main__':
    unittest.main()
