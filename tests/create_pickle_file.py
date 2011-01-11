#!/usr/bin/python

# recreate the pickle file db-metadata-*.pkl that needs to be updated
# after a database upgrade

from base_test import fixture
from daklib.dbconn import DBConn

from sqlalchemy import create_engine, __version__

import pickle

pickle_filename = fixture('db-metadata-%s.pkl' % __version__)
pickle_file = open(pickle_filename, 'w')
metadata = DBConn().db_meta
pickle.dump(metadata, pickle_file)
pickle.dump(metadata.ddl_listeners, pickle_file)
pickle_file.close()
print "File %s has been updated successfully." % pickle_filename
