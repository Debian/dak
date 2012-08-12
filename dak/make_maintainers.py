#!/usr/bin/env python

"""
Generate Maintainers file used by e.g. the Debian Bug Tracking System
@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
@copyright: 2011 Torsten Werner <twerner@debian.org>
@license: GNU General Public License version 2 or later

"""

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

# ``As opposed to "Linux sucks. Respect my academic authoritah, damn
#   you!" or whatever all this hot air amounts to.''
#                             -- ajt@ in _that_ thread on debian-devel@

################################################################################

from daklib import daklog
from daklib import utils
from daklib.config import Config
from daklib.dbconn import *
from daklib.regexes import re_comments

import apt_pkg
import sys

################################################################################

def usage (exit_code=0):
    print """Usage: dak make-maintainers [OPTION] -a ARCHIVE EXTRA_FILE[...]
Generate an index of packages <=> Maintainers / Uploaders.

  -a, --archive=ARCHIVE      archive to take packages from
  -h, --help                 show this help and exit
"""
    sys.exit(exit_code)

################################################################################

def format(package, person):
    '''Return a string nicely formatted for writing to the output file.'''
    return '%-20s %s\n' % (package, person)

################################################################################

def uploader_list(source):
    '''Return a sorted list of uploader names for source package.'''
    return sorted([uploader.name for uploader in source.uploaders])

################################################################################

def main():
    cnf = Config()

    Arguments = [('h',"help","Make-Maintainers::Options::Help"),
                 ('a','archive','Make-Maintainers::Options::Archive','HasArg')]
    if not cnf.has_key("Make-Maintainers::Options::Help"):
        cnf["Make-Maintainers::Options::Help"] = ""

    extra_files = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Make-Maintainers::Options")

    if Options["Help"] or not Options.get('Archive'):
        usage()

    Logger = daklog.Logger('make-maintainers')
    session = DBConn().session()

    archive = session.query(Archive).filter_by(archive_name=Options['Archive']).one()

    # dictionary packages to maintainer names
    maintainers = dict()
    # dictionary packages to list of uploader names
    uploaders = dict()

    source_query = session.query(DBSource).from_statement('''
        select distinct on (source.source) source.* from source
            join src_associations sa on source.id = sa.source
            join suite on sa.suite = suite.id
            where suite.archive_id = :archive_id
            order by source.source, source.version desc''') \
        .params(archive_id=archive.archive_id)

    binary_query = session.query(DBBinary).from_statement('''
        select distinct on (binaries.package) binaries.* from binaries
            join bin_associations ba on binaries.id = ba.bin
            join suite on ba.suite = suite.id
            where suite.archive_id = :archive_id
            order by binaries.package, binaries.version desc''') \
        .params(archive_id=archive.archive_id)

    Logger.log(['sources'])
    for source in source_query:
        maintainers[source.source] = source.maintainer.name
        uploaders[source.source] = uploader_list(source)

    Logger.log(['binaries'])
    for binary in binary_query:
        if binary.package not in maintainers:
            maintainers[binary.package] = binary.maintainer.name
            uploaders[binary.package] = uploader_list(binary.source)

    Logger.log(['files'])
    # Process any additional Maintainer files (e.g. from pseudo
    # packages)
    for filename in extra_files:
        extrafile = utils.open_file(filename)
        for line in extrafile.readlines():
            line = re_comments.sub('', line).strip()
            if line == "":
                continue
            (package, maintainer) = line.split(None, 1)
            maintainers[package] = maintainer
            uploaders[package] = [maintainer]

    maintainer_file = open('Maintainers', 'w')
    uploader_file = open('Uploaders', 'w')
    for package in sorted(uploaders):
        maintainer_file.write(format(package, maintainers[package]))
        for uploader in uploaders[package]:
            uploader_file.write(format(package, uploader))
    uploader_file.close()
    maintainer_file.close()
    Logger.close()

################################################################################

if __name__ == '__main__':
    main()
