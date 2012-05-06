#!/usr/bin/env python
"""
Import data for Package/Sources files from .deb and .dsc files
@copyright: 2011 Torsten Werner <twerner@debian.org>
@copyright: 2011 Mark Hymers <mhy@debian.org>
@license: GNU General Public License version 2 or later
"""

################################################################################

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

################################################################################

# < mvo> that screams for consolidation in libapt at least (that then in turn can
#        use libdpkg ... ) - I guess the "d" means delayed ;)

# (whilst discussing adding xz support to dak, and therefore python-apt, and
#        therefore libapt-pkg)

################################################################################

import sys
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib.metadata import MetadataScanner
from daklib import daklog
from daklib import utils

################################################################################

def usage (exit_code=0):
    print """Usage: dak metadata [options] subcommand

SUBCOMMANDS
    scan-source
        scan the dsc files in the existing pool and load metadata into the database

    scan-binary
        scan the deb files in the existing pool and load metadata into the database

OPTIONS
     -h, --help
        show this help and exit

OPTIONS for scan
     -l, --limit=NUMBER
        maximum number of items to scan
"""
    sys.exit(exit_code)

################################################################################

def scan_all(cnf, mode, limit):
    Logger = daklog.Logger('metadata scan (%s)' % mode)
    result = MetadataScanner.scan_all(mode, limit)
    processed = '%(processed)d %(type)s processed' % result
    remaining = '%(remaining)d %(type)s remaining' % result
    Logger.log([processed, remaining])
    Logger.close()

################################################################################

def main():
    cnf = Config()
    cnf['Metadata::Options::Help'] = ''
    cnf['Metadata::Options::Suite'] = ''
    cnf['Metadata::Options::Limit'] = ''
    cnf['Metadata::Options::Force'] = ''
    arguments = [('h', "help",  'Metadata::Options::Help'),
                 ('s', "suite", 'Metadata::Options::Suite', "HasArg"),
                 ('l', "limit", 'Metadata::Options::Limit', "HasArg"),
                 ('f', "force", 'Metadata::Options::Force'),
                ]
    args = apt_pkg.parse_commandline(cnf.Cnf, arguments, sys.argv)
    options = cnf.subtree('Metadata::Options')

    if (len(args) != 1) or options['Help']:
        usage()

    limit = None
    if len(options['Limit']) > 0:
        limit = int(options['Limit'])

    if args[0] == 'scan-source':
        scan_all(cnf, 'source', limit)
        return
    elif args[0] == 'scan-binary':
        scan_all(cnf, 'binary', limit)
        return

    suite_names = utils.split_args(options['Suite'])

    force = bool(options['Force'])

    if args[0] == 'generate':
        raise NotImplementError

    usage()


if __name__ == '__main__':
    main()
