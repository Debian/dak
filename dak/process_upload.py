#!/usr/bin/env python

"""
Checks Debian packages from Incoming
@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
@copyright: 2009  Frank Lichtenheld <djpig@debian.org>
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

# based on process-unchecked and process-accepted

## pu|pa: locking (daily.lock)
## pu|pa: parse arguments -> list of changes files
## pa: initialize urgency log
## pu|pa: sort changes list

## foreach changes:
###  pa: load dak file
##   pu: copy CHG to tempdir
##   pu: check CHG signature
##   pu: parse changes file
##   pu: checks:
##     pu: check distribution (mappings, rejects)
##     pu: copy FILES to tempdir
##     pu: check whether CHG already exists in CopyChanges
##     pu: check whether FILES already exist in one of the policy queues
##     for deb in FILES:
##       pu: extract control information
##       pu: various checks on control information
##       pu|pa: search for source (in CHG, projectb, policy queues)
##       pu|pa: check whether "Version" fulfills target suite requirements/suite propagation
##       pu|pa: check whether deb already exists in the pool
##     for src in FILES:
##       pu: various checks on filenames and CHG consistency
##       pu: if isdsc: check signature
##     for file in FILES:
##       pu: various checks
##       pu: NEW?
##       //pu: check whether file already exists in the pool
##       pu: store what "Component" the package is currently in
##     pu: check whether we found everything we were looking for in CHG
##     pu: check the DSC:
##       pu: check whether we need and have ONE DSC
##       pu: parse the DSC
##       pu: various checks //maybe drop some of the in favor of lintian
##       pu|pa: check whether "Version" fulfills target suite requirements/suite propagation
##       pu: check whether DSC_FILES is consistent with "Format"
##       for src in DSC_FILES:
##         pu|pa: check whether file already exists in the pool (with special handling for .orig.tar.gz)
##     pu: create new tempdir
##     pu: create symlink mirror of source
##     pu: unpack source
##     pu: extract changelog information for BTS
##     //pu: create missing .orig symlink
##     pu: check with lintian
##     for file in FILES:
##       pu: check checksums and sizes
##     for file in DSC_FILES:
##       pu: check checksums and sizes
##     pu: CHG: check urgency
##     for deb in FILES:
##       pu: extract contents list and check for dubious timestamps
##     pu: check that the uploader is actually allowed to upload the package
###  pa: install:
###    if stable_install:
###      pa: remove from p-u
###      pa: add to stable
###      pa: move CHG to morgue
###      pa: append data to ChangeLog
###      pa: send mail
###      pa: remove .dak file
###    else:
###      pa: add dsc to db:
###        for file in DSC_FILES:
###          pa: add file to file
###          pa: add file to dsc_files
###        pa: create source entry
###        pa: update source associations
###        pa: update src_uploaders
###      for deb in FILES:
###        pa: add deb to db:
###          pa: add file to file
###          pa: find source entry
###          pa: create binaries entry
###          pa: update binary associations
###      pa: .orig component move
###      pa: move files to pool
###      pa: save CHG
###      pa: move CHG to done/
###      pa: change entry in queue_build
##   pu: use dispatch table to choose target queue:
##     if NEW:
##       pu: write .dak file
##       pu: move to NEW
##       pu: send mail
##     elsif AUTOBYHAND:
##       pu: run autobyhand script
##       pu: if stuff left, do byhand or accept
##     elsif targetqueue in (oldstable, stable, embargo, unembargo):
##       pu: write .dak file
##       pu: check overrides
##       pu: move to queue
##       pu: send mail
##     else:
##       pu: write .dak file
##       pu: move to ACCEPTED
##       pu: send mails
##       pu: create files for BTS
##       pu: create entry in queue_build
##       pu: check overrides
import errno
import fcntl
import os
import sys
#from datetime import datetime
import apt_pkg

from daklib import daklog
from daklib.queue import *
from daklib import utils
from daklib.dbconn import *
#from daklib.dak_exceptions import *
#from daklib.regexes import re_default_answer, re_issource, re_fdnic
from daklib.urgencylog import UrgencyLog
from daklib.summarystats import SummaryStats
from daklib.holding import Holding
from daklib.config import Config

###############################################################################

Options = None
Logger = None

###############################################################################

def usage (exit_code=0):
    print """Usage: dak process-upload [OPTION]... [CHANGES]...
  -a, --automatic           automatic run
  -h, --help                show this help and exit.
  -n, --no-action           don't do anything
  -p, --no-lock             don't check lockfile !! for cron.daily only !!
  -s, --no-mail             don't send any mail
  -V, --version             display the version number and exit"""
    sys.exit(exit_code)

###############################################################################

def process_it(changes_file):
    global Logger

    cnf = Config()

    holding = Holding()

    u = Upload()
    u.pkg.changes_file = changes_file
    u.pkg.directory = os.getcwd()
    u.logger = Logger
    origchanges = os.path.join(u.pkg.directory, u.pkg.changes_file)

    # Some defaults in case we can't fully process the .changes file
    u.pkg.changes["maintainer2047"] = cnf["Dinstall::MyEmailAddress"]
    u.pkg.changes["changedby2047"] = cnf["Dinstall::MyEmailAddress"]

    # debian-{devel-,}-changes@lists.debian.org toggles writes access based on this header
    bcc = "X-DAK: dak process-unchecked"
    if cnf.has_key("Dinstall::Bcc"):
        u.Subst["__BCC__"] = bcc + "\nBcc: %s" % (cnf["Dinstall::Bcc"])
    else:
        u.Subst["__BCC__"] = bcc

    # Remember where we are so we can come back after cd-ing into the
    # holding directory.  TODO: Fix this stupid hack
    u.prevdir = os.getcwd()

    # TODO: Figure out something better for this (or whether it's even
    #       necessary - it seems to have been for use when we were
    #       still doing the is_unchecked check; reprocess = 2)
    u.reprocess = 1

    try:
        # If this is the Real Thing(tm), copy things into a private
        # holding directory first to avoid replacable file races.
        if not Options["No-Action"]:
            os.chdir(cnf["Dir::Queue::Holding"])

            # Absolutize the filename to avoid the requirement of being in the
            # same directory as the .changes file.
            holding.copy_to_holding(origchanges)

            # Relativize the filename so we use the copy in holding
            # rather than the original...
            changespath = os.path.basename(u.pkg.changes_file)

        (u.pkg.changes["fingerprint"], rejects) = utils.check_signature(changespath)

        if u.pkg.changes["fingerprint"]:
            valid_changes_p = u.load_changes(changespath)
        else:
            valid_changes_p = False
            u.rejects.extend(rejects)

        if valid_changes_p:
            while u.reprocess:
                u.check_distributions()
                u.check_files(not Options["No-Action"])
                valid_dsc_p = u.check_dsc(not Options["No-Action"])
                if valid_dsc_p and not Options["No-Action"]:
                    u.check_source()
                    u.check_lintian()
                u.check_hashes()
                u.check_urgency()
                u.check_timestamps()
                u.check_signed_by_key()

        action(u)

    except (SystemExit, KeyboardInterrupt):
        raise

    except:
        print "ERROR"
        traceback.print_exc(file=sys.stderr)

    # Restore previous WD
    os.chdir(u.prevdir)

###############################################################################

def main():
    global Options, Logger

    cnf = Config()
    summarystats = SummaryStats()
    log_urgency = False

    DBConn()

    Arguments = [('a',"automatic","Dinstall::Options::Automatic"),
                 ('h',"help","Dinstall::Options::Help"),
                 ('n',"no-action","Dinstall::Options::No-Action"),
                 ('p',"no-lock", "Dinstall::Options::No-Lock"),
                 ('s',"no-mail", "Dinstall::Options::No-Mail"),
                 ('d',"directory", "Dinstall::Options::Directory", "HasArg")]

    for i in ["automatic", "help", "no-action", "no-lock", "no-mail",
              "version", "directory"]:
        if not cnf.has_key("Dinstall::Options::%s" % (i)):
            cnf["Dinstall::Options::%s" % (i)] = ""

    changes_files = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Dinstall::Options")

    if Options["Help"]:
        usage()

    # -n/--dry-run invalidates some other options which would involve things happening
    if Options["No-Action"]:
        Options["Automatic"] = ""

    # Check that we aren't going to clash with the daily cron job
    if not Options["No-Action"] and os.path.exists("%s/daily.lock" % (cnf["Dir::Lock"])) and not Options["No-Lock"]:
        utils.fubar("Archive maintenance in progress.  Try again later.")

    # Obtain lock if not in no-action mode and initialize the log
    if not Options["No-Action"]:
        lock_fd = os.open(cnf["Dinstall::LockFile"], os.O_RDWR | os.O_CREAT)
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError, e:
            if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EAGAIN':
                utils.fubar("Couldn't obtain lock; assuming another 'dak process-upload' is already running.")
            else:
                raise
        if cnf.get("Dir::UrgencyLog"):
            # Initialise UrgencyLog()
            log_urgency = True
            UrgencyLog()

    Logger = daklog.Logger(cnf, "process-upload", Options["No-Action"])

    # If we have a directory flag, use it to find our files
    if cnf["Dinstall::Options::Directory"] != "":
        # Note that we clobber the list of files we were given in this case
        # so warn if the user has done both
        if len(changes_files) > 0:
            utils.warn("Directory provided so ignoring files given on command line")

        changes_files = utils.get_changes_files(cnf["Dinstall::Options::Directory"])
        Logger.log(["Using changes files from directory", cnf["Dinstall::Options::Directory"], len(changes_files)])
    elif not len(changes_files) > 0:
        utils.fubar("No changes files given and no directory specified")
    else:
        Logger.log(["Using changes files from command-line", len(changes_files)])

    # Sort the .changes files so that we process sourceful ones first
    changes_files.sort(utils.changes_compare)

    # Process the changes files
    for changes_file in changes_files:
        print "\n" + changes_file
        session = DBConn().session()
        process_it(changes_file)
        session.close()

    if summarystats.accept_count:
        sets = "set"
        if summarystats.accept_count > 1:
            sets = "sets"
        sys.stderr.write("Installed %d package %s, %s.\n" % (summarystats.accept_count, sets,
                                                             utils.size_type(int(summarystats.accept_bytes))))
        Logger.log(["total", summarystats.accept_count, summarystats.accept_bytes])

    if not Options["No-Action"]:
        if log_urgency:
            UrgencyLog().close()
    Logger.close()

###############################################################################

if __name__ == '__main__':
    main()
