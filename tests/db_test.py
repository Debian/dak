from base_test import DakTestCase, fixture

from daklib.config import Config
from daklib.dbconn import DBConn

from sqlalchemy import create_engine, __version__
from sqlalchemy.exc import SADeprecationWarning

import pickle
import warnings

# suppress some deprecation warnings in squeeze related to sqlalchemy
warnings.filterwarnings('ignore', \
    "The SQLAlchemy PostgreSQL dialect has been renamed from 'postgres' to 'postgresql'.*", \
    SADeprecationWarning)

class DBDakTestCase(DakTestCase):
    def setUp(self):
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
        self.metadata = pickle.load(pickle_file)
        self.metadata.ddl_listeners = pickle.load(pickle_file)
        pickle_file.close()
        self.metadata.bind = create_engine(connstr)
        self.metadata.create_all()
        self.session = DBConn().session()

    def tearDown(self):
        self.session.close()
        #self.metadata.drop_all()

