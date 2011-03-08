#!/usr/bin/env python
"""
Create all the contents files

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2008, 2009 Michael Casadevall <mcasadevall@debian.org>
@copyright: 2009 Mike O'Connor <stew@debian.org>
@copyright: 2011 Torsten Werner <twerner@debian.org>
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

# <Ganneff> there is the idea to slowly replace contents files
# <Ganneff> with a new generation of such files.
# <Ganneff> having more info.

# <Ganneff> of course that wont help for now where we need to generate them :)

################################################################################

import sys
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib.contents import ContentsScanner, ContentsWriter
from daklib import daklog
from daklib import utils

################################################################################

def usage (exit_code=0):
    print """Usage: dak contents [options] subcommand

SUBCOMMANDS
    generate
        generate Contents-$arch.gz files

    scan
        scan the debs in the existing pool and load contents into the bin_contents table

OPTIONS
     -h, --help
        show this help and exit

OPTIONS for generate
     -s, --suite={stable,testing,unstable,...}
        only operate on specified suite names

     -f, --force
        write Contents files for suites marked as untouchable, too

OPTIONS for scan
     -l, --limit=NUMBER
        maximum number of packages to scan
"""
    sys.exit(exit_code)

################################################################################

def write_all(cnf, suite_names = [], force = None):
    Logger = daklog.Logger(cnf.Cnf, 'contents generate')
    ContentsWriter.write_all(suite_names, force)
    Logger.close()

################################################################################

def write_helper(suite_name, argv):
    session = DBConn().session()
    suite = get_suite(suite_name, session)
    architecture = get_architecture(argv[0], session)
    debtype = get_override_type(argv[1], session)
    if len(argv) == 3:
        component = get_component(argv[2], session)
    else:
        component = None
    session.rollback()
    ContentsWriter(suite, architecture, debtype, component).write_file()
    session.close()

################################################################################

def scan_all(cnf, limit):
    Logger = daklog.Logger(cnf.Cnf, 'contents scan')
    result = ContentsScanner.scan_all(limit)
    processed = '%(processed)d packages processed' % result
    remaining = '%(remaining)d packages remaining' % result
    Logger.log([processed, remaining])
    Logger.close()

################################################################################

def main():
    cnf = Config()
    cnf['Contents::Options::Help'] = ''
    cnf['Contents::Options::Suite'] = ''
    cnf['Contents::Options::Limit'] = ''
    cnf['Contents::Options::Force'] = ''
    arguments = [('h', "help",  'Contents::Options::Help'),
                 ('s', "suite", 'Contents::Options::Suite', "HasArg"),
                 ('l', "limit", 'Contents::Options::Limit', "HasArg"),
                 ('f', "force", 'Contents::Options::Force'),
                ]
    args = apt_pkg.ParseCommandLine(cnf.Cnf, arguments, sys.argv)
    options = cnf.SubTree('Contents::Options')

    if (len(args) < 1) or options['Help']:
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
        write_all(cnf, suite_names, force)
        return

    if args[0] == 'generate_helper':
        write_helper(suite_names[0], args[1:])
        return

    usage()


if __name__ == '__main__':
    main()
