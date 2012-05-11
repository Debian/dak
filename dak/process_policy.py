#!/usr/bin/env python
# vim:set et ts=4 sw=4:

""" Handles packages from policy queues

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009 Joerg Jaspert <joerg@debian.org>
@copyright: 2009 Frank Lichtenheld <djpig@debian.org>
@copyright: 2009 Mark Hymers <mhy@debian.org>
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

# <mhy> So how do we handle that at the moment?
# <stew> Probably incorrectly.

################################################################################

import os
import copy
import sys
import apt_pkg

from daklib.dbconn import *
from daklib.queue import *
from daklib import daklog
from daklib import utils
from daklib.dak_exceptions import CantOpenError, AlreadyLockedError, CantGetLockError
from daklib.config import Config
from daklib.changesutils import *

# Globals
Options = None
Logger = None

################################################################################

def do_comments(dir, srcqueue, opref, npref, line, fn, session):
    for comm in [ x for x in os.listdir(dir) if x.startswith(opref) ]:
        lines = open("%s/%s" % (dir, comm)).readlines()
        if len(lines) == 0 or lines[0] != line + "\n": continue
        changes_files = [ x for x in os.listdir(".") if x.startswith(comm[len(opref):]+"_")
                                and x.endswith(".changes") ]
        changes_files = sort_changes(changes_files, session)
        for f in changes_files:
            print "Processing changes file: %s" % f
            f = utils.validate_changes_file_arg(f, 0)
            if not f:
                print "Couldn't validate changes file %s" % f
                continue
            fn(f, srcqueue, "".join(lines[1:]), session)

        if opref != npref and not Options["No-Action"]:
            newcomm = npref + comm[len(opref):]
            os.rename("%s/%s" % (dir, comm), "%s/%s" % (dir, newcomm))

################################################################################

def comment_accept(changes_file, srcqueue, comments, session):
    u = Upload()
    u.pkg.changes_file = changes_file
    u.load_changes(changes_file)
    u.update_subst()

    if not Options["No-Action"]:
        destqueue = get_policy_queue('newstage', session)
        if changes_to_queue(u, srcqueue, destqueue, session):
            print "  ACCEPT"
            Logger.log(["Policy Queue ACCEPT: %s:  %s" % (srcqueue.queue_name, u.pkg.changes_file)])
        else:
            print "E: Failed to migrate %s" % u.pkg.changes_file

################################################################################

def comment_reject(changes_file, srcqueue, comments, session):
    u = Upload()
    u.pkg.changes_file = changes_file
    u.load_changes(changes_file)
    u.update_subst()

    u.rejects.append(comments)

    cnf = Config()
    bcc = "X-DAK: dak process-policy"
    if cnf.has_key("Dinstall::Bcc"):
        u.Subst["__BCC__"] = bcc + "\nBcc: %s" % (cnf["Dinstall::Bcc"])
    else:
        u.Subst["__BCC__"] = bcc

    if not Options["No-Action"]:
        u.do_reject(manual=0, reject_message='\n'.join(u.rejects))
        u.pkg.remove_known_changes(session=session)
        session.commit()

        print "  REJECT"
        Logger.log(["Policy Queue REJECT: %s:  %s" % (srcqueue.queue_name, u.pkg.changes_file)])


################################################################################

def main():
    global Options, Logger

    cnf = Config()
    session = DBConn().session()

    Arguments = [('h',"help","Process-Policy::Options::Help"),
                 ('n',"no-action","Process-Policy::Options::No-Action")]

    for i in ["help", "no-action"]:
        if not cnf.has_key("Process-Policy::Options::%s" % (i)):
            cnf["Process-Policy::Options::%s" % (i)] = ""

    queue_name = apt_pkg.parse_commandline(cnf.Cnf,Arguments,sys.argv)

    if len(queue_name) != 1:
        print "E: Specify exactly one policy queue"
        sys.exit(1)

    queue_name = queue_name[0]

    Options = cnf.subtree("Process-Policy::Options")

    if Options["Help"]:
        usage()

    if not Options["No-Action"]:
        try:
            Logger = daklog.Logger("process-policy")
        except CantOpenError as e:
            Logger = None

    # Find policy queue
    session.query(PolicyQueue)

    try:
        pq = session.query(PolicyQueue).filter_by(queue_name=queue_name).one()
    except NoResultFound:
        print "E: Cannot find policy queue %s" % queue_name
        sys.exit(1)

    commentsdir = os.path.join(pq.path, 'COMMENTS')
    # The comments stuff relies on being in the right directory
    os.chdir(pq.path)
    do_comments(commentsdir, pq, "ACCEPT.", "ACCEPTED.", "OK", comment_accept, session)
    do_comments(commentsdir, pq, "ACCEPTED.", "ACCEPTED.", "OK", comment_accept, session)
    do_comments(commentsdir, pq, "REJECT.", "REJECTED.", "NOTOK", comment_reject, session)


################################################################################

if __name__ == '__main__':
    main()
