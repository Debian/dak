#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Architecture, Suite, get_suite_architectures, \
    get_architecture_suites, Maintainer, DBSource, Location, PoolFile, \
    check_poolfile, get_poolfile_like_name, get_source_in_suite, \
    get_suites_source_in, add_dsc_to_db, source_exists
from daklib.queue_install import package_to_suite
from daklib.queue import get_newest_source, get_suite_version

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

    def setup_suites(self):
        "setup a hash of Suite objects in self.suite"

        if 'suite' in self.__dict__:
            return
        self.suite = {}
        for suite_name in ('lenny', 'squeeze', 'sid'):
            self.suite[suite_name] = Suite(suite_name = suite_name, version = '-')
        self.session.add_all(self.suite.values())

    def setup_architectures(self):
        "setup Architecture objects in self.arch and connect to suites"

        if 'arch' in self.__dict__:
            return
        self.setup_suites()
        self.arch = {}
        for arch_string in ('source', 'all', 'i386', 'amd64', 'kfreebsd-i386'):
            self.arch[arch_string] = Architecture(arch_string)
            if arch_string != 'kfreebsd-i386':
                self.arch[arch_string].suites = self.suite.values()
            else:
                self.arch[arch_string].suites = [self.suite['squeeze'], self.suite['sid']]
        # hard code ids for source and all
        self.arch['source'].arch_id = 1
        self.arch['all'].arch_id = 2
        self.session.add_all(self.arch.values())

    def setup_locations(self):
        'create some Location objects, TODO: add component'

        if 'loc' in self.__dict__:
            return
        self.loc = {}
        self.loc['main'] = Location(path = \
            '/srv/ftp-master.debian.org/ftp/pool/')
        self.loc['contrib'] = Location(path = \
            '/srv/ftp-master.debian.org/ftp/pool/')
        self.session.add_all(self.loc.values())

    def setup_poolfiles(self):
        'create some PoolFile objects'

        if 'file' in self.__dict__:
            return
        self.setup_locations()
        self.file = {}
        self.file['hello_new'] = PoolFile(filename = 'main/h/hello/hello_2.2-3.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['hello'] = PoolFile(filename = 'main/h/hello/hello_2.2-2.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['hello_old'] = PoolFile(filename = 'main/h/hello/hello_2.2-1.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['sl'] = PoolFile(filename = 'main/s/sl/sl_3.03-16.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['python'] = PoolFile( \
            filename = 'main/p/python2.6/python2.6_2.6.6-8.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.session.add_all(self.file.values())

    def setup_maintainers(self):
        'create some Maintainer objects'

        if 'maintainer' in self.__dict__:
            return
        self.maintainer = {}
        self.maintainer['maintainer'] = Maintainer(name = 'Mr. Maintainer')
        self.maintainer['uploader'] = Maintainer(name = 'Mrs. Uploader')
        self.maintainer['lazyguy'] = Maintainer(name = 'Lazy Guy')
        self.session.add_all(self.maintainer.values())

    def setup_sources(self):
        'create a DBSource object; but it cannot be stored in the DB yet'

        if 'source' in self.__dict__:
            return
        self.setup_maintainers()
        self.source = {}
        self.source['hello'] = DBSource(source = 'hello', version = '2.2-2', \
            maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['hello'], install_date = self.now())
        self.source['hello'].suites.append(self.suite['sid'])
        self.source['hello_old'] = DBSource(source = 'hello', version = '2.2-1', \
            maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['hello_old'], install_date = self.now())
        self.source['hello_old'].suites.append(self.suite['sid'])
        self.source['sl'] = DBSource(source = 'sl', version = '3.03-16', \
            maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['sl'], install_date = self.now())
        self.source['sl'].suites.append(self.suite['squeeze'])
        self.source['sl'].suites.append(self.suite['sid'])
        self.session.add_all(self.source.values())

    def setUp(self):
        super(PackageTestCase, self).setUp()
        self.setup_architectures()
        self.setup_poolfiles()
        self.setup_sources()
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
        # check the function get_architecture_suites()
        suites = get_architecture_suites('i386', self.session)
        self.assertEqual(3, len(suites))
        self.assertTrue(self.suite['lenny'] in suites)
        suites = get_architecture_suites('kfreebsd-i386', self.session)
        self.assertEqual(2, len(suites))
        self.assertTrue(self.suite['lenny'] not in suites)

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
        self.assertEqual('/srv/ftp-master.debian.org/ftp/pool/', main.path)
        self.assertEqual(5, main.files.count())
        self.assertEqual(0, contrib.files.count())
        poolfile = main.files. \
                filter(PoolFile.filename.like('%/hello/hello%')). \
                order_by(PoolFile.filename)[1]
        self.assertEqual('main/h/hello/hello_2.2-2.dsc', poolfile.filename)
        self.assertEqual(main, poolfile.location)
        # test get()
        self.assertEqual(poolfile, \
                self.session.query(PoolFile).get(poolfile.file_id))
        self.assertEqual(None, self.session.query(PoolFile).get(-1))
        # test remove() and append()
        main.files.remove(self.file['sl'])
        contrib.files.append(self.file['sl'])
        self.assertEqual(4, main.files.count())
        self.assertEqual(1, contrib.files.count())
        # test fullpath
        self.assertEqual('/srv/ftp-master.debian.org/ftp/pool/main/s/sl/sl_3.03-16.dsc', \
            self.file['sl'].fullpath)
        # test check_poolfile()
        self.assertEqual((True, self.file['sl']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 0, '', \
                contrib.location_id, self.session))
        self.assertEqual((False, None), \
            check_poolfile('foobar', 0, '', contrib.location_id, self.session))
        self.assertEqual((False, self.file['sl']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 42, '', \
                contrib.location_id, self.session))
        self.assertEqual((False, self.file['sl']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 0, 'deadbeef', \
                contrib.location_id, self.session))
        # test get_poolfile_like_name()
        self.assertEqual([self.file['sl']], \
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
        self.assertEqual(3, len(maintainer.maintains_sources))
        self.assertTrue(self.source['hello'] in maintainer.maintains_sources)
        self.assertEqual(maintainer.changed_sources, [])
        self.assertEqual(uploader.maintains_sources, [])
        self.assertEqual(3, len(uploader.changed_sources))
        self.assertTrue(self.source['sl'] in uploader.changed_sources)
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
        self.assertEqual(self.file['hello'], self.source['hello'].poolfile)
        self.assertEqual(self.source['hello'], self.file['hello'].source)
        self.assertEqual(None, self.file['python'].source)
        # test Suite
        squeeze = self.session.query(Suite). \
            filter(Suite.sources.contains(self.source['sl'])). \
            order_by(Suite.suite_name)[1]
        self.assertEqual(self.suite['squeeze'], squeeze)
        self.assertEqual(1, len(squeeze.sources))
        self.assertEqual(self.source['sl'], squeeze.sources[0])
        sl = self.session.query(DBSource). \
            filter(DBSource.suites.contains(self.suite['squeeze'])).one()
        self.assertEqual(self.source['sl'], sl)
        self.assertEqual(2, len(sl.suites))
        self.assertTrue(self.suite['sid'] in sl.suites)
        # test get_source_in_suite()
        self.assertRaises(MultipleResultsFound, self.get_source_in_suite_fail)
        self.assertEqual(None, \
            get_source_in_suite('hello', 'squeeze', self.session))
        self.assertEqual(self.source['sl'], \
            get_source_in_suite('sl', 'sid', self.session))
        # test get_suites_source_in()
        self.assertEqual([self.suite['sid']], \
            get_suites_source_in('hello', self.session))
        self.assertEqual(2, len(get_suites_source_in('sl', self.session)))
        self.assertTrue(self.suite['squeeze'] in \
            get_suites_source_in('sl', self.session))

    def test_upload(self):
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
            'location id': self.loc['main'].component_id,
            'files id': self.file['hello_new'].file_id }
        pkg.dsc_files = {}
        upload = Upload(pkg)
        (source, dsc_component, dsc_location_id, pfs) = \
            add_dsc_to_db(upload, 'hello_2.2-3.dsc', self.session)
        self.assertEqual('hello', source.source)
        self.assertEqual('2.2-3', source.version)
        self.assertEqual('sid', source.suites[0].suite_name)
        self.assertEqual('main', dsc_component)
        # no dsc files defined above
        self.assertEqual(None, dsc_location_id)
        self.assertEqual([], pfs)

    def test_source_exists(self):
        'test function source_exists()'

        hello = self.source['hello']
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
        pkg.changes['source'] = self.source['hello'].source
        pkg.changes['version'] = self.source['hello'].version
        self.assertTrue(not package_to_suite(upload, 'sid', self.session))
        pkg.changes['version'] = '42'
        self.assertTrue(package_to_suite(upload, 'sid', self.session))
        pkg.changes['source'] = 'foobar'
        pkg.changes['version'] = self.source['hello'].version
        self.assertTrue(package_to_suite(upload, 'sid', self.session))
        pkg.changes['distribution'] = { 'lenny': '' }
        self.assertTrue(package_to_suite(upload, 'lenny', self.session))

    def test_get_newest_source(self):
        'test function get_newest_source()'

        import daklib.queue
        daklib.queue.dm_suites = ['sid']
        self.assertEqual(self.source['hello'], get_newest_source('hello', self.session))
        self.assertEqual(None, get_newest_source('foobar', self.session))

    def test_get_suite_version(self):
        'test function get_suite_version()'

        result = get_suite_version('hello', self.session)
        self.assertEqual(2, len(result))
        self.assertTrue(('sid', '2.2-1') in result)
        self.assertTrue(('sid', '2.2-2') in result)
        result = get_suite_version('sl', self.session)
        self.assertEqual(2, len(result))
        self.assertTrue(('squeeze', '3.03-16') in result)
        self.assertTrue(('sid', '3.03-16') in result)

if __name__ == '__main__':
    unittest.main()
