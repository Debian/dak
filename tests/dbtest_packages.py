#! /usr/bin/env python3

from db_test import DBDakTestCase
from base_test import fixture
import os
from os.path import join

from daklib.dbconn import *
from daklib.queue import get_suite_version_by_source, get_suite_version_by_package

from sqlalchemy.orm.exc import MultipleResultsFound
import unittest

DAKBASE = os.environ['DAKBASE']


class Pkg():

    'fake package class used for testing'

    def __init__(self):
        self.dsc = {}
        self.files = {}
        self.changes = {}


class Upload():

    'fake Upload class used for testing'

    def __init__(self, pkg):
        self.pkg = pkg


class PackageTestCase(DBDakTestCase):

    """
    PackageTestCase checks the handling of source and binary packages in dak's
    database.
    """

    def setUp(self):
        super(PackageTestCase, self).setUp()
        self.setup_binaries()
        # flush to make sure that the setup is correct
        self.session.flush()

    def test_suite_architecture(self):
        # check the id for architectures source and all
        self.assertEqual(1, self.arch['source'].arch_id)
        self.assertEqual(2, self.arch['all'].arch_id)
        # check the many to many relation between Suite and Architecture
        self.assertEqual('all', self.suite['lenny'].get_architectures()[0])
        self.assertEqual(4, len(self.suite['lenny'].architectures))
        self.assertEqual(3, len(self.arch['i386'].suites))
        # check the function get_suite_architectures()
        architectures = get_suite_architectures('lenny', session=self.session)
        self.assertEqual(4, len(architectures))
        self.assertTrue(self.arch['source'] in architectures)
        self.assertTrue(self.arch['all'] in architectures)
        self.assertTrue(self.arch['kfreebsd-i386'] not in architectures)
        architectures = get_suite_architectures('sid', session=self.session)
        self.assertEqual(5, len(architectures))
        self.assertTrue(self.arch['kfreebsd-i386'] in architectures)
        architectures = get_suite_architectures(
            'lenny', skipsrc=True, session=self.session)
        self.assertEqual(3, len(architectures))
        self.assertTrue(self.arch['source'] not in architectures)
        architectures = get_suite_architectures(
            'lenny', skipall=True, session=self.session)
        self.assertEqual(3, len(architectures))
        self.assertTrue(self.arch['all'] not in architectures)
        # check overrides
        self.assertEqual(0, self.suite['lenny'].overrides.count())

    def test_poolfiles(self):
        main = self.comp['main']
        contrib = self.comp['contrib']
        poolfile = self.session.query(PoolFile).filter(
            PoolFile.filename.like('%/hello/hello%')). \
            order_by(PoolFile.filename)[0]
        self.assertEqual('h/hello/hello_2.2-1.dsc', poolfile.filename)
        self.assertEqual(main, poolfile.component)
        # test get()
        self.assertEqual(poolfile,
                         self.session.query(PoolFile).get(poolfile.file_id))
        self.assertEqual(None, self.session.query(PoolFile).get(-1))
        # test fullpath
        self.assertEqual(join(DAKBASE, 'ftp/pool/main/s/sl/sl_3.03-16.dsc'),
                         self.file['sl_3.03-16.dsc'].fullpath)

    def test_maintainers(self):
        '''
        tests relation between Maintainer and DBSource

        TODO: add relations to changes_pending_source
        '''

        maintainer = self.maintainer['maintainer']
        self.assertEqual(maintainer,
                         self.session.query(Maintainer).get(maintainer.maintainer_id))
        uploader = self.maintainer['uploader']
        self.assertEqual(uploader,
                         self.session.query(Maintainer).get(uploader.maintainer_id))
        lazyguy = self.maintainer['lazyguy']
        self.assertEqual(lazyguy,
                         self.session.query(Maintainer).get(lazyguy.maintainer_id))
        self.assertEqual(4, len(maintainer.maintains_sources))
        self.assertTrue(
            self.source['hello_2.2-2'] in maintainer.maintains_sources)
        self.assertEqual(maintainer.changed_sources, [])
        self.assertEqual(uploader.maintains_sources, [])
        self.assertEqual(4, len(uploader.changed_sources))
        self.assertTrue(self.source['sl_3.03-16'] in uploader.changed_sources)
        self.assertEqual(lazyguy.maintains_sources, [])
        self.assertEqual(lazyguy.changed_sources, [])

    def get_source_in_suite_fail(self):
        '''
        This function throws the MultipleResultsFound exception because
        get_source_in_suite is broken.

        TODO: fix get_source_in_suite
        '''

        return get_source_in_suite('hello', 'sid', self.session)

    def test_sources(self):
        'test relation between DBSource and PoolFile or Suite'

        # test PoolFile
        self.assertEqual(
            self.file['hello_2.2-2.dsc'], self.source['hello_2.2-2'].poolfile)
        self.assertEqual(
            self.file['hello_2.2-2.dsc'].component, self.comp['main'])
        self.assertEqual(
            self.file['gnome-hello_3.0-1.dsc'].component, self.comp['contrib'])
        # test Suite
        squeeze = self.session.query(Suite). \
            filter(Suite.sources.contains(self.source['sl_3.03-16'])). \
            order_by(Suite.suite_name)[1]
        self.assertEqual(self.suite['squeeze'], squeeze)
        self.assertEqual(1, squeeze.sources.count())
        self.assertEqual(self.source['sl_3.03-16'], squeeze.sources[0])
        sl = self.session.query(DBSource). \
            filter(DBSource.suites.contains(self.suite['squeeze'])).one()
        self.assertEqual(self.source['sl_3.03-16'], sl)
        self.assertEqual(2, len(sl.suites))
        self.assertTrue(self.suite['sid'] in sl.suites)
        # test get_source_in_suite()
        self.assertRaises(MultipleResultsFound, self.get_source_in_suite_fail)
        self.assertEqual(None,
                         get_source_in_suite('hello', 'squeeze', self.session))
        self.assertEqual(self.source['sl_3.03-16'],
                         get_source_in_suite('sl', 'sid', self.session))
        # test get_suites_source_in()
        self.assertEqual([self.suite['sid']],
                         get_suites_source_in('hello', self.session))
        self.assertEqual(2, len(get_suites_source_in('sl', self.session)))
        self.assertTrue(self.suite['squeeze'] in
                        get_suites_source_in('sl', self.session))

    def test_get_suite_version_by_source(self):
        'test function get_suite_version_by_source()'

        result = get_suite_version_by_source('hello', self.session)
        self.assertEqual(2, len(result))
        self.assertTrue(('sid', '2.2-1') in result)
        self.assertTrue(('sid', '2.2-2') in result)
        result = get_suite_version_by_source('sl', self.session)
        self.assertEqual(2, len(result))
        self.assertTrue(('squeeze', '3.03-16') in result)
        self.assertTrue(('sid', '3.03-16') in result)

    def test_binaries(self):
        '''
        tests class DBBinary; TODO: test relation with Architecture, Maintainer,
        PoolFile, and Fingerprint
        '''

        # test Suite relation
        self.assertEqual(3, self.suite['sid'].binaries.count())
        self.assertTrue(self.binary['hello_2.2-1_i386'] in
                        self.suite['sid'].binaries.all())
        self.assertEqual(0, self.suite['lenny'].binaries.count())
        # test DBSource relation
        self.assertEqual(3, len(self.source['hello_2.2-1'].binaries))
        self.assertTrue(self.binary['hello_2.2-1_i386'] in
                        self.source['hello_2.2-1'].binaries)
        self.assertEqual(0, len(self.source['hello_2.2-2'].binaries))
        # test get_suites_binary_in()
        self.assertEqual(2, len(get_suites_binary_in('hello', self.session)))
        self.assertTrue(self.suite['sid'] in
                        get_suites_binary_in('hello', self.session))
        self.assertEqual(
            2, len(get_suites_binary_in('gnome-hello', self.session)))
        self.assertTrue(self.suite['squeeze'] in
                        get_suites_binary_in('gnome-hello', self.session))
        self.assertEqual(0, len(get_suites_binary_in('sl', self.session)))

    def test_get_suite_version_by_package(self):
        'test function get_suite_version_by_package()'

        result = get_suite_version_by_package('hello', 'i386', self.session)
        self.assertEqual(2, len(result))
        self.assertTrue(('sid', '2.2-1') in result)
        result = get_suite_version_by_package('hello', 'amd64', self.session)
        self.assertEqual(0, len(result))
        result = get_suite_version_by_package(
            'python-hello', 'i386', self.session)
        self.assertEqual([('squeeze', '2.2-1')], result)
        result = get_suite_version_by_package(
            'python-hello', 'amd64', self.session)
        self.assertEqual([('squeeze', '2.2-1')], result)

    def test_components(self):
        'test class Component'

        self.assertEqual(0, self.comp['main'].overrides.count())

    def test_get_component_by_package_suite(self):
        'test get_component_by_package_suite()'

        result = get_component_by_package_suite('hello', ['sid'],
                                                session=self.session)
        self.assertEqual('main', result)
        result = get_component_by_package_suite('hello', ['hamm'],
                                                session=self.session)
        self.assertEqual(None, result)
        result = get_component_by_package_suite('foobar', ['sid'],
                                                session=self.session)
        self.assertEqual(None, result)
        # test that the newest version is returned
        result = get_component_by_package_suite('gnome-hello', ['squeeze'],
                                                session=self.session)
        self.assertEqual('main', result)
        result = get_component_by_package_suite('gnome-hello', ['sid'],
                                                session=self.session)
        self.assertEqual('contrib', result)
        # test arch_list
        result = get_component_by_package_suite('hello', ['sid'],
                                                arch_list=['i386'], session=self.session)
        self.assertEqual('main', result)
        result = get_component_by_package_suite('hello', ['sid'],
                                                arch_list=['amd64'], session=self.session)
        self.assertEqual(None, result)


if __name__ == '__main__':
    unittest.main()
