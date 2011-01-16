from base_test import DakTestCase, fixture

from daklib.config import Config
from daklib.dbconn import DBConn

from sqlalchemy import create_engine, __version__
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

    def setUp(self):
        if self.metadata is None:
            self.initialize()
        self.session = DBConn().session()

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
            self.session.query(class_).delete()
        self.session.commit()
        # usually there is no need to drop all tables here
        #self.metadata.drop_all()

