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
    def setUp(self):
        super(DebVersionTestCase, self).setUp()
        self.version_table = Table('version', self.metadata, \
            Column('id', Integer, primary_key = True), \
            Column('version', DebVersion), \
            )
        self.version_table.create(checkfirst = True)
        mapper(Version, self.version_table)

    def test_debversion(self):
        v1 = Version('0.5')
        self.session.add(v1)
        v2 = Version('1.0')
        self.session.add(v2)
        #self.session.commit()
        q = self.session.query(Version)
        self.assertEqual(2, q.count())
        self.assertEqual(2, q.filter(Version.version > '0.5~').count())
        self.assertEqual(1, q.filter(Version.version > '0.5').count())
        self.assertEqual(0, q.filter(Version.version > '1.0').count())
        for v in self.session.query(Version.version):
            print v

    def tearDown(self):
        self.session.close()
        self.version_table.drop()
        super(DebVersionTestCase, self).tearDown()

if __name__ == '__main__':
    unittest.main()
