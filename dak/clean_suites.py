#!/usr/bin/env python

""" Cleans up unassociated binary and source packages """
# Copyright (C) 2000, 2001, 2002, 2003, 2006  James Troup <james@nocrew.org>

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

import os, stat, sys, time
import apt_pkg
from datetime import datetime, timedelta

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils

################################################################################

Options = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak clean-suites [OPTIONS]
Clean old packages from suites.

  -n, --no-action            don't do anything
  -h, --help                 show this help and exit
  -m, --maximum              maximum number of files to remove"""
    sys.exit(exit_code)

################################################################################

def check_binaries(now_date, delete_date, max_delete, session):
    print "Checking for orphaned binary packages..."

    # Get the list of binary packages not in a suite and mark them for
    # deletion.

    # TODO: This can be a single SQL UPDATE statement
    q = session.execute("""
SELECT b.file FROM binaries b, files f
 WHERE f.last_used IS NULL AND b.file = f.id
   AND NOT EXISTS (SELECT 1 FROM bin_associations ba WHERE ba.bin = b.id)""")

    for i in q.fetchall():
        session.execute("UPDATE files SET last_used = :lastused WHERE id = :fileid AND last_used IS NULL",
                        {'lastused': now_date, 'fileid': i[0]})
    session.commit()

    # Check for any binaries which are marked for eventual deletion
    # but are now used again.

    # TODO: This can be a single SQL UPDATE statement
    q = session.execute("""
SELECT b.file FROM binaries b, files f
   WHERE f.last_used IS NOT NULL AND f.id = b.file
    AND EXISTS (SELECT 1 FROM bin_associations ba WHERE ba.bin = b.id)""")

    for i in q.fetchall():
        session.execute("UPDATE files SET last_used = NULL WHERE id = :fileid", {'fileid': i[0]})
    session.commit()

########################################

def check_sources(now_date, delete_date, max_delete, session):
    print "Checking for orphaned source packages..."

    # Get the list of source packages not in a suite and not used by
    # any binaries.
    q = session.execute("""
SELECT s.id, s.file FROM source s, files f
  WHERE f.last_used IS NULL AND s.file = f.id
    AND NOT EXISTS (SELECT 1 FROM src_associations sa WHERE sa.source = s.id)
    AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.source = s.id)""")

    #### XXX: this should ignore cases where the files for the binary b
    ####      have been marked for deletion (so the delay between bins go
    ####      byebye and sources go byebye is 0 instead of StayOfExecution)

    for i in q.fetchall():
        source_id = i[0]
        dsc_file_id = i[1]

        # Mark the .dsc file for deletion
        session.execute("""UPDATE files SET last_used = :last_used
                                    WHERE id = :dscfileid AND last_used IS NULL""",
                        {'last_used': now_date, 'dscfileid': dsc_file_id})

        # Mark all other files references by .dsc too if they're not used by anyone else
        x = session.execute("""SELECT f.id FROM files f, dsc_files d
                              WHERE d.source = :sourceid AND d.file = f.id""",
                             {'sourceid': source_id})
        for j in x.fetchall():
            file_id = j[0]
            y = session.execute("SELECT id FROM dsc_files d WHERE d.file = :fileid", {'fileid': file_id})
            if len(y.fetchall()) == 1:
                session.execute("""UPDATE files SET last_used = :lastused
                                  WHERE id = :fileid AND last_used IS NULL""",
                                {'lastused': now_date, 'fileid': file_id})

    session.commit()

    # Check for any sources which are marked for deletion but which
    # are now used again.

    q = session.execute("""
SELECT f.id FROM source s, files f, dsc_files df
  WHERE f.last_used IS NOT NULL AND s.id = df.source AND df.file = f.id
    AND ((EXISTS (SELECT 1 FROM src_associations sa WHERE sa.source = s.id))
      OR (EXISTS (SELECT 1 FROM binaries b WHERE b.source = s.id)))""")

    #### XXX: this should also handle deleted binaries specially (ie, not
    ####      reinstate sources because of them

    # Could be done in SQL; but left this way for hysterical raisins
    # [and freedom to innovate don'cha know?]
    for i in q.fetchall():
        session.execute("UPDATE files SET last_used = NULL WHERE id = :fileid",
                        {'fileid': i[0]})

    session.commit()

########################################

def check_files(now_date, delete_date, max_delete, session):
    # FIXME: this is evil; nothing should ever be in this state.  if
    # they are, it's a bug and the files should not be auto-deleted.
    # XXX: In that case, remove the stupid return to later and actually
    #      *TELL* us rather than silently ignore it - mhy

    print "Checking for unused files..."
    q = session.execute("""
SELECT id, filename FROM files f
  WHERE NOT EXISTS (SELECT 1 FROM binaries b WHERE b.file = f.id)
    AND NOT EXISTS (SELECT 1 FROM dsc_files df WHERE df.file = f.id)
    ORDER BY filename""")

    ql = q.fetchall()
    if len(ql) > 0:
        print "WARNING: check_files found something it shouldn't"
        for x in ql:
            print x

    # NOW return, the code below is left as an example of what was
    # evidently done at some point in the past
    return

#    for i in q.fetchall():
#        file_id = i[0]
#        session.execute("UPDATE files SET last_used = :lastused WHERE id = :fileid",
#                        {'lastused': now_date, 'fileid': file_id})
#
#    session.commit()

def clean_binaries(now_date, delete_date, max_delete, session):
    # We do this here so that the binaries we remove will have their
    # source also removed (if possible).

    # XXX: why doesn't this remove the files here as well? I don't think it
    #      buys anything keeping this separate
    print "Cleaning binaries from the DB..."
    if not Options["No-Action"]:
        print "Deleting from binaries table... "
        session.execute("""DELETE FROM binaries WHERE EXISTS
                              (SELECT 1 FROM files WHERE binaries.file = files.id
                                         AND files.last_used <= :deldate)""",
                           {'deldate': delete_date})

########################################

def clean(now_date, delete_date, max_delete, session):
    cnf = Config()

    count = 0
    size = 0

    print "Cleaning out packages..."

    cur_date = now_date.strftime("%Y-%m-%d")
    dest = os.path.join(cnf["Dir::Morgue"], cnf["Clean-Suites::MorgueSubDir"], cur_date)
    if not os.path.exists(dest):
        os.mkdir(dest)

    # Delete from source
    if not Options["No-Action"]:
        print "Deleting from source table... "
        session.execute("""DELETE FROM dsc_files
                            WHERE EXISTS
                               (SELECT 1 FROM source s, files f, dsc_files df
                                 WHERE f.last_used <= :deletedate
                                   AND s.file = f.id AND s.id = df.source
                                   AND df.id = dsc_files.id)""", {'deletedate': delete_date})
        session.execute("""DELETE FROM source
                            WHERE EXISTS
                               (SELECT 1 FROM files
                                 WHERE source.file = files.id
                                   AND files.last_used <= :deletedate)""", {'deletedate': delete_date})

        session.commit()

    # Delete files from the pool
    query = """SELECT l.path, f.filename FROM location l, files f
              WHERE f.last_used <= :deletedate AND l.id = f.location"""
    if max_delete is not None:
        query += " LIMIT %d" % max_delete
        print "Limiting removals to %d" % max_delete

    q = session.execute(query, {'deletedate': delete_date})
    for i in q.fetchall():
        filename = i[0] + i[1]
        if not os.path.exists(filename):
            utils.warn("can not find '%s'." % (filename))
            continue
        if os.path.isfile(filename):
            if os.path.islink(filename):
                count += 1
                if Options["No-Action"]:
                    print "Removing symlink %s..." % (filename)
                else:
                    os.unlink(filename)
            else:
                size += os.stat(filename)[stat.ST_SIZE]
                count += 1

                dest_filename = dest + '/' + os.path.basename(filename)
                # If the destination file exists; try to find another filename to use
                if os.path.exists(dest_filename):
                    dest_filename = utils.find_next_free(dest_filename)

                if Options["No-Action"]:
                    print "Cleaning %s -> %s ..." % (filename, dest_filename)
                else:
                    utils.move(filename, dest_filename)
        else:
            utils.fubar("%s is neither symlink nor file?!" % (filename))

    # Delete from the 'files' table
    # XXX: I've a horrible feeling that the max_delete stuff breaks here - mhy
    # TODO: Change it so we do the DELETEs as we go; it'll be slower but
    #       more reliable
    if not Options["No-Action"]:
        print "Deleting from files table... "
        session.execute("DELETE FROM files WHERE last_used <= :deletedate", {'deletedate': delete_date})
        session.commit()

    if count > 0:
        print "Cleaned %d files, %s." % (count, utils.size_type(size))

################################################################################

def clean_maintainers(now_date, delete_date, max_delete, session):
    print "Cleaning out unused Maintainer entries..."

    # TODO Replace this whole thing with one SQL statement
    q = session.execute("""
SELECT m.id FROM maintainer m
  WHERE NOT EXISTS (SELECT 1 FROM binaries b WHERE b.maintainer = m.id)
    AND NOT EXISTS (SELECT 1 FROM source s WHERE s.maintainer = m.id OR s.changedby = m.id)
    AND NOT EXISTS (SELECT 1 FROM src_uploaders u WHERE u.maintainer = m.id)""")

    count = 0

    for i in q.fetchall():
        maintainer_id = i[0]
        if not Options["No-Action"]:
            session.execute("DELETE FROM maintainer WHERE id = :maint", {'maint': maintainer_id})
            count += 1

    if not Options["No-Action"]:
        session.commit()

    if count > 0:
        print "Cleared out %d maintainer entries." % (count)

################################################################################

def clean_fingerprints(now_date, delete_date, max_delete, session):
    print "Cleaning out unused fingerprint entries..."

    # TODO Replace this whole thing with one SQL statement
    q = session.execute("""
SELECT f.id FROM fingerprint f
  WHERE f.keyring IS NULL
    AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.sig_fpr = f.id)
    AND NOT EXISTS (SELECT 1 FROM source s WHERE s.sig_fpr = f.id)""")

    count = 0

    for i in q.fetchall():
        fingerprint_id = i[0]
        if not Options["No-Action"]:
            session.execute("DELETE FROM fingerprint WHERE id = :fpr", {'fpr': fingerprint_id})
            count += 1

    if not Options["No-Action"]:
        session.commit()

    if count > 0:
        print "Cleared out %d fingerprint entries." % (count)

################################################################################

def clean_queue_build(now_date, delete_date, max_delete, session):

    cnf = Config()

    if not cnf.ValueList("Dinstall::QueueBuildSuites") or Options["No-Action"]:
        return

    print "Cleaning out queue build symlinks..."

    our_delete_date = now_date - timedelta(seconds = int(cnf["Clean-Suites::QueueBuildStayOfExecution"]))
    count = 0

    q = session.execute("SELECT filename FROM queue_build WHERE last_used <= :deletedate",
                        {'deletedate': our_delete_date})
    for i in q.fetchall():
        filename = i[0]
        if not os.path.exists(filename):
            utils.warn("%s (from queue_build) doesn't exist." % (filename))
            continue

        if not cnf.FindB("Dinstall::SecurityQueueBuild") and not os.path.islink(filename):
            utils.fubar("%s (from queue_build) should be a symlink but isn't." % (filename))

        os.unlink(filename)
        count += 1

    session.execute("DELETE FROM queue_build WHERE last_used <= :deletedate",
                    {'deletedate': our_delete_date})

    session.commit()

    if count:
        print "Cleaned %d queue_build files." % (count)

################################################################################

def main():
    global Options

    cnf = Config()

    for i in ["Help", "No-Action", "Maximum" ]:
        if not cnf.has_key("Clean-Suites::Options::%s" % (i)):
            cnf["Clean-Suites::Options::%s" % (i)] = ""

    Arguments = [('h',"help","Clean-Suites::Options::Help"),
                 ('n',"no-action","Clean-Suites::Options::No-Action"),
                 ('m',"maximum","Clean-Suites::Options::Maximum", "HasArg")]

    apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Clean-Suites::Options")

    if cnf["Clean-Suites::Options::Maximum"] != "":
        try:
            # Only use Maximum if it's an integer
            max_delete = int(cnf["Clean-Suites::Options::Maximum"])
            if max_delete < 1:
                utils.fubar("If given, Maximum must be at least 1")
        except ValueError, e:
            utils.fubar("If given, Maximum must be an integer")
    else:
        max_delete = None

    if Options["Help"]:
        usage()

    session = DBConn().session()

    now_date = datetime.now()
    delete_date = now_date - timedelta(seconds=int(cnf['Clean-Suites::StayOfExecution']))

    check_binaries(now_date, delete_date, max_delete, session)
    clean_binaries(now_date, delete_date, max_delete, session)
    check_sources(now_date, delete_date, max_delete, session)
    check_files(now_date, delete_date, max_delete, session)
    clean(now_date, delete_date, max_delete, session)
    clean_maintainers(now_date, delete_date, max_delete, session)
    clean_fingerprints(now_date, delete_date, max_delete, session)
    clean_queue_build(now_date, delete_date, max_delete, session)

################################################################################

if __name__ == '__main__':
    main()
