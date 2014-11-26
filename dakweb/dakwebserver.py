#!/usr/bin/python

# Main script to run the dakweb server and also
# to provide the list_paths and path_help functions

from sqlalchemy import or_
import bottle
from daklib.dbconn import DBConn, DBSource, Suite, DSCFile, PoolFile
import json

from dakweb.webregister import QueryRegister

@bottle.route('/')
def root_path():
    """Returns a useless welcome message"""
    return json.dumps('Use the /list_paths path to list all available paths')
QueryRegister().register_path('/', root_path)

@bottle.route('/list_paths')
def list_paths():
    """Returns a list of available paths"""
    return json.dumps(QueryRegister().get_paths())
QueryRegister().register_path('/list_paths', list_paths)

@bottle.route('/path_help/<path>')
def path_help(path=None):

    if path is None:
        return bottle.HTTPError(503, 'Path not specified.')

    return json.dumps(QueryRegister().get_path_help(path))
QueryRegister().register_path('/path_help', list_paths)

# Import our other methods
from queries.archive import *
from queries.madison import *
from queries.source import *
from queries.suite import *

# Set up our initial database connection
d = DBConn()

# Run the bottle if we're called directly
if __name__ == '__main__':
    bottle.run()
