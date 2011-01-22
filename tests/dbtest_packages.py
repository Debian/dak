#!/usr/bin/env python

from db_test import DBDakTestCase

from daklib.dbconn import Architecture, Suite, get_suite_architectures, \
    get_architecture_suites, Maintainer, DBSource, Location, PoolFile, \
    check_poolfile, get_poolfile_like_name, get_source_in_suite

from sqlalchemy.orm.exc import MultipleResultsFound
import unittest

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

    def setUp(self):
        super(PackageTestCase, self).setUp()
        self.setup_architectures()
        self.setup_suites()

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

    def setup_locations(self):
        'create some Location objects, TODO: add component'

        if 'loc' in self.__dict__:
            return
        self.loc = {}
        self.loc['main'] = Location(path = \
            '/srv/ftp-master.debian.org/ftp/pool/')
        self.session.add(self.loc['main'])

    def setup_poolfiles(self):
        'create some PoolFile objects'

        if 'file' in self.__dict__:
            return
        self.setup_locations()
        self.file = {}
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

        self.setup_poolfiles()
        location = self.session.query(Location)[0]
        self.assertEqual('/srv/ftp-master.debian.org/ftp/pool/', location.path)
        self.assertEqual(4, location.files.count())
        poolfile = location.files. \
                filter(PoolFile.filename.like('%/hello/hello%')). \
                order_by(PoolFile.filename)[1]
        self.assertEqual('main/h/hello/hello_2.2-2.dsc', poolfile.filename)
        self.assertEqual(location, poolfile.location)
        # test get()
        self.assertEqual(poolfile, \
                self.session.query(PoolFile).get(poolfile.file_id))
        self.assertEqual(None, self.session.query(PoolFile).get(-1))
        # test remove() and append()
        location.files.remove(self.file['sl'])
        # TODO: deletion should cascade automatically
        self.session.delete(self.file['sl'])
        self.session.refresh(location)
        self.assertEqual(3, location.files.count())
        # please note that we intentionally do not specify 'location' here
        self.file['sl'] = PoolFile(filename = 'main/s/sl/sl_3.03-16.dsc', \
            filesize = 0, md5sum = '')
        location.files.append(self.file['sl'])
        self.session.refresh(location)
        self.assertEqual(4, location.files.count())
        # test fullpath
        self.assertEqual('/srv/ftp-master.debian.org/ftp/pool/main/s/sl/sl_3.03-16.dsc', \
            self.file['sl'].fullpath)
        # test check_poolfile()
        self.assertEqual((True, self.file['sl']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 0, '', \
                location.location_id, self.session))
        self.assertEqual((False, None), \
            check_poolfile('foobar', 0, '', location.location_id, self.session))
        self.assertEqual((False, self.file['sl']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 42, '', \
                location.location_id, self.session))
        self.assertEqual((False, self.file['sl']), \
            check_poolfile('main/s/sl/sl_3.03-16.dsc', 0, 'deadbeef', \
                location.location_id, self.session))
        # test get_poolfile_like_name()
        self.assertEqual([self.file['sl']], \
            get_poolfile_like_name('sl_3.03-16.dsc', self.session))
        self.assertEqual([], get_poolfile_like_name('foobar', self.session))

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
        self.setup_poolfiles()
        self.setup_suites()
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

    def test_maintainers(self):
        '''
        tests relation between Maintainer and DBSource

        TODO: add relations to changes_pending_source
        '''

        self.setup_sources()
        self.session.flush()
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

        self.setup_sources()
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


if __name__ == '__main__':
    unittest.main()
