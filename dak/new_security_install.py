#! /usr/bin/env python3

"""
Do whatever is needed to get a security upload released

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2010 Joerg Jaspert <joerg@debian.org>
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


################################################################################

import os
import sys
import time
import apt_pkg
import errno
import fcntl
import subprocess

from daklib import daklog
from daklib import utils
from daklib.dbconn import *
from daklib.regexes import re_taint_free
from daklib.config import Config

Options = None
Logger = None
Queue = None
changes = []


def usage():
    print("""Usage: dak security-install [OPTIONS] changesfiles
Do whatever there is to do for a security release

    -h, --help                 show this help and exit
    -n, --no-action            don't commit changes
    -s, --sudo                 dont bother, used internally

""")
    sys.exit()


def spawn(command):
    if not re_taint_free.match(command):
        utils.fubar("Invalid character in \"%s\"." % (command))

    if Options["No-Action"]:
        print("[%s]" % (command))
    else:
        try:
            subprocess.check_output(command.split(), stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            utils.fubar("Invocation of '%s' failed:\n%s\n" % (command, e.output.rstrip()), e.returncode)

##################### ! ! ! N O T E ! ! !  #####################
#
# These functions will be reinvoked by semi-priveleged users, be careful not
# to invoke external programs that will escalate privileges, etc.
#
##################### ! ! ! N O T E ! ! !  #####################


def sudo(arg, fn, exit):
    if Options["Sudo"]:
        subprocess.check_call(
            ["/usr/bin/sudo", "-u", "dak", "-H",
             "/usr/local/bin/dak", "new-security-install", "-" + arg])
    else:
        fn()
    if exit:
        quit()


def do_Approve():
    sudo("A", _do_Approve, True)


def _do_Approve():
    print("Locking unchecked")
    with os.fdopen(os.open('/srv/security-master.debian.org/lock/unchecked.lock', os.O_CREAT | os.O_RDWR), 'r') as lock_fd:
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except IOError as e:
                if e.errno in (errno.EACCES, errno.EAGAIN):
                    print("Another process keeping the unchecked lock, waiting.")
                    time.sleep(10)
                else:
                    raise

        # 1. Install accepted packages
        print("Installing accepted packages into security archive")
        for queue_name in ("embargoed",):
            spawn("dak process-policy {0}".format(queue_name))

    # 2. Run all the steps that are needed to publish the changed archive
    print("Doing loadsa stuff in the archive, will take time, please be patient")
    os.environ['configdir'] = '/srv/security-master.debian.org/dak/config/debian-security'
    spawn("/srv/security-master.debian.org/dak/config/debian-security/cronscript unchecked-dinstall")

    print("Triggering metadata export for packages.d.o and other consumers")
    spawn("/srv/security-master.debian.org/dak/config/debian-security/export.sh")

########################################################################
########################################################################


def main():
    global Options, Logger, Queue, changes
    cnf = Config()

    Arguments = [('h', "Help",      "Security::Options::Help"),
                 ('n', "No-Action", "Security::Options::No-Action"),
                 ('c', 'Changesfile', "Security::Options::Changesfile"),
                 ('s', "Sudo", "Security::Options::Sudo"),
                 ('A', "Approve", "Security::Options::Approve")
                 ]

    for i in ["Help", "No-Action", "Changesfile", "Sudo", "Approve"]:
        key = "Security::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    changes_files = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.subtree("Security::Options")
    if Options['Help']:
        usage()

    changesfiles = {}
    for a in changes_files:
        if not a.endswith(".changes"):
            utils.fubar("not a .changes file: %s" % (a))
        changesfiles[a] = 1
    changes = list(changesfiles.keys())

    username = utils.getusername()
    if username != "dak":
        print("Non-dak user: %s" % username)
        Options["Sudo"] = "y"

    if Options["No-Action"]:
        Options["Sudo"] = ""

    if not Options["Sudo"] and not Options["No-Action"]:
        Logger = daklog.Logger("security-install")

    session = DBConn().session()

    # If we call ourselve to approve, we do just that and exit
    if Options["Approve"]:
        do_Approve()
        sys.exit()

    if len(changes) == 0:
        utils.fubar("Need changes files as arguments")

    # Yes, we could do this inside do_Approve too. But this way we see who exactly
    # called it (ownership of the file)

    acceptfiles = {}
    for change in changes:
        dbchange = get_dbchange(os.path.basename(change), session)
        # strip epoch from version
        version = dbchange.version
        version = version[(version.find(':') + 1):]
        # strip possible version from source (binNMUs)
        source = dbchange.source.split(None, 1)[0]
        acceptfilename = "%s/COMMENTS/ACCEPT.%s_%s" % (os.path.dirname(os.path.abspath(changes[0])), source, version)
        acceptfiles[acceptfilename] = 1

    print("Would create %s now and then go on to accept this package, if you allow me to." % (list(acceptfiles.keys())))
    if Options["No-Action"]:
        sys.exit(0)
    else:
        input("Press Enter to continue")

    for acceptfilename in acceptfiles:
        with open(acceptfilename, "w") as accept_file:
            accept_file.write("OK\n")

    do_Approve()


if __name__ == '__main__':
    main()
