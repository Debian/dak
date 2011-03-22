#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn, MetadataKey, BinaryMetadata, SourceMetadata

import unittest

class MetadataTestCase(DBDakTestCase):
    """
    This TestCase checks the metadata handling.
    """

    def test_mappers(self):
        '''
        Tests the mapper configuration.
        '''
        self.setup_binaries()
        # MetadataKey
        depends = MetadataKey(key = 'Depends')
        self.session.add(depends)
        self.session.flush()
        self.assertTrue(depends.key_id is not None)
        # BinaryMetadata
        hello_dep = BinaryMetadata(binary = self.binary['hello_2.2-1_i386'],
            key = depends, value = 'foobar (>= 1.0)')
        self.session.add(hello_dep)
        self.session.flush()
        self.assertEqual('hello', hello_dep.binary.package)
        self.assertEqual('Depends', hello_dep.key.key)
        self.assertEqual('foobar (>= 1.0)', hello_dep.value)
        # SourceMetadata
        build_dep = MetadataKey(key = 'Build-Depends')
        hello_bd = SourceMetadata(source = self.binary['hello_2.2-1_i386'].source,
            key = build_dep, value = 'foobar-dev')
        self.session.add(hello_bd)
        self.session.flush()
        self.assertEqual('hello', hello_bd.source.source)
        self.assertEqual('Build-Depends', hello_bd.key.key)
        self.assertEqual('foobar-dev', hello_bd.value)

if __name__ == '__main__':
    unittest.main()
