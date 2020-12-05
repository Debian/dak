#! /usr/bin/env python3

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

from sqlalchemy.sql import text

################################################################################


def usage(exit_code=0):
    print("""Usage: dak make-maintainers [OPTION] -a ARCHIVE EXTRA_FILE[...]
Generate an index of packages <=> Maintainers / Uploaders.

  -a, --archive=ARCHIVE      archive to take packages from
  -s, --source               output source packages only
  -p, --print                print package list to stdout instead of writing it to files
  -h, --help                 show this help and exit
""")
    sys.exit(exit_code)

################################################################################


def format(package, person):
    '''Return a string nicely formatted for writing to the output file.'''
    return '%-20s %s\n' % (package, person)

################################################################################


def main():
    cnf = Config()

    Arguments = [('h', "help", "Make-Maintainers::Options::Help"),
                 ('a', "archive", "Make-Maintainers::Options::Archive", 'HasArg'),
                 ('s', "source", "Make-Maintainers::Options::Source"),
                 ('p', "print", "Make-Maintainers::Options::Print")]
    for i in ["Help", "Source", "Print"]:
        key = "Make-Maintainers::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

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

    query = session.execute(text('''
SELECT
    bs.package,
    bs.name AS maintainer,
    array_agg(mu.name) OVER (
        PARTITION BY bs.source, bs.id
        ORDER BY mu.name
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS uploaders
    FROM (
        SELECT DISTINCT ON (package)
            *
            FROM (
                SELECT
                    s.id AS source,
                    0 AS id,
                    s.source AS package,
                    s.version,
                    m.name
                    FROM
                        source AS s INNER JOIN
                        maintainer AS m ON s.maintainer = m.id INNER JOIN
                        src_associations AS sa ON s.id = sa.source INNER JOIN
                        suite on sa.suite = suite.id
                    WHERE
                        suite.archive_id = :archive_id
                UNION SELECT
                    b.source,
                    b.id,
                    b.package,
                    b.version,
                    m.name
                    FROM
                        binaries AS b INNER JOIN
                        maintainer AS m ON b.maintainer = m.id INNER JOIN
                        bin_associations AS ba ON b.id = ba.bin INNER JOIN
                        suite on ba.suite = suite.id
                    WHERE
                        NOT :source_only AND
                        suite.archive_id = :archive_id
                ) AS bs
            ORDER BY package, version desc
        ) AS bs LEFT OUTER JOIN
        -- find all uploaders for a given source
        src_uploaders AS su ON bs.source = su.source LEFT OUTER JOIN
        maintainer AS mu ON su.maintainer = mu.id
''').params(
    archive_id=archive.archive_id,
    source_only="True" if Options["Source"] else "False"
))

    Logger.log(['database'])
    for entry in query:
        maintainers[entry['package']] = entry['maintainer']
        if all(x is None for x in entry['uploaders']):
            uploaders[entry['package']] = ['']
        else:
            uploaders[entry['package']] = entry['uploaders']

    Logger.log(['files'])
    # Process any additional Maintainer files (e.g. from pseudo
    # packages)
    for filename in extra_files:
        with open(filename) as extrafile:
            for line in extrafile.readlines():
                line = re_comments.sub('', line).strip()
                if line == "":
                    continue
                (package, maintainer) = line.split(None, 1)
                maintainers[package] = maintainer
                uploaders[package] = [maintainer]

    if Options["Print"]:
        for package in sorted(maintainers):
            print(format(package, maintainers[package]), end='')
    else:
        with open('Maintainers', 'w') as maintainer_file, open('Uploaders', 'w') as uploader_file:
            for package in sorted(uploaders):
                maintainer_file.write(format(package, maintainers[package]))
                for uploader in uploaders[package]:
                    uploader_file.write(format(package, uploader))

        Logger.close()

###############################################################################


if __name__ == '__main__':
    main()
