import sys
import os

sys.path.append('/srv/ftp-master.debian.org/dak')

import bottle

import dakweb.dakwebserver

application = bottle.default_app()

