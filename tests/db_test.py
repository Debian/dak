from base_test import DakTestCase, fixture

from daklib.config import Config
from daklib.dbconn import *

from sqlalchemy import create_engine, func, __version__
from sqlalchemy.schema import DDL

import pickle

all_tables = [
    'acl', 'acl_architecture_map', 'acl_fingerprint_map', 'acl_per_source',
    'architecture', 'archive', 'bin_associations', 'bin_contents', 'binaries',
    'binaries_metadata', 'build_queue', 'changelogs_text', 'changes',
    'component', 'component_suite', 'config', 'dsc_files', 'external_files',
    'external_overrides', 'external_signature_requests', 'extra_src_references',
    'files', 'files_archive_map', 'fingerprint', 'hashfile', 'keyrings',
    'maintainer', 'metadata_keys', 'new_comments', 'override', 'override_type',
    'policy_queue', 'policy_queue_byhand_file', 'policy_queue_upload',
    'policy_queue_upload_binaries_map', 'priority', 'section',
    'signature_history', 'source', 'source_metadata', 'src_associations',
    'src_contents', 'src_format', 'src_uploaders', 'suite', 'suite_acl_map',
    'suite_architectures', 'suite_build_queue_copy', 'suite_permission',
    'suite_src_formats', 'uid', 'version_check',
]


class DBDakTestCase(DakTestCase):
    def execute(self, statement):
        DDL(statement).execute(self.metadata.bind)

    metadata = None

    def initialize(self):
        cnf = Config()
        if cnf["DB::Name"] in ('backports', 'obscurity', 'projectb'):
            self.fail("You have configured an invalid database name: '%s'." %
                    cnf["DB::Name"])
        if cnf["DB::Host"]:
            # TCP/IP
            connstr = "postgresql://%s" % cnf["DB::Host"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += ":%s" % cnf["DB::Port"]
            connstr += "/%s" % cnf["DB::Name"]
        else:
            # Unix Socket
            connstr = "postgresql:///%s" % cnf["DB::Name"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += "?port=%s" % cnf["DB::Port"]

        self.metadata = DBConn().db_meta
        self.metadata.bind = create_engine(connstr)
        self.metadata.create_all()

    def setup_archive(self):
        if 'archive' in self.__dict__:
            return
        self.archive = self.session.query(Archive).get(1)

    def setup_suites(self, suites=None):
        "setup a hash of Suite objects in self.suite"

        if 'suite' in self.__dict__:
            return

        # Default suites. Can be overridden by passing a parameter with a list
        # of suite names and codenames.
        if not suites:
            suites = [('lenny', ''), ('squeeze', ''), ('sid', '')]

        self.setup_archive()
        self.suite = {}
        for suite_name, codename in suites:
            self.suite[suite_name] = get_suite(suite_name, self.session)
            if not self.suite[suite_name]:
                self.suite[suite_name] = Suite(suite_name=suite_name, version='-')
                self.suite[suite_name].archive_id = self.archive.archive_id
                self.suite[suite_name].codename = codename
                self.session.add(self.suite[suite_name])

    def setup_architectures(self):
        "setup Architecture objects in self.arch and connect to suites"

        if 'arch' in self.__dict__:
            return
        self.setup_suites()
        self.arch = {}
        for arch_string in ('source', 'all', 'i386', 'amd64', 'kfreebsd-i386'):
            self.arch[arch_string] = get_architecture(arch_string, self.session)
            if not self.arch[arch_string]:
                self.arch[arch_string] = Architecture(arch_string)
            if arch_string != 'kfreebsd-i386':
                self.arch[arch_string].suites = list(self.suite.values())
            else:
                filtered = list(self.suite.values())
                if 'lenny' in self.suite:
                    filtered.remove(self.suite['lenny'])
                self.arch[arch_string].suites = filtered
        self.session.add_all(self.arch.values())

    def setup_components(self):
        'create some Component objects'

        if 'comp' in self.__dict__:
            return
        self.comp = {}
        for name in ('main', 'contrib', 'non-free'):
            self.comp[name] = get_component(name, self.session)
            if not self.comp[name]:
                self.comp[name] = Component(component_name=name)
                self.session.add(self.comp[name])

    def setup_poolfiles(self):
        'create some PoolFile objects'

        if 'file' in self.__dict__:
            return
        self.setup_archive()
        self.setup_components()
        self.file = {}
        self.file['hello_2.2-3.dsc'] = PoolFile(filename='h/hello/hello_2.2-3.dsc',
            filesize=0, md5sum='')
        self.file['hello_2.2-2.dsc'] = PoolFile(filename='h/hello/hello_2.2-2.dsc',
            filesize=0, md5sum='')
        self.file['hello_2.2-1.dsc'] = PoolFile(filename='h/hello/hello_2.2-1.dsc',
            filesize=0, md5sum='')
        self.file['gnome-hello_3.0-1.dsc'] = PoolFile(
            filename='g/gnome-hello/gnome-hello_3.0-1.dsc',
            filesize=0, md5sum='')
        self.file['hello_2.2-1_i386.deb'] = PoolFile(
            filename='h/hello/hello_2.2-1_i386.deb',
            filesize=0, md5sum='')
        self.file['gnome-hello_2.2-1_i386.deb'] = PoolFile(
            filename='h/hello/gnome-hello_2.2-1_i386.deb',
            filesize=0, md5sum='')
        self.file['python-hello_2.2-1_all.deb'] = PoolFile(
            filename='h/hello/python-hello_2.2-1_all.deb',
            filesize=0, md5sum='')
        self.file['gnome-hello_3.0-1_i386.deb'] = PoolFile(
            filename='g/gnome-hello/gnome-hello_3.0-1_i386.deb',
            filesize=0, md5sum='')
        self.file['sl_3.03-16.dsc'] = PoolFile(filename='s/sl/sl_3.03-16.dsc',
            filesize=0, md5sum='')
        self.file['python2.6_2.6.6-8.dsc'] = PoolFile(
            filename='p/python2.6/python2.6_2.6.6-8.dsc',
            filesize=0, md5sum='')

        archive_files = []
        for f in self.file.values():
            f.sha1sum = 'sha1sum'
            f.sha256sum = 'sha256sum'
            if 'gnome-hello_3.0-1' not in f.filename:
                archive_files.append(ArchiveFile(
                    archive=self.archive, component=self.comp['main'], file=f))
            else:
                archive_files.append(ArchiveFile(
                    archive=self.archive, component=self.comp['contrib'], file=f))
        self.session.add_all(self.file.values())
        self.session.add_all(archive_files)

    def setup_maintainers(self):
        'create some Maintainer objects'

        if 'maintainer' in self.__dict__:
            return
        self.maintainer = {}
        self.maintainer['maintainer'] = get_or_set_maintainer('Mr.  Maintainer', self.session)
        self.maintainer['uploader'] = get_or_set_maintainer('Mrs.  Uploader', self.session)
        self.maintainer['lazyguy'] = get_or_set_maintainer('Lazy Guy', self.session)

    def setup_sources(self):
        'create DBSource objects'

        if 'source' in self.__dict__:
            return
        install_date = self.now()
        self.setup_maintainers()
        self.setup_suites()
        self.setup_poolfiles()
        self.source = {}
        self.source['hello_2.2-2'] = DBSource(source='hello', version='2.2-2',
            maintainer=self.maintainer['maintainer'],
            changedby=self.maintainer['uploader'],
            poolfile=self.file['hello_2.2-2.dsc'], install_date=install_date)
        self.source['hello_2.2-2'].suites.append(self.suite['sid'])
        self.source['hello_2.2-1'] = DBSource(source='hello', version='2.2-1',
            maintainer=self.maintainer['maintainer'],
            changedby=self.maintainer['uploader'],
            poolfile=self.file['hello_2.2-1.dsc'], install_date=install_date)
        self.source['hello_2.2-1'].suites.append(self.suite['sid'])
        self.source['gnome-hello_3.0-1'] = DBSource(source='gnome-hello',
            version='3.0-1', maintainer=self.maintainer['maintainer'],
            changedby=self.maintainer['uploader'],
            poolfile=self.file['gnome-hello_3.0-1.dsc'], install_date=install_date)
        self.source['gnome-hello_3.0-1'].suites.append(self.suite['sid'])
        self.source['sl_3.03-16'] = DBSource(source='sl', version='3.03-16',
            maintainer=self.maintainer['maintainer'],
            changedby=self.maintainer['uploader'],
            poolfile=self.file['sl_3.03-16.dsc'], install_date=install_date)
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
        self.binary['hello_2.2-1_i386'] = DBBinary(package='hello',
            source=self.source['hello_2.2-1'], version='2.2-1',
            maintainer=self.maintainer['maintainer'],
            architecture=self.arch['i386'],
            poolfile=self.file['hello_2.2-1_i386.deb'])
        self.binary['hello_2.2-1_i386'].suites.append(self.suite['squeeze'])
        self.binary['hello_2.2-1_i386'].suites.append(self.suite['sid'])
        self.binary['gnome-hello_2.2-1_i386'] = DBBinary(package='gnome-hello',
            source=self.source['hello_2.2-1'], version='2.2-1',
            maintainer=self.maintainer['maintainer'],
            architecture=self.arch['i386'],
            poolfile=self.file['gnome-hello_2.2-1_i386.deb'])
        self.binary['gnome-hello_2.2-1_i386'].suites.append(self.suite['squeeze'])
        self.binary['gnome-hello_2.2-1_i386'].suites.append(self.suite['sid'])
        self.binary['gnome-hello_3.0-1_i386'] = DBBinary(package='gnome-hello',
            source=self.source['gnome-hello_3.0-1'], version='3.0-1',
            maintainer=self.maintainer['maintainer'],
            architecture=self.arch['i386'],
            poolfile=self.file['gnome-hello_3.0-1_i386.deb'])
        self.binary['gnome-hello_3.0-1_i386'].suites.append(self.suite['sid'])
        self.binary['python-hello_2.2-1_i386'] = DBBinary(package='python-hello',
            source=self.source['hello_2.2-1'], version='2.2-1',
            maintainer=self.maintainer['maintainer'],
            architecture=self.arch['all'],
            poolfile=self.file['python-hello_2.2-1_all.deb'])
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
            self.otype[type_] = get_override_type(type_, self.session)

    def setup_sections(self):
        '''
        Setup self.section of class Section.
        '''
        if 'section' in self.__dict__:
            return
        self.section = {}
        self.section['python'] = get_section('python', self.session)

    def setup_priorities(self):
        '''
        Setup self.prio of class Priority.
        '''
        if 'prio' in self.__dict__:
            return
        self.prio = {}
        self.prio['standard'] = get_priority('standard', self.session)

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
        self.override['hello_sid_main_udeb'] = Override(package='hello',
            suite=self.suite['sid'], component=self.comp['main'],
            overridetype=self.otype['udeb'],
            section=self.section['python'], priority=self.prio['standard'])
        self.override['hello_squeeze_main_deb'] = Override(package='hello',
            suite=self.suite['squeeze'], component=self.comp['main'],
            overridetype=self.otype['deb'],
            section=self.section['python'], priority=self.prio['standard'])
        self.override['hello_lenny_contrib_deb'] = Override(package='hello',
            suite=self.suite['lenny'], component=self.comp['contrib'],
            overridetype=self.otype['deb'],
            section=self.section['python'], priority=self.prio['standard'])
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

    def clean_suites(self):
        for suite in self.suite.values():
            self.session.delete(suite)

    def tearDown(self):
        self.session.rollback()
        for class_ in self.classes_to_clean():
            for object_ in self.session.query(class_):
                self.session.delete(object_)
        self.session.commit()
        # usually there is no need to drop all tables here
        # self.metadata.drop_all()
