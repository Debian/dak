#!/usr/bin/env python

""" Cleans up unassociated binary and source packages

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
@copyright: 2010  Joerg Jaspert <joerg@debian.org>
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

# 07:05|<elmo> well.. *shrug*.. no, probably not.. but to fix it,
#      |       we're going to have to implement reference counting
#      |       through dependencies.. do we really want to go down
#      |       that road?
#
# 07:05|<Culus> elmo: Augh! <brain jumps out of skull>

################################################################################

import os
import stat
import sys
import time
import apt_pkg
from datetime import datetime, timedelta

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils
from daklib import daklog

################################################################################

Options = None
Logger = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak clean-suites [OPTIONS]
Clean old packages from suites.

  -n, --no-action            don't do anything
  -h, --help                 show this help and exit
  -m, --maximum              maximum number of files to remove"""
    sys.exit(exit_code)

################################################################################

def check_binaries(now_date, session):
    Logger.log(["Checking for orphaned binary packages..."])

    # Get the list of binary packages not in a suite and mark them for
    # deletion.
    # Check for any binaries which are marked for eventual deletion
    # but are now used again.

    query = """
       WITH usage AS (
         SELECT
           af.archive_id AS archive_id,
           af.file_id AS file_id,
           af.component_id AS component_id,
           BOOL_OR(EXISTS (SELECT 1 FROM bin_associations ba
                            JOIN suite s ON ba.suite = s.id
                           WHERE ba.bin = b.id
                             AND s.archive_id = af.archive_id))
             AS in_use
         FROM files_archive_map af
         JOIN binaries b ON af.file_id = b.file
         GROUP BY af.archive_id, af.file_id, af.component_id
       )

       UPDATE files_archive_map af
          SET last_used = CASE WHEN usage.in_use THEN NULL ELSE :last_used END
         FROM usage, files f, archive
        WHERE af.archive_id = usage.archive_id AND af.file_id = usage.file_id AND af.component_id = usage.component_id
          AND ((af.last_used IS NULL AND NOT usage.in_use) OR (af.last_used IS NOT NULL AND usage.in_use))
          AND af.file_id = f.id
          AND af.archive_id = archive.id
       RETURNING archive.name, f.filename, af.last_used IS NULL"""

    res = session.execute(query, {'last_used': now_date})
    for i in res:
        op = "set lastused"
        if i[2]:
            op = "unset lastused"
        Logger.log([op, i[0], i[1]])

########################################

def check_sources(now_date, session):
    Logger.log(["Checking for orphaned source packages..."])

    # Get the list of source packages not in a suite and not used by
    # any binaries.

    # Check for any sources which are marked for deletion but which
    # are now used again.

    # TODO: the UPDATE part is the same as in check_binaries. Merge?

    query = """
    WITH usage AS (
      SELECT
        af.archive_id AS archive_id,
        af.file_id AS file_id,
        af.component_id AS component_id,
        BOOL_OR(EXISTS (SELECT 1 FROM src_associations sa
                         JOIN suite s ON sa.suite = s.id
                        WHERE sa.source = df.source
                          AND s.archive_id = af.archive_id)
          OR EXISTS (SELECT 1 FROM files_archive_map af_bin
                              JOIN binaries b ON af_bin.file_id = b.file
                             WHERE b.source = df.source
                               AND af_bin.archive_id = af.archive_id
                               AND (af_bin.last_used IS NULL OR af_bin.last_used > ad.delete_date))
          OR EXISTS (SELECT 1 FROM extra_src_references esr
                         JOIN bin_associations ba ON esr.bin_id = ba.bin
                         JOIN binaries b ON ba.bin = b.id
                         JOIN suite s ON ba.suite = s.id
                        WHERE esr.src_id = df.source
                          AND s.archive_id = af.archive_id))
          AS in_use
      FROM files_archive_map af
      JOIN dsc_files df ON af.file_id = df.file
      JOIN archive_delete_date ad ON af.archive_id = ad.archive_id
      GROUP BY af.archive_id, af.file_id, af.component_id
    )

    UPDATE files_archive_map af
       SET last_used = CASE WHEN usage.in_use THEN NULL ELSE :last_used END
      FROM usage, files f, archive
     WHERE af.archive_id = usage.archive_id AND af.file_id = usage.file_id AND af.component_id = usage.component_id
       AND ((af.last_used IS NULL AND NOT usage.in_use) OR (af.last_used IS NOT NULL AND usage.in_use))
       AND af.file_id = f.id
       AND af.archive_id = archive.id

    RETURNING archive.name, f.filename, af.last_used IS NULL
    """

    res = session.execute(query, {'last_used': now_date})
    for i in res:
        op = "set lastused"
        if i[2]:
            op = "unset lastused"
        Logger.log([op, i[0], i[1]])

########################################

def check_files(now_date, session):
    # FIXME: this is evil; nothing should ever be in this state.  if
    # they are, it's a bug.

    # However, we've discovered it happens sometimes so we print a huge warning
    # and then mark the file for deletion.  This probably masks a bug somwhere
    # else but is better than collecting cruft forever

    Logger.log(["Checking for unused files..."])
    q = session.execute("""
    UPDATE files_archive_map af
       SET last_used = :last_used
      FROM files f, archive
     WHERE af.file_id = f.id
       AND af.archive_id = archive.id
       AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.file = af.file_id)
       AND NOT EXISTS (SELECT 1 FROM dsc_files df WHERE df.file = af.file_id)
       AND af.last_used IS NULL
    RETURNING archive.name, f.filename""", {'last_used': now_date})

    for x in q:
        utils.warn("orphaned file: {0}".format(x))
        Logger.log(["set lastused", x[0], x[1], "ORPHANED FILE"])

    if not Options["No-Action"]:
        session.commit()

def clean_binaries(now_date, session):
    # We do this here so that the binaries we remove will have their
    # source also removed (if possible).

    # XXX: why doesn't this remove the files here as well? I don't think it
    #      buys anything keeping this separate

    Logger.log(["Deleting from binaries table... "])
    q = session.execute("""
      DELETE FROM binaries b
       USING files f
       WHERE f.id = b.file
         AND NOT EXISTS (SELECT 1 FROM files_archive_map af
                                  JOIN archive_delete_date ad ON af.archive_id = ad.archive_id
                                 WHERE af.file_id = b.file
                                   AND (af.last_used IS NULL OR af.last_used > ad.delete_date))
      RETURNING f.filename
    """)
    for b in q:
        Logger.log(["delete binary", b[0]])

########################################

def clean(now_date, archives, max_delete, session):
    cnf = Config()

    count = 0
    size = 0

    Logger.log(["Cleaning out packages..."])

    morguedir = cnf.get("Dir::Morgue", os.path.join("Dir::Pool", 'morgue'))
    morguesubdir = cnf.get("Clean-Suites::MorgueSubDir", 'pool')

    # Build directory as morguedir/morguesubdir/year/month/day
    dest = os.path.join(morguedir,
                        morguesubdir,
                        str(now_date.year),
                        '%.2d' % now_date.month,
                        '%.2d' % now_date.day)

    if not Options["No-Action"] and not os.path.exists(dest):
        os.makedirs(dest)

    # Delete from source
    Logger.log(["Deleting from source table..."])
    q = session.execute("""
      WITH
      deleted_sources AS (
        DELETE FROM source
         USING files f
         WHERE source.file = f.id
           AND NOT EXISTS (SELECT 1 FROM files_archive_map af
                                    JOIN archive_delete_date ad ON af.archive_id = ad.archive_id
                                   WHERE af.file_id = source.file
                                     AND (af.last_used IS NULL OR af.last_used > ad.delete_date))
        RETURNING source.id AS id, f.filename AS filename
      ),
      deleted_dsc_files AS (
        DELETE FROM dsc_files df WHERE df.source IN (SELECT id FROM deleted_sources)
        RETURNING df.file AS file_id
      ),
      now_unused_source_files AS (
        UPDATE files_archive_map af
           SET last_used = '1977-03-13 13:37:42' -- Kill it now. We waited long enough before removing the .dsc.
         WHERE af.file_id IN (SELECT file_id FROM deleted_dsc_files)
           AND NOT EXISTS (SELECT 1 FROM dsc_files df WHERE df.file = af.file_id)
      )
      SELECT filename FROM deleted_sources""")
    for s in q:
        Logger.log(["delete source", s[0]])

    if not Options["No-Action"]:
        session.commit()

    # Delete files from the pool
    old_files = session.query(ArchiveFile).filter('files_archive_map.last_used <= (SELECT delete_date FROM archive_delete_date ad WHERE ad.archive_id = files_archive_map.archive_id)').join(Archive)
    if max_delete is not None:
        old_files = old_files.limit(max_delete)
        Logger.log(["Limiting removals to %d" % max_delete])

    if archives is not None:
        archive_ids = [ a.archive_id for a in archives ]
        old_files = old_files.filter(ArchiveFile.archive_id.in_(archive_ids))

    for af in old_files:
        filename = af.path
        if not os.path.exists(filename):
            Logger.log(["database referred to non-existing file", af.path])
            session.delete(af)
            continue
        Logger.log(["delete archive file", filename])
        if os.path.isfile(filename):
            if os.path.islink(filename):
                count += 1
                Logger.log(["delete symlink", filename])
                if not Options["No-Action"]:
                    os.unlink(filename)
            else:
                size += os.stat(filename)[stat.ST_SIZE]
                count += 1

                dest_filename = dest + '/' + os.path.basename(filename)
                # If the destination file exists; try to find another filename to use
                if os.path.lexists(dest_filename):
                    dest_filename = utils.find_next_free(dest_filename)

                if not Options["No-Action"]:
                    if af.archive.use_morgue:
                        Logger.log(["move to morgue", filename, dest_filename])
                        utils.move(filename, dest_filename)
                    else:
                        Logger.log(["removed file", filename])
                        os.unlink(filename)

            if not Options["No-Action"]:
                session.delete(af)
                session.commit()

        else:
            utils.fubar("%s is neither symlink nor file?!" % (filename))

    if count > 0:
        Logger.log(["total", count, utils.size_type(size)])

    # Delete entries in files no longer referenced by any archive
    query = """
       DELETE FROM files f
        WHERE NOT EXISTS (SELECT 1 FROM files_archive_map af WHERE af.file_id = f.id)
    """
    session.execute(query)

    if not Options["No-Action"]:
        session.commit()

################################################################################

def clean_maintainers(now_date, session):
    Logger.log(["Cleaning out unused Maintainer entries..."])

    # TODO Replace this whole thing with one SQL statement
    q = session.execute("""
SELECT m.id, m.name FROM maintainer m
  WHERE NOT EXISTS (SELECT 1 FROM binaries b WHERE b.maintainer = m.id)
    AND NOT EXISTS (SELECT 1 FROM source s WHERE s.maintainer = m.id OR s.changedby = m.id)
    AND NOT EXISTS (SELECT 1 FROM src_uploaders u WHERE u.maintainer = m.id)""")

    count = 0

    for i in q.fetchall():
        maintainer_id = i[0]
        Logger.log(["delete maintainer", i[1]])
        if not Options["No-Action"]:
            session.execute("DELETE FROM maintainer WHERE id = :maint", {'maint': maintainer_id})
        count += 1

    if not Options["No-Action"]:
        session.commit()

    if count > 0:
        Logger.log(["total", count])

################################################################################

def clean_fingerprints(now_date, session):
    Logger.log(["Cleaning out unused fingerprint entries..."])

    # TODO Replace this whole thing with one SQL statement
    q = session.execute("""
SELECT f.id, f.fingerprint FROM fingerprint f
  WHERE f.keyring IS NULL
    AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.sig_fpr = f.id)
    AND NOT EXISTS (SELECT 1 FROM source s WHERE s.sig_fpr = f.id)
    AND NOT EXISTS (SELECT 1 FROM acl_per_source aps WHERE aps.created_by_id = f.id)""")

    count = 0

    for i in q.fetchall():
        fingerprint_id = i[0]
        Logger.log(["delete fingerprint", i[1]])
        if not Options["No-Action"]:
            session.execute("DELETE FROM fingerprint WHERE id = :fpr", {'fpr': fingerprint_id})
        count += 1

    if not Options["No-Action"]:
        session.commit()

    if count > 0:
        Logger.log(["total", count])

################################################################################

def clean_empty_directories(session):
    """
    Removes empty directories from pool directories.
    """

    Logger.log(["Cleaning out empty directories..."])

    count = 0

    cursor = session.execute(
        """SELECT DISTINCT(path) FROM archive"""
    )
    bases = [x[0] for x in cursor.fetchall()]

    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base, topdown=False):
            if not filenames and not dirnames:
                to_remove = os.path.join(base, dirpath)
                if not Options["No-Action"]:
                    Logger.log(["removing directory", to_remove])
                    os.removedirs(to_remove)
                count += 1

    if count:
        Logger.log(["total removed directories", count])

################################################################################

def set_archive_delete_dates(now_date, session):
    session.execute("""
        CREATE TEMPORARY TABLE archive_delete_date (
          archive_id INT NOT NULL,
          delete_date TIMESTAMP NOT NULL
        )""")

    session.execute("""
        INSERT INTO archive_delete_date
          (archive_id, delete_date)
        SELECT
          archive.id, :now_date - archive.stayofexecution
        FROM archive""", {'now_date': now_date})

    session.flush()

################################################################################

def main():
    global Options, Logger

    cnf = Config()

    for i in ["Help", "No-Action", "Maximum" ]:
        if not cnf.has_key("Clean-Suites::Options::%s" % (i)):
            cnf["Clean-Suites::Options::%s" % (i)] = ""

    Arguments = [('h',"help","Clean-Suites::Options::Help"),
                 ('a','archive','Clean-Suites::Options::Archive','HasArg'),
                 ('n',"no-action","Clean-Suites::Options::No-Action"),
                 ('m',"maximum","Clean-Suites::Options::Maximum", "HasArg")]

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Clean-Suites::Options")

    if cnf["Clean-Suites::Options::Maximum"] != "":
        try:
            # Only use Maximum if it's an integer
            max_delete = int(cnf["Clean-Suites::Options::Maximum"])
            if max_delete < 1:
                utils.fubar("If given, Maximum must be at least 1")
        except ValueError as e:
            utils.fubar("If given, Maximum must be an integer")
    else:
        max_delete = None

    if Options["Help"]:
        usage()

    program = "clean-suites"
    if Options['No-Action']:
        program = "clean-suites (no action)"
    Logger = daklog.Logger(program, debug=Options["No-Action"])

    session = DBConn().session()

    archives = None
    if 'Archive' in Options:
        archive_names = Options['Archive'].split(',')
        archives = session.query(Archive).filter(Archive.archive_name.in_(archive_names)).all()
        if len(archives) == 0:
            utils.fubar('Unknown archive.')

    now_date = datetime.now()

    set_archive_delete_dates(now_date, session)

    check_binaries(now_date, session)
    clean_binaries(now_date, session)
    check_sources(now_date, session)
    check_files(now_date, session)
    clean(now_date, archives, max_delete, session)
    clean_maintainers(now_date, session)
    clean_fingerprints(now_date, session)
    clean_empty_directories(session)

    session.rollback()

    Logger.close()

################################################################################

if __name__ == '__main__':
    main()
