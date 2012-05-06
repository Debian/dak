#!/usr/bin/env python
# coding=utf8

"""
Import known_changes files

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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

import sys
import os
import logging
import threading
from daklib.dbconn import DBConn, get_dbchange, get_policy_queue
from daklib.config import Config
import apt_pkg
from daklib.dak_exceptions import DBUpdateError, InvalidDscError, ChangesUnicodeError
from daklib.changes import Changes
from daklib.utils import parse_changes, warn, gpgv_get_status_output, process_gpgv_output
import traceback

# where in dak.conf all of our configuration will be stowed
options_prefix = "KnownChanges"
options_prefix = "%s::Options" % options_prefix

log = logging.getLogger()

################################################################################


def usage (exit_code=0):
    print """Usage: dak import-known-changes [options]

OPTIONS
     -j n
        run with n threads concurrently

     -v, --verbose
        show verbose information messages

     -q, --quiet
        supress all output but errors

"""
    sys.exit(exit_code)

def check_signature (sig_filename, data_filename=""):
    fingerprint = None

    keyrings = [
        "/home/joerg/keyring/keyrings/debian-keyring.gpg",
        "/home/joerg/keyring/keyrings/debian-maintainers.gpg",
        "/home/joerg/keyring/keyrings/debian-role-keys.gpg",
        "/home/joerg/keyring/keyrings/emeritus-keyring.pgp",
        "/home/joerg/keyring/keyrings/emeritus-keyring.gpg",
        "/home/joerg/keyring/keyrings/removed-keys.gpg",
        "/home/joerg/keyring/keyrings/removed-keys.pgp"
        ]

    keyringargs = " ".join(["--keyring %s" % x for x in keyrings ])

    # Build the command line
    status_read, status_write = os.pipe()
    cmd = "gpgv --status-fd %s %s %s" % (status_write, keyringargs, sig_filename)

    # Invoke gpgv on the file
    (output, status, exit_status) = gpgv_get_status_output(cmd, status_read, status_write)

    # Process the status-fd output
    (keywords, internal_error) = process_gpgv_output(status)

    # If we failed to parse the status-fd output, let's just whine and bail now
    if internal_error:
        warn("Couldn't parse signature")
        return None

    # usually one would check for bad things here. We, however, do not care.

    # Next check gpgv exited with a zero return code
    if exit_status:
        warn("Couldn't parse signature")
        return None

    # Sanity check the good stuff we expect
    if not keywords.has_key("VALIDSIG"):
        warn("Couldn't parse signature")
    else:
        args = keywords["VALIDSIG"]
        if len(args) < 1:
            warn("Couldn't parse signature")
        else:
            fingerprint = args[0]

    return fingerprint


class EndOfChanges(object):
    """something enqueued to signify the last change"""
    pass


class OneAtATime(object):
    """
    a one space queue which sits between multiple possible producers
    and multiple possible consumers
    """
    def __init__(self):
        self.next_in_line = None
        self.read_lock = threading.Condition()
        self.write_lock = threading.Condition()
        self.die = False

    def plsDie(self):
        self.die = True
        self.write_lock.acquire()
        self.write_lock.notifyAll()
        self.write_lock.release()

        self.read_lock.acquire()
        self.read_lock.notifyAll()
        self.read_lock.release()

    def enqueue(self, next):
        self.write_lock.acquire()
        while self.next_in_line:
            if self.die:
                return
            self.write_lock.wait()

        assert( not self.next_in_line )
        self.next_in_line = next
        self.write_lock.release()
        self.read_lock.acquire()
        self.read_lock.notify()
        self.read_lock.release()

    def dequeue(self):
        self.read_lock.acquire()
        while not self.next_in_line:
            if self.die:
                return
            self.read_lock.wait()

        result = self.next_in_line

        self.next_in_line = None
        self.read_lock.release()
        self.write_lock.acquire()
        self.write_lock.notify()
        self.write_lock.release()

        if isinstance(result, EndOfChanges):
            return None

        return result

class ChangesToImport(object):
    """A changes file to be enqueued to be processed"""
    def __init__(self, checkdir, changesfile, count):
        self.dirpath = checkdir
        self.changesfile = changesfile
        self.count = count

    def __str__(self):
        return "#%d: %s in %s" % (self.count, self.changesfile, self.dirpath)

class ChangesGenerator(threading.Thread):
    """enqueues changes files to be imported"""
    def __init__(self, parent, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.session = DBConn().session()
        self.parent = parent
        self.die = False

    def plsDie(self):
        self.die = True

    def run(self):
        cnf = Config()
        count = 1

        dirs = []
        dirs.append(cnf['Dir::Done'])

        for queue_name in [ "byhand", "new", "proposedupdates", "oldproposedupdates" ]:
            queue = get_policy_queue(queue_name)
            if queue:
                dirs.append(os.path.abspath(queue.path))
            else:
                warn("Could not find queue %s in database" % queue_name)

        for checkdir in dirs:
            if os.path.exists(checkdir):
                print "Looking into %s" % (checkdir)

                for dirpath, dirnames, filenames in os.walk(checkdir, topdown=True):
                    if not filenames:
                        # Empty directory (or only subdirectories), next
                        continue

                    for changesfile in filenames:
                        try:
                            if not changesfile.endswith(".changes"):
                                # Only interested in changes files.
                                continue
                            count += 1

                            if not get_dbchange(changesfile, self.session):
                                to_import = ChangesToImport(dirpath, changesfile, count)
                                if self.die:
                                    return
                                self.queue.enqueue(to_import)
                        except KeyboardInterrupt:
                            print("got Ctrl-c in enqueue thread.  terminating")
                            self.parent.plsDie()
                            sys.exit(1)

        self.queue.enqueue(EndOfChanges())

class ImportThread(threading.Thread):
    def __init__(self, parent, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.session = DBConn().session()
        self.parent = parent
        self.die = False

    def plsDie(self):
        self.die = True

    def run(self):
        while True:
            try:
                if self.die:
                    return
                to_import = self.queue.dequeue()
                if not to_import:
                    return

                print( "Directory %s, file %7d, (%s)" % (to_import.dirpath[-10:], to_import.count, to_import.changesfile) )

                changes = Changes()
                changes.changes_file = to_import.changesfile
                changesfile = os.path.join(to_import.dirpath, to_import.changesfile)
                changes.changes = parse_changes(changesfile, signing_rules=-1)
                changes.changes["fingerprint"] = check_signature(changesfile)
                changes.add_known_changes(to_import.dirpath, session=self.session)
                self.session.commit()

            except InvalidDscError as line:
                warn("syntax error in .dsc file '%s', line %s." % (f, line))

            except ChangesUnicodeError:
                warn("found invalid changes file, not properly utf-8 encoded")

            except KeyboardInterrupt:
                print("Caught C-c; on ImportThread. terminating.")
                self.parent.plsDie()
                sys.exit(1)

            except:
                self.parent.plsDie()
                sys.exit(1)

class ImportKnownChanges(object):
    def __init__(self,num_threads):
        self.queue = OneAtATime()
        self.threads = [ ChangesGenerator(self,self.queue) ]

        for i in range(num_threads):
            self.threads.append( ImportThread(self,self.queue) )

        try:
            for thread in self.threads:
                thread.start()

        except KeyboardInterrupt:
            print("Caught C-c; terminating.")
            warn("Caught C-c; terminating.")
            self.plsDie()

    def plsDie(self):
        traceback.print_stack90
        for thread in self.threads:
            print( "STU: before ask %s to die" % thread )
            thread.plsDie()
            print( "STU: after ask %s to die" % thread )

        self.threads=[]
        sys.exit(1)


def main():
    cnf = Config()

    arguments = [('h',"help", "%s::%s" % (options_prefix,"Help")),
                 ('j',"concurrency", "%s::%s" % (options_prefix,"Concurrency"),"HasArg"),
                 ('q',"quiet", "%s::%s" % (options_prefix,"Quiet")),
                 ('v',"verbose", "%s::%s" % (options_prefix,"Verbose")),
                ]

    args = apt_pkg.parse_commandline(cnf.Cnf, arguments,sys.argv)

    num_threads = 1

    if len(args) > 0:
        usage()

    if cnf.has_key("%s::%s" % (options_prefix,"Help")):
        usage()

    level=logging.INFO
    if cnf.has_key("%s::%s" % (options_prefix,"Quiet")):
        level=logging.ERROR

    elif cnf.has_key("%s::%s" % (options_prefix,"Verbose")):
        level=logging.DEBUG


    logging.basicConfig( level=level,
                         format='%(asctime)s %(levelname)s %(message)s',
                         stream = sys.stderr )

    if Config().has_key( "%s::%s" %(options_prefix,"Concurrency")):
        num_threads = int(Config()[ "%s::%s" %(options_prefix,"Concurrency")])

    ImportKnownChanges(num_threads)




if __name__ == '__main__':
    main()
