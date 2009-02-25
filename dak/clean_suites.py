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

import os, pg, stat, sys, time
import apt_pkg
from daklib import utils

################################################################################

projectB = None
Cnf = None
Options = None
now_date = None;     # mark newly "deleted" things as deleted "now"
delete_date = None;  # delete things marked "deleted" earler than this
max_delete = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak clean-suites [OPTIONS]
Clean old packages from suites.

  -n, --no-action            don't do anything
  -h, --help                 show this help and exit
  -m, --maximum              maximum number of files to remove"""
    sys.exit(exit_code)

################################################################################

def check_binaries():
    global delete_date, now_date

    print "Checking for orphaned binary packages..."

    # Get the list of binary packages not in a suite and mark them for
    # deletion.
    q = projectB.query("""
SELECT b.file FROM binaries b, files f
 WHERE f.last_used IS NULL AND b.file = f.id
   AND NOT EXISTS (SELECT 1 FROM bin_associations ba WHERE ba.bin = b.id)""")
    ql = q.getresult()

    projectB.query("BEGIN WORK")
    for i in ql:
        file_id = i[0]
        projectB.query("UPDATE files SET last_used = '%s' WHERE id = %s AND last_used IS NULL" % (now_date, file_id))
    projectB.query("COMMIT WORK")

    # Check for any binaries which are marked for eventual deletion
    # but are now used again.
    q = projectB.query("""
SELECT b.file FROM binaries b, files f
   WHERE f.last_used IS NOT NULL AND f.id = b.file
    AND EXISTS (SELECT 1 FROM bin_associations ba WHERE ba.bin = b.id)""")
    ql = q.getresult()

    projectB.query("BEGIN WORK")
    for i in ql:
        file_id = i[0]
        projectB.query("UPDATE files SET last_used = NULL WHERE id = %s" % (file_id))
    projectB.query("COMMIT WORK")

########################################

def check_sources():
    global delete_date, now_date

    print "Checking for orphaned source packages..."

    # Get the list of source packages not in a suite and not used by
    # any binaries.
    q = projectB.query("""
SELECT s.id, s.file FROM source s, files f
  WHERE f.last_used IS NULL AND s.file = f.id
    AND NOT EXISTS (SELECT 1 FROM src_associations sa WHERE sa.source = s.id)
    AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.source = s.id)""")

    #### XXX: this should ignore cases where the files for the binary b
    ####      have been marked for deletion (so the delay between bins go
    ####      byebye and sources go byebye is 0 instead of StayOfExecution)

    ql = q.getresult()

    projectB.query("BEGIN WORK")
    for i in ql:
        source_id = i[0]
        dsc_file_id = i[1]

        # Mark the .dsc file for deletion
        projectB.query("UPDATE files SET last_used = '%s' WHERE id = %s AND last_used IS NULL" % (now_date, dsc_file_id))
        # Mark all other files references by .dsc too if they're not used by anyone else
        x = projectB.query("SELECT f.id FROM files f, dsc_files d WHERE d.source = %s AND d.file = f.id" % (source_id))
        for j in x.getresult():
            file_id = j[0]
            y = projectB.query("SELECT id FROM dsc_files d WHERE d.file = %s" % (file_id))
            if len(y.getresult()) == 1:
                projectB.query("UPDATE files SET last_used = '%s' WHERE id = %s AND last_used IS NULL" % (now_date, file_id))
    projectB.query("COMMIT WORK")

    # Check for any sources which are marked for deletion but which
    # are now used again.

    q = projectB.query("""
SELECT f.id FROM source s, files f, dsc_files df
  WHERE f.last_used IS NOT NULL AND s.id = df.source AND df.file = f.id
    AND ((EXISTS (SELECT 1 FROM src_associations sa WHERE sa.source = s.id))
      OR (EXISTS (SELECT 1 FROM binaries b WHERE b.source = s.id)))""")

    #### XXX: this should also handle deleted binaries specially (ie, not
    ####      reinstate sources because of them

    ql = q.getresult()
    # Could be done in SQL; but left this way for hysterical raisins
    # [and freedom to innovate don'cha know?]
    projectB.query("BEGIN WORK")
    for i in ql:
        file_id = i[0]
        projectB.query("UPDATE files SET last_used = NULL WHERE id = %s" % (file_id))
    projectB.query("COMMIT WORK")

########################################

def check_files():
    global delete_date, now_date

    # FIXME: this is evil; nothing should ever be in this state.  if
    # they are, it's a bug and the files should not be auto-deleted.

    return

    print "Checking for unused files..."
    q = projectB.query("""
SELECT id FROM files f
  WHERE NOT EXISTS (SELECT 1 FROM binaries b WHERE b.file = f.id)
    AND NOT EXISTS (SELECT 1 FROM dsc_files df WHERE df.file = f.id)""")

    projectB.query("BEGIN WORK")
    for i in q.getresult():
        file_id = i[0]
        projectB.query("UPDATE files SET last_used = '%s' WHERE id = %s" % (now_date, file_id))
    projectB.query("COMMIT WORK")

def clean_binaries():
    global delete_date, now_date

    # We do this here so that the binaries we remove will have their
    # source also removed (if possible).

    # XXX: why doesn't this remove the files here as well? I don't think it
    #      buys anything keeping this separate
    print "Cleaning binaries from the DB..."
    if not Options["No-Action"]:
        before = time.time()
        sys.stdout.write("[Deleting from binaries table... ")
        projectB.query("DELETE FROM binaries WHERE EXISTS (SELECT 1 FROM files WHERE binaries.file = files.id AND files.last_used <= '%s')" % (delete_date))
        sys.stdout.write("done. (%d seconds)]\n" % (int(time.time()-before)))

########################################

def clean():
    global delete_date, now_date, max_delete
    count = 0
    size = 0

    print "Cleaning out packages..."

    date = time.strftime("%Y-%m-%d")
    dest = Cnf["Dir::Morgue"] + '/' + Cnf["Clean-Suites::MorgueSubDir"] + '/' + date
    if not os.path.exists(dest):
        os.mkdir(dest)

    # Delete from source
    if not Options["No-Action"]:
        before = time.time()
        sys.stdout.write("[Deleting from source table... ")
        projectB.query("DELETE FROM dsc_files WHERE EXISTS (SELECT 1 FROM source s, files f, dsc_files df WHERE f.last_used <= '%s' AND s.file = f.id AND s.id = df.source AND df.id = dsc_files.id)" % (delete_date))
        projectB.query("DELETE FROM src_uploaders WHERE EXISTS (SELECT 1 FROM source s, files f WHERE f.last_used <= '%s' AND s.file = f.id AND s.id = src_uploaders.source)" % (delete_date))
        projectB.query("DELETE FROM source WHERE EXISTS (SELECT 1 FROM files WHERE source.file = files.id AND files.last_used <= '%s')" % (delete_date))
        sys.stdout.write("done. (%d seconds)]\n" % (int(time.time()-before)))

    # Delete files from the pool
    query = "SELECT l.path, f.filename FROM location l, files f WHERE f.last_used <= '%s' AND l.id = f.location" % (delete_date)
    if max_delete is not None:
        query += " LIMIT %d" % maximum
        sys.stdout.write("Limiting removals to %d" % Cnf["Clean-Suites::Options::Maximum"])

    q=projectB.query(query)
    for i in q.getresult():
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
    if not Options["No-Action"]:
        before = time.time()
        sys.stdout.write("[Deleting from files table... ")
        projectB.query("DELETE FROM files WHERE last_used <= '%s'" % (delete_date))
        sys.stdout.write("done. (%d seconds)]\n" % (int(time.time()-before)))
    if count > 0:
        sys.stderr.write("Cleaned %d files, %s.\n" % (count, utils.size_type(size)))

################################################################################

def clean_maintainers():
    print "Cleaning out unused Maintainer entries..."

    q = projectB.query("""
SELECT m.id FROM maintainer m
  WHERE NOT EXISTS (SELECT 1 FROM binaries b WHERE b.maintainer = m.id)
    AND NOT EXISTS (SELECT 1 FROM source s WHERE s.maintainer = m.id OR s.changedby = m.id)
    AND NOT EXISTS (SELECT 1 FROM src_uploaders u WHERE u.maintainer = m.id)""")
    ql = q.getresult()

    count = 0
    projectB.query("BEGIN WORK")
    for i in ql:
        maintainer_id = i[0]
        if not Options["No-Action"]:
            projectB.query("DELETE FROM maintainer WHERE id = %s" % (maintainer_id))
            count += 1
    projectB.query("COMMIT WORK")

    if count > 0:
        sys.stderr.write("Cleared out %d maintainer entries.\n" % (count))

################################################################################

def clean_fingerprints():
    print "Cleaning out unused fingerprint entries..."

    q = projectB.query("""
SELECT f.id FROM fingerprint f
  WHERE f.keyring IS NULL
    AND NOT EXISTS (SELECT 1 FROM binaries b WHERE b.sig_fpr = f.id)
    AND NOT EXISTS (SELECT 1 FROM source s WHERE s.sig_fpr = f.id)""")
    ql = q.getresult()

    count = 0
    projectB.query("BEGIN WORK")
    for i in ql:
        fingerprint_id = i[0]
        if not Options["No-Action"]:
            projectB.query("DELETE FROM fingerprint WHERE id = %s" % (fingerprint_id))
            count += 1
    projectB.query("COMMIT WORK")

    if count > 0:
        sys.stderr.write("Cleared out %d fingerprint entries.\n" % (count))

################################################################################

def clean_queue_build():
    global now_date

    if not Cnf.ValueList("Dinstall::QueueBuildSuites") or Options["No-Action"]:
        return

    print "Cleaning out queue build symlinks..."

    our_delete_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time()-int(Cnf["Clean-Suites::QueueBuildStayOfExecution"])))
    count = 0

    q = projectB.query("SELECT filename FROM queue_build WHERE last_used <= '%s'" % (our_delete_date))
    for i in q.getresult():
        filename = i[0]
        if not os.path.exists(filename):
            utils.warn("%s (from queue_build) doesn't exist." % (filename))
            continue
        if not Cnf.FindB("Dinstall::SecurityQueueBuild") and not os.path.islink(filename):
            utils.fubar("%s (from queue_build) should be a symlink but isn't." % (filename))
        os.unlink(filename)
        count += 1
    projectB.query("DELETE FROM queue_build WHERE last_used <= '%s'" % (our_delete_date))

    if count:
        sys.stderr.write("Cleaned %d queue_build files.\n" % (count))

################################################################################

def main():
    global Cnf, Options, projectB, delete_date, now_date, max_delete

    Cnf = utils.get_conf()
    for i in ["Help", "No-Action", "Maximum" ]:
        if not Cnf.has_key("Clean-Suites::Options::%s" % (i)):
            Cnf["Clean-Suites::Options::%s" % (i)] = ""

    Arguments = [('h',"help","Clean-Suites::Options::Help"),
                 ('n',"no-action","Clean-Suites::Options::No-Action"),
                 ('m',"maximum","Clean-Suites::Options::Maximum", "HasArg")]

    apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Clean-Suites::Options")

    if Cnf["Clean-Suites::Options::Maximum"] != "":
        try:
            # Only use Maximum if it's an integer
            max_delete = int(Cnf["Clean-Suites::Options::Maximum"])
            if max_delete < 1:
                utils.fubar("If given, Maximum must be at least 1")
        except ValueError, e:
            utils.fubar("If given, Maximum must be an integer")
    else:
        max_delete = None

    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))

    now_date = time.strftime("%Y-%m-%d %H:%M")
    delete_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time()-int(Cnf["Clean-Suites::StayOfExecution"])))

    check_binaries()
    clean_binaries()
    check_sources()
    check_files()
    clean()
    clean_maintainers()
    clean_fingerprints()
    clean_queue_build()

################################################################################

if __name__ == '__main__':
    main()
