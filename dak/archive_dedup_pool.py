#!/usr/bin/env python
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
import os
import stat
import sys

from daklib.dbconn import DBConn
from daklib import daklog
from daklib.config import Config

Options = None
Logger = None

################################################################################
################################################################################
################################################################################

def usage (exit_code=0):
    print """Usage: dak archive-dedup-pool [OPTION]...
  -h, --help                show this help and exit.
  -V, --version             display the version number and exit
"""
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
        SELECT DISTINCT ON (id) filenames, size
            FROM (
                SELECT
                    f1.id,
                    f1.size,
                    array_agg(av.path || '/pool/' || c.name || '/' || f2.filename) OVER (PARTITION BY f1.id, a1.archive_id ORDER by f2.created) AS filenames
                    FROM
                        files AS f1 INNER JOIN
                        files_archive_map AS a1 ON f1.id = a1.file_id INNER JOIN
                        files AS f2 ON f1.size = f2.size AND f1.sha256sum = f2.sha256sum INNER JOIN
                        files_archive_map AS a2 ON f2.id = a2.file_id INNER JOIN
                        component c ON a2.component_id = c.id INNER JOIN
                        archive av ON a1.archive_id = a2.archive_id AND a2.archive_id = av.id
            ) AS f
            WHERE array_length(filenames, 1) > 1
            ORDER BY id, array_length(filenames, 1) DESC
    ) AS f
    ORDER by filenames;
    """)

    for i in results:
        dedup_one(i['size'], *i['filenames'])

################################################################################

def main():
    global Options, Logger

    cnf = Config()
    session = DBConn().session()

    Arguments = [('h',"help","Archive-Dedup-Pool::Options::Help")]

    apt_pkg.parse_commandline(cnf.Cnf,Arguments,sys.argv)

    for i in ["help"]:
        if not cnf.has_key("Archive-Dedup-Pool::Options::%s" % (i)):
            cnf["Archive-Dedup-Pool::Options::%s" % (i)] = ""

    Options = cnf.subtree("Archive-Dedup-Pool::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger("archive-dedup-pool")

    dedup(session)

    Logger.close()

################################################################################

if __name__ == '__main__':
    main()
