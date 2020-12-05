#! /usr/bin/env python3
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
import os
import sys

from daklib.config import Config
from daklib.dbconn import *
from daklib.fstransactions import FilesystemTransaction


def usage():
    print("""Usage: dak export-suite -s <suite> [options]

Export binaries and sources from a suite to a flat directory structure.

 -c --copy         copy files instead of symlinking them
 -d <directory>    target directory to export packages to
                   default: current directory
 -r --relative     use symlinks relative to target directory
 -s <suite>        suite to grab uploads from
""")


def main(argv=None):
    if argv is None:
        argv = sys.argv

    arguments = [('h', 'help', 'Export::Options::Help'),
                 ('c', 'copy', 'Export::Options::Copy'),
                 ('d', 'directory', 'Export::Options::Directory', 'HasArg'),
                 ('r', 'relative', 'Export::Options::Relative'),
                 ('s', 'suite', 'Export::Options::Suite', 'HasArg')]

    cnf = Config()
    apt_pkg.parse_commandline(cnf.Cnf, arguments, argv)
    options = cnf.subtree('Export::Options')

    if 'Help' in options or 'Suite' not in options:
        usage()
        sys.exit(0)

    session = DBConn().session()

    suite = session.query(Suite).filter_by(suite_name=options['Suite']).first()
    if suite is None:
        print("Unknown suite '{0}'".format(options['Suite']))
        sys.exit(1)

    directory = options.get('Directory')
    if not directory:
        print("No target directory.")
        sys.exit(1)

    symlink = 'Copy' not in options
    relative = 'Relative' in options

    if relative and not symlink:
        print("E: --relative and --copy cannot be used together.")
        sys.exit(1)

    binaries = suite.binaries
    sources = suite.sources

    files = []
    files.extend([b.poolfile for b in binaries])
    for s in sources:
        files.extend([ds.poolfile for ds in s.srcfiles])

    with FilesystemTransaction() as fs:
        for f in files:
            af = session.query(ArchiveFile) \
                        .join(ArchiveFile.component).join(ArchiveFile.file) \
                        .filter(ArchiveFile.archive == suite.archive) \
                        .filter(ArchiveFile.file == f).first()
            src = af.path
            if relative:
                src = os.path.relpath(src, directory)
            dst = os.path.join(directory, f.basename)
            if not os.path.exists(dst):
                fs.copy(src, dst, symlink=symlink)
        fs.commit()


if __name__ == '__main__':
    main()
