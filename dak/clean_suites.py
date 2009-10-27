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

def check_binaries(now_date, delete_date, max_delete, session):
    print "Checking for orphaned binary packages..."

    # Get the list of binary packages not in a suite and mark them for
    # deletion.

    q = session.execute("""
SELECT b.file, f.filename FROM binaries b, files f
 WHERE f.last_used IS NULL AND b.file = f.id
   AND NOT EXISTS (SELECT 1 FROM bin_associations ba WHERE ba.bin = b.id)""")

    for i in q.fetchall():
        Logger.log(["set lastused", i[1]])
        session.execute("UPDATE files SET last_used = :lastused WHERE id = :fileid AND last_used IS NULL",
                        {'lastused': now_date, 'fileid': i[0]})
    session.commit()

    # Check for any binaries which are marked for eventual deletion
    # but are now used again.
      
    q = session.execute("""
SELECT b.file, f.filename FROM binaries b, files f
   WHERE f.last_used IS NOT NULL AND f.id = b.file
    AND EXISTS (SELECT 1 FROM bin_associations ba WHERE ba.bin = b.id)""")

    for i in q.fetchall():
        Logger.log(["unset lastused", i[1]])
        session.execute("UPDATE files SET last_used = NULL WHERE id = :fileid", {'fileid': i[0]})
    session.commit()

########################################
  
def check_sources(now_date, delete_date, max_delete, session):
    print "Checking for orphaned source packages..."

    # Get the list of source packages not in a suite and not used by
    # any binaries.
    q = session.execute("""
SELECT s.id, s.file, f.filename FROM source s, files f
  WHERE f.last_used IS NULL AND s.file = f.id
    AND NOT EXISTS (SELECT 1 FROM src_associations sa WHERE sa.source = s.id)
    AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.source = s.id)""")

    #### XXX: this should ignore cases where the files for the binary b
    ####      have been marked for deletion (so the delay between bins go
    ####      byebye and sources go byebye is 0 instead of StayOfExecution)

    for i in q.fetchall():
        source_id = i[0]
        dsc_file_id = i[1]
        dsc_fname = i[2]

        # Mark the .dsc file for deletion
        Logger.log(["set lastused", dsc_fname])
        session.execute("""UPDATE files SET last_used = :last_used
                                    WHERE id = :dscfileid AND last_used IS NULL""",
                        {'last_used': now_date, 'dscfileid': dsc_file_id})

        # Mark all other files references by .dsc too if they're not used by anyone else
        x = session.execute("""SELECT f.id, f.filename FROM files f, dsc_files d
                              WHERE d.source = :sourceid AND d.file = f.id""",
                             {'sourceid': source_id})
        for j in x.fetchall():
            file_id = j[0]
            file_name = j[1]
            y = session.execute("SELECT id FROM dsc_files d WHERE d.file = :fileid", {'fileid': file_id})
            if len(y.fetchall()) == 1:
                Logger.log(["set lastused", file_name])
                session.execute("""UPDATE files SET last_used = :lastused
                                  WHERE id = :fileid AND last_used IS NULL""",
                                {'lastused': now_date, 'fileid': file_id})

    session.commit()

    # Check for any sources which are marked for deletion but which
    # are now used again.

    q = session.execute("""
SELECT f.id, f.filename FROM source s, files f, dsc_files df
  WHERE f.last_used IS NOT NULL AND s.id = df.source AND df.file = f.id
    AND ((EXISTS (SELECT 1 FROM src_associations sa WHERE sa.source = s.id))
      OR (EXISTS (SELECT 1 FROM binaries b WHERE b.source = s.id)))""")

    #### XXX: this should also handle deleted binaries specially (ie, not
    ####      reinstate sources because of them

    for i in q.fetchall():
        Logger.log(["unset lastused", i[1]]) 
        session.execute("UPDATE files SET last_used = NULL WHERE id = :fileid",
                        {'fileid': i[0]})

    session.commit()

########################################

def check_files(now_date, delete_date, max_delete, session):
    # FIXME: this is evil; nothing should ever be in this state.  if
    # they are, it's a bug.

    # However, we've discovered it happens sometimes so we print a huge warning
    # and then mark the file for deletion.  This probably masks a bug somwhere
    # else but is better than collecting cruft forever

    print "Checking for unused files..."
    q = session.execute("""
SELECT id, filename FROM files f
  WHERE NOT EXISTS (SELECT 1 FROM binaries b WHERE b.file = f.id)
    AND NOT EXISTS (SELECT 1 FROM dsc_files df WHERE df.file = f.id)
    ORDER BY filename""")

    ql = q.fetchall()
    if len(ql) > 0:
        utils.warn("check_files found something it shouldn't")
        for x in ql:
            utils.warn("orphaned file: %s" % x)
            Logger.log(["set lastused", x[1], "ORPHANED FILE"])
            session.execute("UPDATE files SET last_used = :lastused WHERE id = :fileid",
                            {'lastused': now_date, 'fileid': x[0]})

        session.commit()

def clean_binaries(now_date, delete_date, max_delete, session):
    # We do this here so that the binaries we remove will have their
    # source also removed (if possible).

    # XXX: why doesn't this remove the files here as well? I don't think it
    #      buys anything keeping this separate
    print "Cleaning binaries from the DB..."
    print "Deleting from binaries table... "
    for bin in session.query(DBBinary).join(DBBinary.poolfile).filter(PoolFile.last_used <= delete_date):
        Logger.log(["delete binary", bin.poolfile.filename])
        if not Options["No-Action"]:
            session.delete(bin)
    if not Options["No-Action"]:
        session.commit()

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
    print "Deleting from source table... "
    q = session.execute("""
SELECT df.id, s.id, f.filename FROM source s, files f, dsc_files df
  WHERE f.last_used <= :deletedate
        AND s.file = f.id AND s.id = df.source""", {'deletedate': delete_date})
    for s in q.fetchall():
        Logger.log(["delete source", s[2]])
        if not Options["No-Action"]:
            session.execute("DELETE FROM dsc_files WHERE id = :dsc_id", {"dscid":s[0]})
            session.execute("DELETE FROM source WHERE id = :s_id", {"s_id":s[1]})

    if not Options["No-Action"]:
        session.commit()

    # Delete files from the pool
    old_files = session.query(PoolFile).filter(PoolFile.last_used <= delete_date)
    if max_delete is not None:
        old_files = old_files.limit(max_delete)
        print "Limiting removals to %d" % max_delete

    for pf in old_files:
        filename = os.path.join(pf.location.path, pf.filename)
        if not os.path.exists(filename):
            utils.warn("can not find '%s'." % (filename))
            continue
        Logger.log(["delete pool file", filename])
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
                if os.path.exists(dest_filename):
                    dest_filename = utils.find_next_free(dest_filename)

                Logger.log(["move to morgue", filename, dest_filename])
                if not Options["No-Action"]:
                    utils.move(filename, dest_filename)

            if not Options["No-Action"]:
                session.delete(pf)
            
        else:
            utils.fubar("%s is neither symlink nor file?!" % (filename))

    if not Options["No-Action"]:
        session.commit()

    if count > 0:
        print "Cleaned %d files, %s." % (count, utils.size_type(size))

################################################################################

def clean_maintainers(now_date, delete_date, max_delete, session):
    print "Cleaning out unused Maintainer entries..."

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
        print "Cleared out %d maintainer entries." % (count)

################################################################################

def clean_fingerprints(now_date, delete_date, max_delete, session):
    print "Cleaning out unused fingerprint entries..."

    # TODO Replace this whole thing with one SQL statement
    q = session.execute("""
SELECT f.id, f.fingerprint FROM fingerprint f
  WHERE f.keyring IS NULL
    AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.sig_fpr = f.id)
    AND NOT EXISTS (SELECT 1 FROM source s WHERE s.sig_fpr = f.id)""")

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
        print "Cleared out %d fingerprint entries." % (count)

################################################################################

def clean_queue_build(now_date, delete_date, max_delete, session):

    cnf = Config()

    if not cnf.ValueList("Dinstall::QueueBuildSuites") or Options["No-Action"]:
        return

    print "Cleaning out queue build symlinks..."

    our_delete_date = now_date - timedelta(seconds = int(cnf["Clean-Suites::QueueBuildStayOfExecution"]))
    count = 0

    for qf in session.query(QueueBuild).filter(QueueBuild.last_used <= our_delete_date):
        if not os.path.exists(qf.filename):
            utils.warn("%s (from queue_build) doesn't exist." % (qf.filename))
            continue

        if not cnf.FindB("Dinstall::SecurityQueueBuild") and not os.path.islink(qf.filename):
            utils.fubar("%s (from queue_build) should be a symlink but isn't." % (qf.filename))

        Logger.log(["delete queue build", qf.filename])
        if not Options["No-Action"]:
            os.unlink(qf.filename)
            session.delete(qf)
        count += 1

    if not Options["No-Action"]:
        session.commit()

    if count:
        print "Cleaned %d queue_build files." % (count)

################################################################################

def main():
    global Options, Logger

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

    Logger = daklog.Logger(cnf, "clean-suites", debug=Options["No-Action"])

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

    Logger.close()

################################################################################

if __name__ == '__main__':
    main()
