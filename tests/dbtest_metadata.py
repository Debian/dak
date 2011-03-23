#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import DBConn, MetadataKey, BinaryMetadata, SourceMetadata

import unittest

class MetadataTestCase(DBDakTestCase):
    """
    This TestCase checks the metadata handling.
    """

    def setup_metadata(self):
        '''
        Setup the metadata objects.
        '''
        self.setup_binaries()
        self.depends = MetadataKey('Depends')
        self.session.add(self.depends)
        self.session.flush()
        self.bin_hello = self.binary['hello_2.2-1_i386']
        self.src_hello = self.bin_hello.source
        self.session.add(self.bin_hello)
        self.session.add(self.src_hello)
        self.hello_dep = BinaryMetadata(self.depends, 'foobar (>= 1.0)', self.bin_hello)
        self.session.add(self.hello_dep)
        self.recommends = MetadataKey('Recommends')
        self.bin_hello.key[self.recommends] = BinaryMetadata(self.recommends, 'goodbye')
        self.build_dep = MetadataKey('Build-Depends')
        self.hello_bd = SourceMetadata(self.build_dep, 'foobar-dev', self.src_hello)
        self.session.add(self.hello_bd)
        self.homepage = MetadataKey('Homepage')
        self.src_hello.key[self.homepage] = SourceMetadata(self.homepage, 'http://debian.org')
        self.session.flush()

    def test_mappers(self):
        '''
        Tests the mapper configuration.
        '''
        self.setup_metadata()
        # MetadataKey
        self.assertTrue(self.depends.key_id is not None)
        # BinaryMetadata
        self.assertEqual('hello', self.hello_dep.binary.package)
        self.assertEqual('Depends', self.hello_dep.key.key)
        self.assertEqual('foobar (>= 1.0)', self.hello_dep.value)
        # SourceMetadata
        self.assertEqual('hello', self.hello_bd.source.source)
        self.assertEqual('Build-Depends', self.hello_bd.key.key)
        self.assertEqual('foobar-dev', self.hello_bd.value)
        # DBBinary relation
        self.assertEqual(self.hello_dep, self.bin_hello.key[self.depends])
        self.assertEqual('goodbye', self.bin_hello.key[self.recommends].value)
        # DBSource relation
        self.assertEqual(self.hello_bd, self.src_hello.key[self.build_dep])
        self.assertEqual('http://debian.org', self.src_hello.key[self.homepage].value)

    def test_association_proxy(self):
        '''
        Test the association proxies 'metadata' in DBBinary and DBSource.
        '''
        self.setup_metadata()
        # DBBinary association proxy
        essential = MetadataKey('Essential')
        self.bin_hello.metadata[essential] = 'yes'
        self.session.flush()
        self.assertEqual('yes', self.bin_hello.metadata[essential])
        self.assertEqual('foobar (>= 1.0)', self.bin_hello.metadata[self.depends])
        self.assertTrue(self.recommends in self.bin_hello.metadata)
        # DBSource association proxy
        std_version = MetadataKey('Standards-Version')
        self.src_hello.metadata[std_version] = '3.9.1'
        self.session.flush()
        self.assertEqual('3.9.1', self.src_hello.metadata[std_version])
        self.assertEqual('http://debian.org', self.src_hello.metadata[self.homepage])
        self.assertTrue(self.depends not in self.src_hello.metadata)

    def test_delete(self):
        '''
        Tests the delete / cascading behaviour.
        '''
        self.setup_metadata()
        self.session.delete(self.bin_hello)
        # Remove associated binaries because we have no cascading rule for
        # them.
        for binary in self.src_hello.binaries:
            self.session.delete(binary)
        self.session.delete(self.src_hello)
        self.session.flush()

if __name__ == '__main__':
    unittest.main()
