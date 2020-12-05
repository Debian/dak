#! /usr/bin/env python3

""" Main script to run the dakweb server and also
to provide the list_paths and path_help functions

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2014  Mark Hymers <mhy@debian.org>
@license: GNU General Public License version 2 or later
"""

import bottle
from bottle import redirect
from daklib.dbconn import DBConn
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
    redirect("https://ftp-team.pages.debian.net/dak/epydoc/dakweb-module.html#__package__")


QueryRegister().register_path('/list_paths', list_paths)


@bottle.route('/path_help/<path>')
def path_help(path=None):
    """Redirects to the API description containing the path_help"""
    if path is None:
        return bottle.HTTPError(503, 'Path not specified.')

    redirect("https://ftp-team.pages.debian.net/dak/epydoc/%s-module.html#%s" %
             (QueryRegister().get_path_help(path), path))


QueryRegister().register_path('/path_help', list_paths)

# Import our other methods
from .queries.archive import *
from .queries.madison import *
from .queries.source import *
from .queries.suite import *
from .queries.binary import *

# Set up our initial database connection
d = DBConn()

# Run the bottle if we're called directly
if __name__ == '__main__':
    bottle.run()
