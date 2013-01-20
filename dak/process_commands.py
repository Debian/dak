#! /usr/bin/env python
#
# Copyright (C) 2012, Ansgar Burchardt <ansgar@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import apt_pkg
import datetime
import os
import sys
import time

from daklib.config import Config
from daklib.command import CommandError, CommandFile
from daklib.daklog import Logger
from daklib.fstransactions import FilesystemTransaction
from daklib.gpg import GpgException
from daklib.utils import find_next_free

def usage():
    print """Usage: dak process-commands [-d <directory>] [<command-file>...]

process command files
"""

def main(argv=None):
    if argv is None:
        argv = sys.argv

    arguments = [('h', 'help', 'Process-Commands::Options::Help'),
                 ('d', 'directory', 'Process-Commands::Options::Directory', 'HasArg')]

    cnf = Config()
    cnf['Process-Commands::Options::Dummy'] = ''
    filenames = apt_pkg.parse_commandline(cnf.Cnf, arguments, argv)
    options = cnf.subtree('Process-Commands::Options')

    if 'Help' in options or (len(filenames) == 0 and 'Directory' not in options):
        usage()
        sys.exit(0)

    log = Logger('command')

    now = datetime.datetime.now()
    donedir = os.path.join(cnf['Dir::Done'], now.strftime('%Y/%m/%d'))
    rejectdir = cnf['Dir::Reject']

    if len(filenames) == 0:
        filenames = [ fn for fn in os.listdir(options['Directory']) if fn.endswith('.dak-commands') ]

    for fn in filenames:
        basename = os.path.basename(fn)
        if not fn.endswith('.dak-commands'):
            log.log(['unexpected filename', basename])
            continue

        with open(fn, 'r') as fh:
            data = fh.read()

        try:
            command = CommandFile(basename, data, log)
            command.evaluate()
        except:
            created = os.stat(fn).st_mtime
            now = time.time()
            too_new = (now - created < int(cnf.get('Dinstall::SkipTime', '60')))
            if too_new:
                log.log(['skipped (too new)'])
                continue
            log.log(['reject', basename])
            dst = find_next_free(os.path.join(rejectdir, basename))
        else:
            log.log(['done', basename])
            dst = find_next_free(os.path.join(donedir, basename))

        with FilesystemTransaction() as fs:
            fs.unlink(fn)
            fs.create(dst, mode=0o644).write(data)
            fs.commit()

    log.close()

if __name__ == '__main__':
    main()
