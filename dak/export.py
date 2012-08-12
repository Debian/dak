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
import sys

from daklib.config import Config
from daklib.dbconn import *
from daklib.policy import UploadCopy

def usage():
    print """Usage: dak export -q <queue> [options] -a|--all|<source...>

Export uploads from policy queues, that is the changes files for the given
source package and all other files associated with that.

 -a --all          export all uploads
 -c --copy         copy files instead of symlinking them
 -d <directory>    target directory to export packages to
                   default: current directory
 -q <queue>        queue to grab uploads from
 <source>          source package name to export
"""

def main(argv=None):
    if argv is None:
        argv = sys.argv

    arguments = [('h', 'help', 'Export::Options::Help'),
                 ('a', 'all', 'Export::Options::All'),
                 ('c', 'copy', 'Export::Options::Copy'),
                 ('d', 'directory', 'Export::Options::Directory', 'HasArg'),
                 ('q', 'queue', 'Export::Options::Queue', 'HasArg')]

    cnf = Config()
    source_names = apt_pkg.parse_commandline(cnf.Cnf, arguments, argv)
    options = cnf.subtree('Export::Options')

    if 'Help' in options or 'Queue' not in options:
        usage()
        sys.exit(0)

    session = DBConn().session()

    queue = session.query(PolicyQueue).filter_by(queue_name=options['Queue']).first()
    if queue is None:
        print "Unknown queue '{0}'".format(options['Queue'])
        sys.exit(1)
    uploads = session.query(PolicyQueueUpload).filter_by(policy_queue=queue)
    if 'All' not in options:
        uploads = uploads.filter(DBChange.source.in_(source_names))
    directory = options.get('Directory', '.')
    symlink = 'Copy' not in options

    for u in uploads:
        UploadCopy(u).export(directory, symlink=symlink, ignore_existing=True)

if __name__ == '__main__':
    main()
