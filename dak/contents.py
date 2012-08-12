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
from daklib.contents import BinaryContentsScanner, ContentsWriter, \
    SourceContentsScanner
from daklib import daklog
from daklib import utils

################################################################################

def usage (exit_code=0):
    print """Usage: dak contents [options] subcommand

SUBCOMMANDS
    generate
        generate Contents-$arch.gz files

    scan-source
        scan the source packages in the existing pool and load contents into
        the src_contents table

    scan-binary
        scan the (u)debs in the existing pool and load contents into the
        bin_contents table

OPTIONS
     -h, --help
        show this help and exit

OPTIONS for generate
     -a, --archive=ARCHIVE
        only operate on suites in the specified archive

     -s, --suite={stable,testing,unstable,...}
        only operate on specified suite names

     -c, --component={main,contrib,non-free}
        only operate on specified components

     -f, --force
        write Contents files for suites marked as untouchable, too

OPTIONS for scan-source and scan-binary
     -l, --limit=NUMBER
        maximum number of packages to scan
"""
    sys.exit(exit_code)

################################################################################

def write_all(cnf, archive_names = [], suite_names = [], component_names = [], force = None):
    Logger = daklog.Logger('contents generate')
    ContentsWriter.write_all(Logger, archive_names, suite_names, component_names, force)
    Logger.close()

################################################################################

def binary_scan_all(cnf, limit):
    Logger = daklog.Logger('contents scan-binary')
    result = BinaryContentsScanner.scan_all(limit)
    processed = '%(processed)d packages processed' % result
    remaining = '%(remaining)d packages remaining' % result
    Logger.log([processed, remaining])
    Logger.close()

################################################################################

def source_scan_all(cnf, limit):
    Logger = daklog.Logger('contents scan-source')
    result = SourceContentsScanner.scan_all(limit)
    processed = '%(processed)d packages processed' % result
    remaining = '%(remaining)d packages remaining' % result
    Logger.log([processed, remaining])
    Logger.close()

################################################################################

def main():
    cnf = Config()
    cnf['Contents::Options::Help'] = ''
    cnf['Contents::Options::Suite'] = ''
    cnf['Contents::Options::Component'] = ''
    cnf['Contents::Options::Limit'] = ''
    cnf['Contents::Options::Force'] = ''
    arguments = [('h', "help",      'Contents::Options::Help'),
                 ('a', 'archive',   'Contents::Options::Archive',   'HasArg'),
                 ('s', "suite",     'Contents::Options::Suite',     "HasArg"),
                 ('c', "component", 'Contents::Options::Component', "HasArg"),
                 ('l', "limit",     'Contents::Options::Limit',     "HasArg"),
                 ('f', "force",     'Contents::Options::Force'),
                ]
    args = apt_pkg.parse_commandline(cnf.Cnf, arguments, sys.argv)
    options = cnf.subtree('Contents::Options')

    if (len(args) != 1) or options['Help']:
        usage()

    limit = None
    if len(options['Limit']) > 0:
        limit = int(options['Limit'])

    if args[0] == 'scan-source':
        source_scan_all(cnf, limit)
        return

    if args[0] == 'scan-binary':
        binary_scan_all(cnf, limit)
        return

    archive_names   = utils.split_args(options['Archive'])
    suite_names     = utils.split_args(options['Suite'])
    component_names = utils.split_args(options['Component'])

    force = bool(options['Force'])

    if args[0] == 'generate':
        write_all(cnf, archive_names, suite_names, component_names, force)
        return

    usage()


if __name__ == '__main__':
    main()
