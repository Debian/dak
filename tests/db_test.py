from base_test import DakTestCase, fixture

from daklib.config import Config
from daklib.dbconn import *

from sqlalchemy import create_engine, func, __version__
from sqlalchemy.exc import SADeprecationWarning
from sqlalchemy.schema import DDL

import pickle
import warnings

all_tables = ['architecture', 'archive', 'bin_associations', 'bin_contents',
    'binaries', 'binary_acl', 'binary_acl_map', 'build_queue', 'build_queue_files',
    'changes', 'changes_pending_binaries', 'changes_pending_files',
    'changes_pending_files_map', 'changes_pending_source',
    'changes_pending_source_files', 'changes_pool_files', 'component', 'config',
    'dsc_files', 'files', 'fingerprint', 'keyring_acl_map', 'keyrings', 'location',
    'maintainer', 'new_comments', 'override', 'override_type', 'policy_queue',
    'priority', 'section', 'source', 'source_acl', 'src_associations',
    'src_format', 'src_uploaders', 'suite', 'suite_architectures',
    'suite_build_queue_copy', 'suite_src_formats', 'uid', 'upload_blocks']

drop_plpgsql = "DROP LANGUAGE IF EXISTS plpgsql CASCADE"
create_plpgsql = "CREATE LANGUAGE plpgsql"
create_function = """CREATE OR REPLACE FUNCTION tfunc_set_modified() RETURNS trigger AS $$
    BEGIN NEW.modified = now(); return NEW; END;
    $$ LANGUAGE 'plpgsql'"""
create_trigger = """CREATE TRIGGER modified_%s BEFORE UPDATE ON %s
    FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified()"""

class DBDakTestCase(DakTestCase):
    def execute(self, statement):
        DDL(statement).execute(self.metadata.bind)

    def create_all_triggers(self):
        for statement in (drop_plpgsql, create_plpgsql, create_function):
            self.execute(statement)
        for table in all_tables:
            self.execute(create_trigger % (table, table))

    metadata = None

    def initialize(self):
        cnf = Config()
        if cnf["DB::Name"] in ('backports', 'obscurity', 'projectb'):
            self.fail("You have configured an invalid database name: '%s'." % \
                    cnf["DB::Name"])
        if cnf["DB::Host"]:
            # TCP/IP
            connstr = "postgres://%s" % cnf["DB::Host"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += ":%s" % cnf["DB::Port"]
            connstr += "/%s" % cnf["DB::Name"]
        else:
            # Unix Socket
            connstr = "postgres:///%s" % cnf["DB::Name"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += "?port=%s" % cnf["DB::Port"]

        pickle_filename = 'db-metadata-%s.pkl' % __version__
        pickle_file = open(fixture(pickle_filename), 'r')
        DBDakTestCase.metadata = pickle.load(pickle_file)
        self.metadata.ddl_listeners = pickle.load(pickle_file)
        pickle_file.close()
        self.metadata.bind = create_engine(connstr)
        self.metadata.create_all()
        self.create_all_triggers()

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

    def setup_components(self):
        'create some Component objects'

        if 'comp' in self.__dict__:
            return
        self.comp = {}
        for name in ('main', 'contrib', 'non-free'):
            self.comp[name] = Component(component_name = name)
        self.session.add_all(self.comp.values())

    def setup_locations(self):
        'create some Location objects'

        if 'loc' in self.__dict__:
            return
        self.setup_components()
        self.loc = {}
        self.loc['main'] = Location( \
            path = fixture('ftp/pool/'), component = self.comp['main'])
        self.loc['contrib'] = Location( \
            path = fixture('ftp/pool/'), component = self.comp['contrib'])
        self.session.add_all(self.loc.values())

    def setup_poolfiles(self):
        'create some PoolFile objects'

        if 'file' in self.__dict__:
            return
        self.setup_locations()
        self.file = {}
        self.file['hello_2.2-3.dsc'] = PoolFile(filename = 'main/h/hello/hello_2.2-3.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['hello_2.2-2.dsc'] = PoolFile(filename = 'main/h/hello/hello_2.2-2.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['hello_2.2-1.dsc'] = PoolFile(filename = 'main/h/hello/hello_2.2-1.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['gnome-hello_3.0-1.dsc'] = PoolFile( \
            filename = 'main/g/gnome-hello/gnome-hello_3.0-1.dsc', \
            location = self.loc['contrib'], filesize = 0, md5sum = '')
        self.file['hello_2.2-1_i386.deb'] = PoolFile( \
            filename = 'main/h/hello/hello_2.2-1_i386.deb', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['gnome-hello_2.2-1_i386.deb'] = PoolFile( \
            filename = 'main/h/hello/gnome-hello_2.2-1_i386.deb', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['python-hello_2.2-1_all.deb'] = PoolFile( \
            filename = 'main/h/hello/python-hello_2.2-1_all.deb', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['gnome-hello_3.0-1_i386.deb'] = PoolFile( \
            filename = 'main/g/gnome-hello/gnome-hello_3.0-1_i386.deb', \
            location = self.loc['contrib'], filesize = 0, md5sum = '')
        self.file['sl_3.03-16.dsc'] = PoolFile(filename = 'main/s/sl/sl_3.03-16.dsc', \
            location = self.loc['main'], filesize = 0, md5sum = '')
        self.file['python2.6_2.6.6-8.dsc'] = PoolFile( \
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
        'create DBSource objects'

        if 'source' in self.__dict__:
            return
        install_date = self.now()
        self.setup_maintainers()
        self.setup_suites()
        self.setup_poolfiles()
        self.source = {}
        self.source['hello_2.2-2'] = DBSource(source = 'hello', version = '2.2-2', \
            maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['hello_2.2-2.dsc'], install_date = install_date)
        self.source['hello_2.2-2'].suites.append(self.suite['sid'])
        self.source['hello_2.2-1'] = DBSource(source = 'hello', version = '2.2-1', \
            maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['hello_2.2-1.dsc'], install_date = install_date)
        self.source['hello_2.2-1'].suites.append(self.suite['sid'])
        self.source['gnome-hello_3.0-1'] = DBSource(source = 'gnome-hello', \
            version = '3.0-1', maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['gnome-hello_3.0-1.dsc'], install_date = install_date)
        self.source['gnome-hello_3.0-1'].suites.append(self.suite['sid'])
        self.source['sl_3.03-16'] = DBSource(source = 'sl', version = '3.03-16', \
            maintainer = self.maintainer['maintainer'], \
            changedby = self.maintainer['uploader'], \
            poolfile = self.file['sl_3.03-16.dsc'], install_date = install_date)
        self.source['sl_3.03-16'].suites.append(self.suite['squeeze'])
        self.source['sl_3.03-16'].suites.append(self.suite['sid'])
        self.session.add_all(self.source.values())

    def setup_binaries(self):
        'create DBBinary objects'

        if 'binary' in self.__dict__:
            return
        self.setup_sources()
        self.setup_architectures()
        self.binary = {}
        self.binary['hello_2.2-1_i386'] = DBBinary(package = 'hello', \
            source = self.source['hello_2.2-1'], version = '2.2-1', \
            maintainer = self.maintainer['maintainer'], \
            architecture = self.arch['i386'], \
            poolfile = self.file['hello_2.2-1_i386.deb'])
        self.binary['hello_2.2-1_i386'].suites.append(self.suite['squeeze'])
        self.binary['hello_2.2-1_i386'].suites.append(self.suite['sid'])
        self.binary['gnome-hello_2.2-1_i386'] = DBBinary(package = 'gnome-hello', \
            source = self.source['hello_2.2-1'], version = '2.2-1', \
            maintainer = self.maintainer['maintainer'], \
            architecture = self.arch['i386'], \
            poolfile = self.file['gnome-hello_2.2-1_i386.deb'])
        self.binary['gnome-hello_2.2-1_i386'].suites.append(self.suite['squeeze'])
        self.binary['gnome-hello_2.2-1_i386'].suites.append(self.suite['sid'])
        self.binary['gnome-hello_3.0-1_i386'] = DBBinary(package = 'gnome-hello', \
            source = self.source['gnome-hello_3.0-1'], version = '3.0-1', \
            maintainer = self.maintainer['maintainer'], \
            architecture = self.arch['i386'], \
            poolfile = self.file['gnome-hello_3.0-1_i386.deb'])
        self.binary['gnome-hello_3.0-1_i386'].suites.append(self.suite['sid'])
        self.binary['python-hello_2.2-1_i386'] = DBBinary(package = 'python-hello', \
            source = self.source['hello_2.2-1'], version = '2.2-1', \
            maintainer = self.maintainer['maintainer'], \
            architecture = self.arch['all'], \
            poolfile = self.file['python-hello_2.2-1_all.deb'])
        self.binary['python-hello_2.2-1_i386'].suites.append(self.suite['squeeze'])
        self.session.add_all(self.binary.values())

    def setup_overridetypes(self):
        '''
        Setup self.otype of class OverrideType.
        '''
        if 'otype' in self.__dict__:
            return
        self.otype = {}
        for type_ in ('deb', 'udeb'):
            self.otype[type_] = OverrideType(overridetype = type_)
        self.session.add_all(self.otype.values())
        self.session.flush()

    def setup_sections(self):
        '''
        Setup self.section of class Section.
        '''
        if 'section' in self.__dict__:
            return
        self.section = {}
        self.section['python'] = Section(section = 'python')
        self.session.add_all(self.section.values())
        self.session.flush()

    def setup_priorities(self):
        '''
        Setup self.prio of class Priority.
        '''
        if 'prio' in self.__dict__:
            return
        self.prio = {}
        self.prio['standard'] = Priority(priority = 'standard', level = 7)
        self.session.add_all(self.prio.values())
        self.session.flush()

    def setup_overrides(self):
        '''
        Setup self.override of class Override.
        '''
        if 'override' in self.__dict__:
            return
        self.setup_suites()
        self.setup_components()
        self.setup_overridetypes()
        self.setup_sections()
        self.setup_priorities()
        self.override = {}
        self.override['hello_sid_main_udeb'] = Override(package = 'hello', \
            suite = self.suite['sid'], component = self.comp['main'], \
            overridetype = self.otype['udeb'], \
            section = self.section['python'], priority = self.prio['standard'])
        self.override['hello_squeeze_main_deb'] = Override(package = 'hello', \
            suite = self.suite['squeeze'], component = self.comp['main'], \
            overridetype = self.otype['deb'], \
            section = self.section['python'], priority = self.prio['standard'])
        self.override['hello_lenny_contrib_deb'] = Override(package = 'hello', \
            suite = self.suite['lenny'], component = self.comp['contrib'], \
            overridetype = self.otype['deb'], \
            section = self.section['python'], priority = self.prio['standard'])
        self.session.add_all(self.override.values())
        self.session.flush()

    def setUp(self):
        if self.metadata is None:
            self.initialize()
        self.session = DBConn().session()

    def now(self):
        """
        Returns the current time at the db server. Please note the function
        returns the same value as long as it is in the same transaction. You
        should self.session.rollback() (or commit) if you rely on getting a
        fresh timestamp.
        """

        return self.session.query(func.now()).scalar()

    def classes_to_clean(self):
        """
        The function classes_to_clean() returns a list of classes. All objects
        of each class will be deleted from the database in tearDown(). This
        function should be overridden in derived test cases as needed.
        """
        return ()

    def tearDown(self):
        self.session.rollback()
        for class_ in self.classes_to_clean():
            for object_ in self.session.query(class_):
                self.session.delete(object_)
        self.session.commit()
        # usually there is no need to drop all tables here
        #self.metadata.drop_all()

