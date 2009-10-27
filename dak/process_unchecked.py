#!/usr/bin/env python

"""
Checks Debian packages from Incoming
@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
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

# Originally based on dinstall by Guy Maor <maor@debian.org>

################################################################################

# Computer games don't affect kids. I mean if Pacman affected our generation as
# kids, we'd all run around in a darkened room munching pills and listening to
# repetitive music.
#         -- Unknown

################################################################################

import errno
import fcntl
import os
import sys
import traceback
import apt_pkg

from daklib.dbconn import *
from daklib import daklog
from daklib.queue import *
from daklib import utils
from daklib.textutils import fix_maintainer
from daklib.dak_exceptions import *
from daklib.regexes import re_default_answer
from daklib.summarystats import SummaryStats
from daklib.holding import Holding
from daklib.config import Config

from types import *

################################################################################


################################################################################

# Globals
Options = None
Logger = None

###############################################################################

def init():
    global Options

    apt_pkg.init()
    cnf = Config()

    Arguments = [('a',"automatic","Dinstall::Options::Automatic"),
                 ('h',"help","Dinstall::Options::Help"),
                 ('n',"no-action","Dinstall::Options::No-Action"),
                 ('p',"no-lock", "Dinstall::Options::No-Lock"),
                 ('s',"no-mail", "Dinstall::Options::No-Mail"),
                 ('d',"directory", "Dinstall::Options::Directory", "HasArg")]

    for i in ["automatic", "help", "no-action", "no-lock", "no-mail",
              "override-distribution", "version", "directory"]:
        cnf["Dinstall::Options::%s" % (i)] = ""

    changes_files = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Dinstall::Options")

    if Options["Help"]:
        usage()

    # If we have a directory flag, use it to find our files
    if cnf["Dinstall::Options::Directory"] != "":
        # Note that we clobber the list of files we were given in this case
        # so warn if the user has done both
        if len(changes_files) > 0:
            utils.warn("Directory provided so ignoring files given on command line")

        changes_files = utils.get_changes_files(cnf["Dinstall::Options::Directory"])

    return changes_files

################################################################################

def usage (exit_code=0):
    print """Usage: dinstall [OPTION]... [CHANGES]...
  -a, --automatic           automatic run
  -h, --help                show this help and exit.
  -n, --no-action           don't do anything
  -p, --no-lock             don't check lockfile !! for cron.daily only !!
  -s, --no-mail             don't send any mail
  -V, --version             display the version number and exit"""
    sys.exit(exit_code)

################################################################################

def action(u):
    cnf = Config()

    # changes["distribution"] may not exist in corner cases
    # (e.g. unreadable changes files)
    if not u.pkg.changes.has_key("distribution") or not isinstance(u.pkg.changes["distribution"], DictType):
        u.pkg.changes["distribution"] = {}

    (summary, short_summary) = u.build_summaries()

    # q-unapproved hax0ring
    queue_info = {
         "New": { "is": is_new, "process": acknowledge_new },
         "Autobyhand" : { "is" : is_autobyhand, "process": do_autobyhand },
         "Byhand" : { "is": is_byhand, "process": do_byhand },
         "OldStableUpdate" : { "is": is_oldstableupdate,
                               "process": do_oldstableupdate },
         "StableUpdate" : { "is": is_stableupdate, "process": do_stableupdate },
         "Unembargo" : { "is": is_unembargo, "process": queue_unembargo },
         "Embargo" : { "is": is_embargo, "process": queue_embargo },
    }

    queues = [ "New", "Autobyhand", "Byhand" ]
    if cnf.FindB("Dinstall::SecurityQueueHandling"):
        queues += [ "Unembargo", "Embargo" ]
    else:
        queues += [ "OldStableUpdate", "StableUpdate" ]

    (prompt, answer) = ("", "XXX")
    if Options["No-Action"] or Options["Automatic"]:
        answer = 'S'

    queuekey = ''

    pi = u.package_info()

    if len(u.rejects) > 0:
        if u.upload_too_new():
            print "SKIP (too new)\n" + pi,
            prompt = "[S]kip, Quit ?"
        else:
            print "REJECT\n" + pi
            prompt = "[R]eject, Skip, Quit ?"
            if Options["Automatic"]:
                answer = 'R'
    else:
        qu = None
        for q in queues:
            if queue_info[q]["is"](u):
                qu = q
                break
        if qu:
            print "%s for %s\n%s%s" % ( qu.upper(), ", ".join(u.pkg.changes["distribution"].keys()), pi, summary)
            queuekey = qu[0].upper()
            if queuekey in "RQSA":
                queuekey = "D"
                prompt = "[D]ivert, Skip, Quit ?"
            else:
                prompt = "[%s]%s, Skip, Quit ?" % (queuekey, qu[1:].lower())
            if Options["Automatic"]:
                answer = queuekey
        else:
            print "ACCEPT\n" + pi + summary,
            prompt = "[A]ccept, Skip, Quit ?"
            if Options["Automatic"]:
                answer = 'A'

    while prompt.find(answer) == -1:
        answer = utils.our_raw_input(prompt)
        m = re_default_answer.match(prompt)
        if answer == "":
            answer = m.group(1)
        answer = answer[:1].upper()

    if answer == 'R':
        os.chdir(u.pkg.directory)
        u.do_reject(0, pi)
    elif answer == 'A':
        u.accept(summary, short_summary)
        u.check_override()
        u.remove()
    elif answer == queuekey:
        queue_info[qu]["process"](u, summary, short_summary)
        u.remove()
    elif answer == 'Q':
        sys.exit(0)

################################################################################

def package_to_suite(u, suite):
    if not u.pkg.changes["distribution"].has_key(suite):
        return False

    ret = True

    if not u.pkg.changes["architecture"].has_key("source"):
        s = DBConn().session()
        q = s.query(SrcAssociation.sa_id)
        q = q.join(Suite).filter_by(suite_name=suite)
        q = q.join(DBSource).filter_by(source=u.pkg.changes['source'])
        q = q.filter_by(version=u.pkg.changes['version']).limit(1)

        # NB: Careful, this logic isn't what you would think it is
        # Source is already in {old-,}proposed-updates so no need to hold
        # Instead, we don't move to the holding area, we just do an ACCEPT
        if q.count() > 0:
            ret = False

        s.close()

    return ret

def package_to_queue(u, summary, short_summary, queue, perms=0660, build=True, announce=None):
    cnf = Config()
    dir = cnf["Dir::Queue::%s" % queue]

    print "Moving to %s holding area" % queue.upper()
    Logger.log(["Moving to %s" % queue, u.pkg.changes_file])

    u.pkg.write_dot_dak(dir)
    u.move_to_dir(dir, perms=perms)
    if build:
        get_or_set_queue(queue.lower()).autobuild_upload(u.pkg, dir)

    # Check for override disparities
    u.check_override()

    # Send accept mail, announce to lists and close bugs
    if announce and not cnf["Dinstall::Options::No-Mail"]:
        template = os.path.join(cnf["Dir::Templates"], announce)
        u.update_subst()
        u.Subst["__SUITE__"] = ""
        mail_message = utils.TemplateSubst(u.Subst, template)
        utils.send_mail(mail_message)
        u.announce(short_summary, True)

################################################################################

def is_unembargo(u):
    session = DBConn().session()
    cnf = Config()

    q = session.execute("SELECT package FROM disembargo WHERE package = :source AND version = :version", u.pkg.changes)
    if q.rowcount > 0:
        session.close()
        return True

    oldcwd = os.getcwd()
    os.chdir(cnf["Dir::Queue::Disembargo"])
    disdir = os.getcwd()
    os.chdir(oldcwd)

    ret = False

    if u.pkg.directory == disdir:
        if u.pkg.changes["architecture"].has_key("source"):
            if not Options["No-Action"]:
                session.execute("INSERT INTO disembargo (package, version) VALUES (:package, :version)", u.pkg.changes)
                session.commit()

            ret = True

    session.close()

    return ret

def queue_unembargo(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "Unembargoed",
                            perms=0660, build=True, announce='process-unchecked.accepted')

################################################################################

def is_embargo(u):
    # if embargoed queues are enabled always embargo
    return True

def queue_embargo(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "Unembargoed",
                            perms=0660, build=True, announce='process-unchecked.accepted')

################################################################################

def is_stableupdate(u):
    return package_to_suite(u, 'proposed-updates')

def do_stableupdate(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "ProposedUpdates",
                            perms=0664, build=False, announce=None)

################################################################################

def is_oldstableupdate(u):
    return package_to_suite(u, 'oldstable-proposed-updates')

def do_oldstableupdate(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "OldProposedUpdates",
                            perms=0664, build=False, announce=None)

################################################################################

def is_autobyhand(u):
    cnf = Config()

    all_auto = 1
    any_auto = 0
    for f in u.pkg.files.keys():
        if u.pkg.files[f].has_key("byhand"):
            any_auto = 1

            # filename is of form "PKG_VER_ARCH.EXT" where PKG, VER and ARCH
            # don't contain underscores, and ARCH doesn't contain dots.
            # further VER matches the .changes Version:, and ARCH should be in
            # the .changes Architecture: list.
            if f.count("_") < 2:
                all_auto = 0
                continue

            (pckg, ver, archext) = f.split("_", 2)
            if archext.count(".") < 1 or u.pkg.changes["version"] != ver:
                all_auto = 0
                continue

            ABH = cnf.SubTree("AutomaticByHandPackages")
            if not ABH.has_key(pckg) or \
              ABH["%s::Source" % (pckg)] != u.pkg.changes["source"]:
                print "not match %s %s" % (pckg, u.pkg.changes["source"])
                all_auto = 0
                continue

            (arch, ext) = archext.split(".", 1)
            if arch not in u.pkg.changes["architecture"]:
                all_auto = 0
                continue

            u.pkg.files[f]["byhand-arch"] = arch
            u.pkg.files[f]["byhand-script"] = ABH["%s::Script" % (pckg)]

    return any_auto and all_auto

def do_autobyhand(u, summary, short_summary):
    print "Attempting AUTOBYHAND."
    byhandleft = True
    for f, entry in u.pkg.files.items():
        byhandfile = f

        if not entry.has_key("byhand"):
            continue

        if not entry.has_key("byhand-script"):
            byhandleft = True
            continue

        os.system("ls -l %s" % byhandfile)

        result = os.system("%s %s %s %s %s" % (
                entry["byhand-script"],
                byhandfile,
                u.pkg.changes["version"],
                entry["byhand-arch"],
                os.path.abspath(u.pkg.changes_file)))

        if result == 0:
            os.unlink(byhandfile)
            del entry
        else:
            print "Error processing %s, left as byhand." % (f)
            byhandleft = True

    if byhandleft:
        do_byhand(u, summary, short_summary)
    else:
        u.accept(summary, short_summary)
        u.check_override()
        # XXX: We seem to be missing a u.remove() here
        #      This might explain why we get byhand leftovers in unchecked - mhy

################################################################################

def is_byhand(u):
    for f in u.pkg.files.keys():
        if u.pkg.files[f].has_key("byhand"):
            return True
    return False

def do_byhand(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "Byhand",
                            perms=0660, build=False, announce=None)

################################################################################

def is_new(u):
    for f in u.pkg.files.keys():
        if u.pkg.files[f].has_key("new"):
            return True
    return False

def acknowledge_new(u, summary, short_summary):
    cnf = Config()

    print "Moving to NEW holding area."
    Logger.log(["Moving to new", u.pkg.changes_file])

    u.pkg.write_dot_dak(cnf["Dir::Queue::New"])
    u.move_to_dir(cnf["Dir::Queue::New"], perms=0640, changesperms=0644)

    if not Options["No-Mail"]:
        print "Sending new ack."
        template = os.path.join(cnf["Dir::Templates"], 'process-unchecked.new')
        u.update_subst()
        u.Subst["__SUMMARY__"] = summary
        new_ack_message = utils.TemplateSubst(u.Subst, template)
        utils.send_mail(new_ack_message)

################################################################################

# reprocess is necessary for the case of foo_1.2-1 and foo_1.2-2 in
# Incoming. -1 will reference the .orig.tar.gz, but -2 will not.
# Upload.check_dsc_against_db() can find the .orig.tar.gz but it will
# not have processed it during it's checks of -2.  If -1 has been
# deleted or otherwise not checked by 'dak process-unchecked', the
# .orig.tar.gz will not have been checked at all.  To get round this,
# we force the .orig.tar.gz into the .changes structure and reprocess
# the .changes file.

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
    bcc = "X-DAK: dak process-unchecked\nX-Katie: $Revision: 1.65 $"
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
                if valid_dsc_p:
                    u.check_source()
                    # u.check_lintian()
                u.check_hashes()
                u.check_urgency()
                u.check_timestamps()
                u.check_signed_by_key()

        action(u)

    except SystemExit:
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
    changes_files = init()

    # -n/--dry-run invalidates some other options which would involve things happening
    if Options["No-Action"]:
        Options["Automatic"] = ""

    # Initialize our Holding singleton
    holding = Holding()

    # Ensure all the arguments we were given are .changes files
    for f in changes_files:
        if not f.endswith(".changes"):
            utils.warn("Ignoring '%s' because it's not a .changes file." % (f))
            changes_files.remove(f)

    if changes_files == []:
        if cnf["Dinstall::Options::Directory"] == "":
            utils.fubar("Need at least one .changes file as an argument.")
        else:
            sys.exit(0)

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
                utils.fubar("Couldn't obtain lock; assuming another 'dak process-unchecked' is already running.")
            else:
                raise
        Logger = daklog.Logger(cnf, "process-unchecked")

    # Sort the .changes files so that we process sourceful ones first
    changes_files.sort(utils.changes_compare)

    # Process the changes files
    for changes_file in changes_files:
        print "\n" + changes_file
        try:
            process_it (changes_file)
        finally:
            if not Options["No-Action"]:
                holding.clean()

    accept_count = SummaryStats().accept_count
    accept_bytes = SummaryStats().accept_bytes

    if accept_count:
        sets = "set"
        if accept_count > 1:
            sets = "sets"
        print "Accepted %d package %s, %s." % (accept_count, sets, utils.size_type(int(accept_bytes)))
        Logger.log(["total",accept_count,accept_bytes])

    if not Options["No-Action"]:
        Logger.close()

################################################################################

if __name__ == '__main__':
    main()
