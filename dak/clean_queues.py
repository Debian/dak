#!/usr/bin/env python

""" Clean incoming of old unused files """
# Copyright (C) 2000, 2001, 2002, 2006  James Troup <james@nocrew.org>

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

# <aj> Bdale, a ham-er, and the leader,
# <aj> Willy, a GCC maintainer,
# <aj> Lamont-work, 'cause he's the top uploader....
# <aj>         Penguin Puff' save the day!
# <aj> Porting code, trying to build the world,
# <aj> Here they come just in time...
# <aj>         The Penguin Puff' Guys!
# <aj> [repeat]
# <aj> Penguin Puff'!
# <aj> willy: btw, if you don't maintain gcc you need to start, since
#      the lyrics fit really well that way

################################################################################

import os, os.path, stat, sys, time
from datetime import datetime, timedelta
import apt_pkg
from daklib import utils
from daklib import daklog
from daklib.config import Config
from daklib.dbconn import get_policy_queue

################################################################################

Options = None
Logger = None
del_dir = None
delete_date = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak clean-queues [OPTIONS]
Clean out incoming directories.

  -d, --days=DAYS            remove anything older than DAYS old
  -i, --incoming=INCOMING    the incoming directory to clean
  -n, --no-action            don't do anything
  -v, --verbose              explain what is being done
  -h, --help                 show this help and exit"""

    sys.exit(exit_code)

################################################################################

def init (cnf):
    global delete_date, del_dir

    # Used for directory naming
    now_date = datetime.now()

    # Used for working out times
    delete_date = int(time.time())-(int(Options["Days"])*84600)

    morguedir = cnf.get("Dir::Morgue", os.path.join("Dir::Pool", 'morgue'))
    morguesubdir = cnf.get("Clean-Queues::MorgueSubDir", 'queue')

    # Build directory as morguedir/morguesubdir/year/month/day
    del_dir = os.path.join(morguedir,
                           morguesubdir,
                           str(now_date.year),
                           '%.2d' % now_date.month,
                           '%.2d' % now_date.day)

    # Ensure a directory exists to remove files to
    if not Options["No-Action"]:
        if not os.path.exists(del_dir):
            os.makedirs(del_dir, 0o2775)
        if not os.path.isdir(del_dir):
            utils.fubar("%s must be a directory." % (del_dir))

    # Move to the directory to clean
    incoming = Options.get("Incoming")
    if not incoming:
        incoming = cnf.get('Dir::Unchecked')
        if not incoming:
            utils.fubar("Cannot find 'unchecked' directory")

    try:
        os.chdir(incoming)
    except OSError as e:
        utils.fubar("Cannot chdir to %s" % incoming)

# Remove a file to the morgue
def remove (from_dir, f):
    fname = os.path.basename(f)
    if os.access(f, os.R_OK):
        Logger.log(["move file to morgue", from_dir, fname, del_dir])
        if Options["Verbose"]:
            print "Removing '%s' (to '%s')."  % (fname, del_dir)
        if Options["No-Action"]:
            return

        dest_filename = os.path.join(del_dir, fname)
        # If the destination file exists; try to find another filename to use
        if os.path.exists(dest_filename):
            dest_filename = utils.find_next_free(dest_filename, 10)
            Logger.log(["change destination file name", os.path.basename(dest_filename)])
        utils.move(f, dest_filename, 0o660)
    else:
        Logger.log(["skipping file because of permission problem", fname])
        utils.warn("skipping '%s', permission denied." % fname)

# Removes any old files.
# [Used for Incoming/REJECT]
#
def flush_old ():
    Logger.log(["check Incoming/REJECT for old files", os.getcwd()])
    for f in os.listdir('.'):
        if os.path.isfile(f):
            if os.stat(f)[stat.ST_MTIME] < delete_date:
                remove('Incoming/REJECT', f)
            else:
                if Options["Verbose"]:
                    print "Skipping, too new, '%s'." % (os.path.basename(f))

# Removes any files which are old orphans (not associated with a valid .changes file).
# [Used for Incoming]
#
def flush_orphans ():
    all_files = {}
    changes_files = []

    Logger.log(["check Incoming for old orphaned files", os.getcwd()])
    # Build up the list of all files in the directory
    for i in os.listdir('.'):
        if os.path.isfile(i):
            all_files[i] = 1
            if i.endswith(".changes"):
                changes_files.append(i)

    # Proces all .changes and .dsc files.
    for changes_filename in changes_files:
        try:
            changes = utils.parse_changes(changes_filename)
            files = utils.build_file_list(changes)
        except:
            utils.warn("error processing '%s'; skipping it. [Got %s]" % (changes_filename, sys.exc_info()[0]))
            continue

        dsc_files = {}
        for f in files.keys():
            if f.endswith(".dsc"):
                try:
                    dsc = utils.parse_changes(f, dsc_file=1)
                    dsc_files = utils.build_file_list(dsc, is_a_dsc=1)
                except:
                    utils.warn("error processing '%s'; skipping it. [Got %s]" % (f, sys.exc_info()[0]))
                    continue

        # Ensure all the files we've seen aren't deleted
        keys = []
        for i in (files.keys(), dsc_files.keys(), [changes_filename]):
            keys.extend(i)
        for key in keys:
            if all_files.has_key(key):
                if Options["Verbose"]:
                    print "Skipping, has parents, '%s'." % (key)
                del all_files[key]

    # Anthing left at this stage is not referenced by a .changes (or
    # a .dsc) and should be deleted if old enough.
    for f in all_files.keys():
        if os.stat(f)[stat.ST_MTIME] < delete_date:
            remove('Incoming', f)
        else:
            if Options["Verbose"]:
                print "Skipping, too new, '%s'." % (os.path.basename(f))

################################################################################

def main ():
    global Options, Logger

    cnf = Config()

    for i in ["Help", "Incoming", "No-Action", "Verbose" ]:
        if not cnf.has_key("Clean-Queues::Options::%s" % (i)):
            cnf["Clean-Queues::Options::%s" % (i)] = ""
    if not cnf.has_key("Clean-Queues::Options::Days"):
        cnf["Clean-Queues::Options::Days"] = "14"

    Arguments = [('h',"help","Clean-Queues::Options::Help"),
                 ('d',"days","Clean-Queues::Options::Days", "IntLevel"),
                 ('i',"incoming","Clean-Queues::Options::Incoming", "HasArg"),
                 ('n',"no-action","Clean-Queues::Options::No-Action"),
                 ('v',"verbose","Clean-Queues::Options::Verbose")]

    apt_pkg.parse_commandline(cnf.Cnf,Arguments,sys.argv)
    Options = cnf.subtree("Clean-Queues::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger('clean-queues', Options['No-Action'])

    init(cnf)

    if Options["Verbose"]:
        print "Processing incoming..."
    flush_orphans()

    reject = cnf["Dir::Reject"]
    if os.path.exists(reject) and os.path.isdir(reject):
        if Options["Verbose"]:
            print "Processing reject directory..."
        os.chdir(reject)
        flush_old()

    Logger.close()

#######################################################################################

if __name__ == '__main__':
    main()
