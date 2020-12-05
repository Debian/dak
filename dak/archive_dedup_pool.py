#! /usr/bin/env python3
# vim:set et ts=4 sw=4:

""" De-duplicates files in the pool directory

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2017 Bastian Blank <waldi@debian.org>
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

import apt_pkg
import errno
import os
import sys

from daklib.dbconn import DBConn
from daklib import daklog
from daklib.config import Config

Options = None
Logger = None

################################################################################
################################################################################
################################################################################


def usage(exit_code=0):
    print("""Usage: dak archive-dedup-pool [OPTION]...
  -h, --help                show this help and exit.
  -V, --version             display the version number and exit
""")
    sys.exit(exit_code)

################################################################################


def dedup_one(size, reference, *filenames):
    stat_reference = os.stat(reference)

    # safety net
    if stat_reference.st_size != size:
        raise RuntimeError('Size of {} does not match database: {} != {}'.format(
            reference, size, stat_reference.st_size))

    for filename in filenames:
        stat_filename = os.stat(filename)

        # if file is already a hard-linked, ignore
        if stat_reference == stat_filename:
            continue

        # safety net
        if stat_filename.st_size != size:
            raise RuntimeError('Size of {} does not match database: {} != {}'.format(
                filename, size, stat_filename.st_size))

        tempfile = filename + '.new'
        os.link(reference, tempfile)
        try:
            Logger.log(["deduplicate", filename, reference])
            os.rename(tempfile, filename)
        finally:
            try:
                os.unlink(tempfile)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise

################################################################################


def dedup(session):
    results = session.execute("""
SELECT DISTINCT *
    FROM (
        SELECT
            f.size,
            array_agg(a.path || '/pool/' || c.name || '/' || f.filename) OVER (
                -- we aggregate all files with the same size, sha256sum and archive
                PARTITION BY f.size, f.sha256sum, a.id
                -- the oldest should be first
                ORDER by f.created
                -- we always want to see all rows
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            )
            AS filenames
            FROM
                files AS f INNER JOIN
                files_archive_map AS fa ON f.id = fa.file_id INNER JOIN
                component c ON fa.component_id = c.id INNER JOIN
                archive a ON fa.archive_id = a.id
    ) AS f
    -- we only care about entries with more than one filename
    WHERE array_length(filenames, 1) > 1
    """)

    for i in results:
        dedup_one(i['size'], *i['filenames'])

################################################################################


def main():
    global Options, Logger

    cnf = Config()
    session = DBConn().session()

    Arguments = [('h', "help", "Archive-Dedup-Pool::Options::Help")]

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    for i in ["help"]:
        key = "Archive-Dedup-Pool::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    Options = cnf.subtree("Archive-Dedup-Pool::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger("archive-dedup-pool")

    dedup(session)

    Logger.close()

################################################################################


if __name__ == '__main__':
    main()
