#!/usr/bin/python

# recreate the pickle file db-metadata-*.pkl that needs to be updated
# after a database upgrade

from sqlalchemy import create_engine, __version__

import pickle
import sys
from os.path import abspath, dirname

DAK_TEST_DIR = dirname(abspath(__file__))
DAK_ROOT_DIR = dirname(DAK_TEST_DIR)
if DAK_ROOT_DIR not in sys.path:
    sys.path.insert(0, DAK_ROOT_DIR)

from daklib.dbconn import DBConn

pickle_filename = '%s/fixtures/db-metadata-%s.pkl' % (DAK_TEST_DIR, __version__)
pickle_file = open(pickle_filename, 'w')
metadata = DBConn().db_meta
pickle.dump(metadata, pickle_file)
pickle.dump(metadata.ddl_listeners, pickle_file)
pickle_file.close()
print "File %s has been updated successfully." % pickle_filename
