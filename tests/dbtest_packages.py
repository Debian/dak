#!/usr/bin/env python

from db_test import DBDakTestCase
from base_test import fixture

from daklib.dbconn import *
from daklib.queue_install import package_to_suite
from daklib.queue import get_newest_source, get_suite_version_by_source, \
    get_source_by_package_and_suite, get_suite_version_by_package

from sqlalchemy.orm.exc import MultipleResultsFound
import unittest

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
        self.assertEqual('source', self.suite['lenny'].architectures[0])
        self.assertEqual(4, len(self.suite['lenny'].architectures))
        self.assertEqual(3, len(self.arch['i386'].suites))
        # check the function get_suite_architectures()
        architectures = get_suite_architectures('lenny', session = self.session)
        self.assertEqual(4, len(architectures))
        self.assertTrue(self.arch['source'] in architectures)
        self.assertTrue(self.arch['all'] in architectures)
        self.assertTrue(self.arch['kfreebsd-i386'] not in architectures)
        architectures = get_suite_architectures('sid', session = self.session)
        self.assertEqual(5, len(architectures))
        self.assertTrue(self.arch['kfreebsd-i386'] in architectures)
        architectures = get_suite_architectures('lenny', skipsrc = True, session = self.session)
        self.assertEqual(3, len(architectures))
        self.assertTrue(self.arch['source'] not in architectures)
        architectures = get_suite_architectures('lenny', skipall = True, session = self.session)
        self.assertEqual(3, len(architectures))
        self.assertTrue(self.arch['all'] not in architectures)
        # check overrides
        self.assertEqual(0, self.suite['lenny'].overrides.count())

    def test_poolfiles(self):
        '''
        Test the relation of the classes PoolFile and Location.

        The code needs some explaination. The property Location.files is not a
        list as in other relations because such a list would become rather
        huge. It is a query object that can be queried, filtered, and iterated
        as usual.  But list like methods like append() and remove() are
        supported as well which allows code like:

        somelocation.files.append(somefile)
        '''

        main = self.loc['main']
        contrib = self.loc['contrib']
        self.assertEqual(fixture('ftp/pool/'), main.path)
        count = len(self.file.keys()) - 2
        self.assertEqual(count, main.files.count())
        self.assertEqual(2, contrib.files.count())
        poolfile = main.files. \
                filter(PoolFile.filename.like('%/hello/hello%')). \
                order_by(PoolFile.filename)[0]
        self.assertEqual('main/h/hello/hello_2.2-1.dsc', poolfile.filename)
        self.assertEqual(main, poolfile.location)
        # test get()
        self.assertEqual(poolfile, \
                self.session.query(PoolFile).get(poolfile.file_id))
        self.assertEqual(None, self.session.query(PoolFile).get(-1))
        # test remove() and append()
        main.files.remove(self.file['sl_3.03-16.dsc'])
        contrib.files.append(self.file['sl_3.03-16.dsc'])
        self.assertEqual(count - 1, main.files.count())
        self.assertEqual(3, contrib.files.count())
        # test fullpath
        self.assertEqual(fixture('ftp/pool/main/s/sl/sl_3.03-16.dsc'), \
            self.file['sl_3.03-16.dsc'].fullpath)
        # test check_poolfile()
        self.assertEqual((True, self.file['sl_3.03-16.dsc']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 0, '', \
                contrib.location_id, self.session))
        # test string value of 2nd argument
        self.assertEqual((True, self.file['sl_3.03-16.dsc']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', '0', '', \
                contrib.location_id, self.session))
        self.assertEqual((False, None), \
            check_poolfile('foobar', 0, '', contrib.location_id, self.session))
        self.assertEqual((False, self.file['sl_3.03-16.dsc']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 42, '', \
                contrib.location_id, self.session))
        self.assertEqual((False, self.file['sl_3.03-16.dsc']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 0, 'deadbeef', \
                contrib.location_id, self.session))
        # test get_poolfile_like_name()
        self.assertEqual([self.file['sl_3.03-16.dsc']], \
            get_poolfile_like_name('sl_3.03-16.dsc', self.session))
        self.assertEqual([], get_poolfile_like_name('foobar', self.session))

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
        self.assertTrue(self.source['hello_2.2-2'] in maintainer.maintains_sources)
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
        self.assertEqual(self.file['hello_2.2-2.dsc'], self.source['hello_2.2-2'].poolfile)
        self.assertEqual(self.source['hello_2.2-2'], self.file['hello_2.2-2.dsc'].source)
        self.assertEqual(None, self.file['python2.6_2.6.6-8.dsc'].source)
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
        self.assertEqual(None, \
            get_source_in_suite('hello', 'squeeze', self.session))
        self.assertEqual(self.source['sl_3.03-16'], \
            get_source_in_suite('sl', 'sid', self.session))
        # test get_suites_source_in()
        self.assertEqual([self.suite['sid']], \
            get_suites_source_in('hello', self.session))
        self.assertEqual(2, len(get_suites_source_in('sl', self.session)))
        self.assertTrue(self.suite['squeeze'] in \
            get_suites_source_in('sl', self.session))

    def test_add_dsc_to_db(self):
        'tests function add_dsc_to_db()'

        pkg = Pkg()
        pkg.dsc['source'] = 'hello'
        pkg.dsc['version'] = '2.2-3'
        pkg.dsc['maintainer'] = self.maintainer['maintainer'].name
        pkg.changes['changed-by'] = self.maintainer['uploader'].name
        pkg.changes['fingerprint'] = 'deadbeef'
        pkg.changes['distribution'] = { 'sid': '' }
        pkg.files['hello_2.2-3.dsc'] = { \
            'component': 'main',
            'location id': self.loc['main'].location_id,
            'files id': self.file['hello_2.2-3.dsc'].file_id }
        pkg.dsc_files = {}
        upload = Upload(pkg)
        (source, dsc_component, dsc_location_id, pfs) = \
            add_dsc_to_db(upload, 'hello_2.2-3.dsc', self.session)
        self.assertEqual('hello', source.source)
        self.assertEqual('2.2-3', source.version)
        self.assertEqual('sid', source.suites[0].suite_name)
        self.assertEqual('main', dsc_component)
        self.assertEqual(self.loc['main'].location_id, dsc_location_id)
        self.assertEqual([], pfs)

    def test_source_exists(self):
        'test function source_exists()'

        hello = self.source['hello_2.2-2']
        self.assertTrue(source_exists(hello.source, hello.version, \
            suites = ['sid'], session = self.session))
        # binNMU
        self.assertTrue(source_exists(hello.source, hello.version + '+b7', \
            suites = ['sid'], session = self.session))
        self.assertTrue(not source_exists(hello.source, hello.version, \
            suites = ['lenny', 'squeeze'], session = self.session))
        self.assertTrue(not source_exists(hello.source, hello.version, \
            suites = ['lenny', 'sid'], session = self.session))
        self.assertTrue(not source_exists(hello.source, hello.version, \
            suites = ['sid', 'lenny'], session = self.session))
        self.assertTrue(not source_exists(hello.source, '0815', \
            suites = ['sid'], session = self.session))
        # 'any' suite
        self.assertTrue(source_exists(hello.source, hello.version, \
            session = self.session))

    def test_package_to_suite(self):
        'test function package_to_suite()'

        pkg = Pkg()
        pkg.changes = { 'distribution': {} }
        upload = Upload(pkg)
        self.assertTrue(not package_to_suite(upload, 'sid', self.session))
        pkg.changes['distribution'] = { 'sid': '' }
        pkg.changes['architecture'] = { 'source': '' }
        self.assertTrue(package_to_suite(upload, 'sid', self.session))
        pkg.changes['architecture'] = {}
        pkg.changes['source'] = self.source['hello_2.2-2'].source
        pkg.changes['version'] = self.source['hello_2.2-2'].version
        self.assertTrue(not package_to_suite(upload, 'sid', self.session))
        pkg.changes['version'] = '42'
        self.assertTrue(package_to_suite(upload, 'sid', self.session))
        pkg.changes['source'] = 'foobar'
        pkg.changes['version'] = self.source['hello_2.2-2'].version
        self.assertTrue(package_to_suite(upload, 'sid', self.session))
        pkg.changes['distribution'] = { 'lenny': '' }
        self.assertTrue(package_to_suite(upload, 'lenny', self.session))

    def test_get_newest_source(self):
        'test function get_newest_source()'

        import daklib.queue
        daklib.queue.dm_suites = ['sid']
        self.assertEqual(self.source['hello_2.2-2'], get_newest_source('hello', self.session))
        self.assertEqual(None, get_newest_source('foobar', self.session))

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
        self.assertTrue(self.binary['hello_2.2-1_i386'] in \
            self.suite['sid'].binaries.all())
        self.assertEqual(0, self.suite['lenny'].binaries.count())
        # test DBSource relation
        self.assertEqual(3, len(self.source['hello_2.2-1'].binaries))
        self.assertTrue(self.binary['hello_2.2-1_i386'] in \
            self.source['hello_2.2-1'].binaries)
        self.assertEqual(0, len(self.source['hello_2.2-2'].binaries))
        # test get_suites_binary_in()
        self.assertEqual(2, len(get_suites_binary_in('hello', self.session)))
        self.assertTrue(self.suite['sid'] in \
            get_suites_binary_in('hello', self.session))
        self.assertEqual(2, len(get_suites_binary_in('gnome-hello', self.session)))
        self.assertTrue(self.suite['squeeze'] in \
            get_suites_binary_in('gnome-hello', self.session))
        self.assertEqual(0, len(get_suites_binary_in('sl', self.session)))

    def test_add_deb_to_db(self):
        'tests function add_deb_to_db()'

        pkg = Pkg()
        pkg.changes['fingerprint'] = 'deadbeef'
        pkg.changes['distribution'] = { 'sid': '' }
        pkg.files['hello_2.2-2_i386.deb'] = { \
            'package': 'hello',
            'version': '2.2-2',
            'maintainer': self.maintainer['maintainer'].name,
            'architecture': 'i386',
            'dbtype': 'deb',
            'pool name': 'main/h/hello/',
            'location id': self.loc['main'].location_id,
            'source package': 'hello',
            'source version': '2.2-2',
            'size': 0,
            'md5sum': 'deadbeef',
            'sha1sum': 'deadbeef',
            'sha256sum': 'deadbeef'}
        upload = Upload(pkg)
        bin, poolfile = add_deb_to_db(upload, 'hello_2.2-2_i386.deb', self.session)
        self.session.refresh(poolfile)
        self.session.refresh(poolfile.binary)
        self.assertEqual('main/h/hello/hello_2.2-2_i386.deb', poolfile.filename)
        self.assertEqual('hello', poolfile.binary.package)
        self.assertEqual('2.2-2', poolfile.binary.version)
        self.assertEqual(['sid'], poolfile.binary.suites)
        self.assertEqual('Mr. Maintainer', poolfile.binary.maintainer.name)
        self.assertEqual('i386', poolfile.binary.architecture.arch_string)
        self.assertEqual('deb', poolfile.binary.binarytype)
        self.assertEqual(self.loc['main'], poolfile.location)
        self.assertEqual(self.source['hello_2.2-2'], poolfile.binary.source)
        self.assertEqual(0, poolfile.filesize)
        self.assertEqual('deadbeef', poolfile.md5sum)
        self.assertEqual('deadbeef', poolfile.sha1sum)
        self.assertEqual('deadbeef', poolfile.sha256sum)

    def test_get_source_by_package_and_suite(self):
        'test get_source_by_package_and_suite()'

        query = get_source_by_package_and_suite('hello', 'sid', self.session)
        self.assertEqual(self.source['hello_2.2-1'], query.one())
        query = get_source_by_package_and_suite('gnome-hello', 'squeeze', self.session)
        self.assertEqual(self.source['hello_2.2-1'], query.one())
        query = get_source_by_package_and_suite('hello', 'hamm', self.session)
        self.assertEqual(0, query.count())
        query = get_source_by_package_and_suite('foobar', 'squeeze', self.session)
        self.assertEqual(0, query.count())

    def test_get_suite_version_by_package(self):
        'test function get_suite_version_by_package()'

        result = get_suite_version_by_package('hello', 'i386', self.session)
        self.assertEqual(2, len(result))
        self.assertTrue(('sid', '2.2-1') in result)
        result = get_suite_version_by_package('hello', 'amd64', self.session)
        self.assertEqual(0, len(result))
        result = get_suite_version_by_package('python-hello', 'i386', self.session)
        self.assertEqual([('squeeze', '2.2-1')], result)
        result = get_suite_version_by_package('python-hello', 'amd64', self.session)
        self.assertEqual([('squeeze', '2.2-1')], result)

    def test_components(self):
        'test class Component'

        self.assertEqual([self.loc['main']], self.comp['main'].location)
        self.assertEqual([self.loc['contrib']], self.comp['contrib'].location)
        self.assertEqual(0, self.comp['main'].overrides.count())

    def test_get_component_by_package_suite(self):
        'test get_component_by_package_suite()'

        result = get_component_by_package_suite('hello', ['sid'], \
            session = self.session)
        self.assertEqual('main', result)
        result = get_component_by_package_suite('hello', ['hamm'], \
            session = self.session)
        self.assertEqual(None, result)
        result = get_component_by_package_suite('foobar', ['sid'], \
            session = self.session)
        self.assertEqual(None, result)
        # test that the newest version is returned
        result = get_component_by_package_suite('gnome-hello', ['squeeze'], \
            session = self.session)
        self.assertEqual('main', result)
        result = get_component_by_package_suite('gnome-hello', ['sid'], \
            session = self.session)
        self.assertEqual('contrib', result)
        # test arch_list
        result = get_component_by_package_suite('hello', ['sid'], \
            arch_list = ['i386'], session = self.session)
        self.assertEqual('main', result)
        result = get_component_by_package_suite('hello', ['sid'], \
            arch_list = ['amd64'], session = self.session)
        self.assertEqual(None, result)

if __name__ == '__main__':
    unittest.main()
