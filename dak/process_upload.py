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

# Integrity checks
## GPG
## Parsing changes (check for duplicates)
## Parse dsc
## file list checks

# New check layout (TODO: Implement)
## Permission checks
### suite mappings
### ACLs
### version checks (suite)
### override checks

## Source checks
### copy orig
### unpack
### BTS changelog
### src contents
### lintian
### urgency log

## Binary checks
### timestamps
### control checks
### src relation check
### contents

## Database insertion (? copy from stuff)
### BYHAND / NEW / Policy queues
### Pool

## Queue builds

import datetime
import errno
from errno import EACCES, EAGAIN
import fcntl
import os
import sys
import traceback
import apt_pkg
import time
from sqlalchemy.orm.exc import NoResultFound

from daklib import daklog
from daklib.dbconn import *
from daklib.urgencylog import UrgencyLog
from daklib.summarystats import SummaryStats
from daklib.config import Config
import daklib.utils as utils
from daklib.regexes import *

import daklib.announce
import daklib.archive
import daklib.checks
import daklib.upload

###############################################################################

Options = None
Logger = None

###############################################################################

def usage (exit_code=0):
    print """Usage: dak process-upload [OPTION]... [CHANGES]...
  -a, --automatic           automatic run
  -d, --directory <DIR>     process uploads in <DIR>
  -h, --help                show this help and exit.
  -n, --no-action           don't do anything
  -p, --no-lock             don't check lockfile !! for cron.daily only !!
  -s, --no-mail             don't send any mail
  -V, --version             display the version number and exit"""
    sys.exit(exit_code)

###############################################################################

def try_or_reject(function):
    """Try to call function or reject the upload if that fails
    """
    def wrapper(directory, upload, *args, **kwargs):
        reason = 'No exception caught. This should not happen.'

        try:
            return function(directory, upload, *args, **kwargs)
        except (daklib.archive.ArchiveException, daklib.checks.Reject) as e:
            reason = unicode(e)
        except Exception as e:
            reason = "There was an uncaught exception when processing your upload:\n{0}\nAny original reject reason follows below.".format(traceback.format_exc())

        try:
            upload.rollback()
            return real_reject(directory, upload, reason=reason)
        except Exception as e:
            reason = "In addition there was an exception when rejecting the package:\n{0}\nPrevious reasons:\n{1}".format(traceback.format_exc(), reason)
            upload.rollback()
            return real_reject(directory, upload, reason=reason, notify=False)

        raise Exception('Rejecting upload failed after multiple tries. Giving up. Last reason:\n{0}'.format(reason))

    return wrapper

def get_processed_upload(upload):
    changes = upload.changes
    control = upload.changes.changes

    pu = daklib.announce.ProcessedUpload()

    pu.maintainer = control.get('Maintainer')
    pu.changed_by = control.get('Changed-By')
    pu.fingerprint = changes.primary_fingerprint

    pu.suites = upload.final_suites or []
    pu.from_policy_suites = []

    pu.changes = open(upload.changes.path, 'r').read()
    pu.changes_filename = upload.changes.filename
    pu.sourceful = upload.changes.sourceful
    pu.source = control.get('Source')
    pu.version = control.get('Version')
    pu.architecture = control.get('Architecture')
    pu.bugs = changes.closed_bugs

    pu.program = "process-upload"

    pu.warnings = upload.warnings

    return pu

@try_or_reject
def accept(directory, upload):
    cnf = Config()

    Logger.log(['ACCEPT', upload.changes.filename])
    print "ACCEPT"

    upload.install()

    accepted_to_real_suite = False
    for suite in upload.final_suites:
        accepted_to_real_suite = accepted_to_real_suite or suite.policy_queue is None

    sourceful_upload = 'source' in upload.changes.architectures

    control = upload.changes.changes
    if sourceful_upload and not Options['No-Action']:
        urgency = control.get('Urgency')
        if urgency not in cnf.value_list('Urgency::Valid'):
            urgency = cnf['Urgency::Default']
        UrgencyLog().log(control['Source'], control['Version'], urgency)

    pu = get_processed_upload(upload)
    daklib.announce.announce_accept(pu)

    # Move .changes to done, but only for uploads that were accepted to a
    # real suite.  process-policy will handle this for uploads to queues.
    if accepted_to_real_suite:
        src = os.path.join(upload.directory, upload.changes.filename)

        now = datetime.datetime.now()
        donedir = os.path.join(cnf['Dir::Done'], now.strftime('%Y/%m/%d'))
        dst = os.path.join(donedir, upload.changes.filename)
        dst = utils.find_next_free(dst)

        upload.transaction.fs.copy(src, dst, mode=0o644)

    SummaryStats().accept_count += 1
    SummaryStats().accept_bytes += upload.changes.bytes

@try_or_reject
def accept_to_new(directory, upload):
    cnf = Config()

    Logger.log(['ACCEPT-TO-NEW', upload.changes.filename])
    print "ACCEPT-TO-NEW"

    upload.install_to_new()
    # TODO: tag bugs pending

    pu = get_processed_upload(upload)
    daklib.announce.announce_new(pu)

    SummaryStats().accept_count += 1
    SummaryStats().accept_bytes += upload.changes.bytes

@try_or_reject
def reject(directory, upload, reason=None, notify=True):
    real_reject(directory, upload, reason, notify)

def real_reject(directory, upload, reason=None, notify=True):
    # XXX: rejection itself should go to daklib.archive.ArchiveUpload
    cnf = Config()

    Logger.log(['REJECT', upload.changes.filename])
    print "REJECT"

    fs = upload.transaction.fs
    rejectdir = cnf['Dir::Reject']

    files = [ f.filename for f in upload.changes.files.itervalues() ]
    files.append(upload.changes.filename)

    for fn in files:
        src = os.path.join(upload.directory, fn)
        dst = utils.find_next_free(os.path.join(rejectdir, fn))
        if not os.path.exists(src):
            continue
        fs.copy(src, dst)

    if upload.reject_reasons is not None:
        if reason is None:
            reason = ''
        reason = reason + '\n' + '\n'.join(upload.reject_reasons)

    if reason is None:
        reason = '(Unknown reason. Please check logs.)'

    dst = utils.find_next_free(os.path.join(rejectdir, '{0}.reason'.format(upload.changes.filename)))
    fh = fs.create(dst)
    fh.write(reason)
    fh.close()

    if notify:
        pu = get_processed_upload(upload)
        daklib.announce.announce_reject(pu, reason)

    SummaryStats().reject_count += 1

###############################################################################

def action(directory, upload):
    changes = upload.changes
    processed = True

    global Logger

    cnf = Config()

    okay = upload.check()

    summary = changes.changes.get('Changes', '')

    package_info = []
    if okay:
        if changes.source is not None:
            package_info.append("source:{0}".format(changes.source.dsc['Source']))
        for binary in changes.binaries:
            package_info.append("binary:{0}".format(binary.control['Package']))

    (prompt, answer) = ("", "XXX")
    if Options["No-Action"] or Options["Automatic"]:
        answer = 'S'

    queuekey = ''

    print summary
    print
    print "\n".join(package_info)
    print
    if len(upload.warnings) > 0:
        print "\n".join(upload.warnings)
        print

    if len(upload.reject_reasons) > 0:
        print "Reason:"
        print "\n".join(upload.reject_reasons)
        print

        path = os.path.join(directory, changes.filename)
        created = os.stat(path).st_mtime
        now = time.time()
        too_new = (now - created < int(cnf['Dinstall::SkipTime']))

        if too_new:
            print "SKIP (too new)"
            prompt = "[S]kip, Quit ?"
        else:
            prompt = "[R]eject, Skip, Quit ?"
            if Options["Automatic"]:
                answer = 'R'
    elif upload.new:
        prompt = "[N]ew, Skip, Quit ?"
        if Options['Automatic']:
            answer = 'N'
    else:
        prompt = "[A]ccept, Skip, Quit ?"
        if Options['Automatic']:
            answer = 'A'

    while prompt.find(answer) == -1:
        answer = utils.our_raw_input(prompt)
        m = re_default_answer.match(prompt)
        if answer == "":
            answer = m.group(1)
        answer = answer[:1].upper()

    if answer == 'R':
        reject(directory, upload)
    elif answer == 'A':
        # upload.try_autobyhand must not be run with No-Action.
        if Options['No-Action']:
            accept(directory, upload)
        elif upload.try_autobyhand():
            accept(directory, upload)
        else:
            print "W: redirecting to BYHAND as automatic processing failed."
            accept_to_new(directory, upload)
    elif answer == 'N':
        accept_to_new(directory, upload)
    elif answer == 'Q':
        sys.exit(0)
    elif answer == 'S':
        processed = False

    if not Options['No-Action']:
        upload.commit()

    return processed

###############################################################################

def unlink_if_exists(path):
    try:
        os.unlink(path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise

def process_it(directory, changes, keyrings, session):
    global Logger

    print "\n{0}\n".format(changes.filename)
    Logger.log(["Processing changes file", changes.filename])

    with daklib.archive.ArchiveUpload(directory, changes, keyrings) as upload:
        processed = action(directory, upload)
        if processed and not Options['No-Action']:
            unlink_if_exists(os.path.join(directory, changes.filename))
            for fn in changes.files:
                unlink_if_exists(os.path.join(directory, fn))

###############################################################################

def process_changes(changes_filenames):
    session = DBConn().session()
    keyrings = session.query(Keyring).filter_by(active=True).order_by(Keyring.priority)
    keyring_files = [ k.keyring_name for k in keyrings ]

    changes = []
    for fn in changes_filenames:
        try:
            directory, filename = os.path.split(fn)
            c = daklib.upload.Changes(directory, filename, keyring_files)
            changes.append([directory, c])
        except Exception as e:
            Logger.log([filename, "Error while loading changes: {0}".format(e)])

    changes.sort(key=lambda x: x[1])

    for directory, c in changes:
        process_it(directory, c, keyring_files, session)

    session.rollback()

###############################################################################

def main():
    global Options, Logger

    cnf = Config()
    summarystats = SummaryStats()

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

    changes_files = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Dinstall::Options")

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
        lock_fd = os.open(os.path.join(cnf["Dir::Lock"], 'dinstall.lock'), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError as e:
            if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EAGAIN':
                utils.fubar("Couldn't obtain lock; assuming another 'dak process-upload' is already running.")
            else:
                raise

        # Initialise UrgencyLog() - it will deal with the case where we don't
        # want to log urgencies
        urgencylog = UrgencyLog()

    Logger = daklog.Logger("process-upload", Options["No-Action"])

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

    process_changes(changes_files)

    if summarystats.accept_count:
        sets = "set"
        if summarystats.accept_count > 1:
            sets = "sets"
        print "Installed %d package %s, %s." % (summarystats.accept_count, sets,
                                                utils.size_type(int(summarystats.accept_bytes)))
        Logger.log(["total", summarystats.accept_count, summarystats.accept_bytes])

    if summarystats.reject_count:
        sets = "set"
        if summarystats.reject_count > 1:
            sets = "sets"
        print "Rejected %d package %s." % (summarystats.reject_count, sets)
        Logger.log(["rejected", summarystats.reject_count])

    if not Options["No-Action"]:
        urgencylog.close()

    Logger.close()

###############################################################################

if __name__ == '__main__':
    main()
