#!/usr/bin/env python
"""
Import data for Packages files from .deb files

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2008, 2009 Michael Casadevall <mcasadevall@debian.org>
@copyright: 2009 Mike O'Connor <stew@debian.org>
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
from daklib.packages import PackagesScanner
from daklib import daklog
from daklib import utils

################################################################################

def usage (exit_code=0):
    print """Usage: dak packagescan [options] subcommand

SUBCOMMANDS
    scan
        scan the debs in the existing pool and load metadata into the database

OPTIONS
     -h, --help
        show this help and exit

OPTIONS for scan
     -l, --limit=NUMBER
        maximum number of packages to scan
"""
    sys.exit(exit_code)

################################################################################

def scan_all(cnf, limit):
    Logger = daklog.Logger(cnf.Cnf, 'packages scan')
    result = PackagesScanner.scan_all(limit)
    processed = '%(processed)d packages processed' % result
    remaining = '%(remaining)d packages remaining' % result
    Logger.log([processed, remaining])
    Logger.close()

################################################################################

def main():
    cnf = Config()
    cnf['Packages::Options::Help'] = ''
    cnf['Packages::Options::Suite'] = ''
    cnf['Packages::Options::Limit'] = ''
    cnf['Packages::Options::Force'] = ''
    arguments = [('h', "help",  'Packages::Options::Help'),
                 ('s', "suite", 'Packages::Options::Suite', "HasArg"),
                 ('l', "limit", 'Packages::Options::Limit', "HasArg"),
                 ('f', "force", 'Packages::Options::Force'),
                ]
    args = apt_pkg.ParseCommandLine(cnf.Cnf, arguments, sys.argv)
    options = cnf.SubTree('Packages::Options')

    if (len(args) != 1) or options['Help']:
        usage()

    limit = None
    if len(options['Limit']) > 0:
        limit = int(options['Limit'])

    if args[0] == 'scan':
        scan_all(cnf, limit)
        return

    suite_names = utils.split_args(options['Suite'])

    force = bool(options['Force'])

    if args[0] == 'generate':
        raise NotImplementError

    usage()


if __name__ == '__main__':
    main()
