#!/usr/bin/env python
"""
Create all the contents files

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2008, 2009 Michael Casadevall <mcasadevall@debian.org>
@copyright: 2009 Mike O'Connor <stew@debian.org>
@license: GNU General Public License version 2 or later
"""

################################################################################

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

# <Ganneff> there is the idea to slowly replace contents files
# <Ganneff> with a new generation of such files.
# <Ganneff> having more info.

# <Ganneff> of course that wont help for now where we need to generate them :)

################################################################################

import sys
import os
import logging
import gzip
import threading
import traceback
import Queue
import apt_pkg
from daklib import utils
from daklib.binary import Binary
from daklib.config import Config
from daklib.dbconn import *

################################################################################

def usage (exit_code=0):
    print """Usage: dak contents [options] command [arguments]

COMMANDS
    generate
        generate Contents-$arch.gz files

    bootstrap_bin
        scan the debs in the existing pool and load contents into the bin_contents table

    cruft
        remove files/paths which are no longer referenced by a binary

OPTIONS
     -h, --help
        show this help and exit

     -v, --verbose
        show verbose information messages

     -q, --quiet
        supress all output but errors

     -s, --suite={stable,testing,unstable,...}
        only operate on a single suite
"""
    sys.exit(exit_code)

################################################################################

# where in dak.conf all of our configuration will be stowed

options_prefix = "Contents"
options_prefix = "%s::Options" % options_prefix

log = logging.getLogger()

################################################################################

class EndOfContents(object):
    """
    A sentry object for the end of the filename stream
    """
    pass

class GzippedContentWriter(object):
    """
    An object which will write contents out to a Contents-$arch.gz
    file on a separate thread
    """

    header = None # a class object holding the header section of contents file

    def __init__(self, filename):
        """
        @type filename: string
        @param filename: the name of the file to write to
        """
        self.queue = Queue.Queue()
        self.current_file = None
        self.first_package = True
        self.output = self.open_file(filename)
        self.thread = threading.Thread(target=self.write_thread,
                                       name='Contents writer')
        self.thread.start()

    def open_file(self, filename):
        """
        opens a gzip stream to the contents file
        """
        filepath = Config()["Contents::Root"] + filename
        filedir = os.path.dirname(filepath)
        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        return gzip.open(filepath, "w")

    def write(self, filename, section, package):
        """
        enqueue content to be written to the file on a separate thread
        """
        self.queue.put((filename,section,package))

    def write_thread(self):
        """
        the target of a Thread which will do the actual writing
        """
        while True:
            next = self.queue.get()
            if isinstance(next, EndOfContents):
                self.output.write('\n')
                self.output.close()
                break

            (filename,section,package)=next
            if next != self.current_file:
                # this is the first file, so write the header first
                if not self.current_file:
                    self.output.write(self._getHeader())

                self.output.write('\n%s\t' % filename)
                self.first_package = True

            self.current_file=filename

            if not self.first_package:
                self.output.write(',')
            else:
                self.first_package=False
            self.output.write('%s/%s' % (section,package))

    def finish(self):
        """
        enqueue the sentry object so that writers will know to terminate
        """
        self.queue.put(EndOfContents())

    @classmethod
    def _getHeader(self):
        """
        Internal method to return the header for Contents.gz files

        This is boilerplate which explains the contents of the file and how
        it can be used.
        """
        if not GzippedContentWriter.header:
            if Config().has_key("Contents::Header"):
                try:
                    h = open(os.path.join( Config()["Dir::Templates"],
                                           Config()["Contents::Header"] ), "r")
                    GzippedContentWriter.header = h.read()
                    h.close()
                except:
                    log.error( "error opening header file: %d\n%s" % (Config()["Contents::Header"],
                                                                      traceback.format_exc() ))
                    GzippedContentWriter.header = None
            else:
                GzippedContentWriter.header = None

        return GzippedContentWriter.header


class Contents(object):
    """
    Class capable of generating Contents-$arch.gz files
    """

    def __init__(self):
        self.header = None

    def reject(self, message):
        log.error("E: %s" % message)

    def cruft(self):
        """
        remove files/paths from the DB which are no longer referenced
        by binaries and clean the temporary table
        """
        s = DBConn().session()

        # clear out all of the temporarily stored content associations
        # this should be run only after p-a has run.  after a p-a
        # run we should have either accepted or rejected every package
        # so there should no longer be anything in the queue
        s.query(PendingContentAssociation).delete()

        # delete any filenames we are storing which have no binary associated
        # with them
        cafq = s.query(ContentAssociation.filename_id).distinct()
        cfq = s.query(ContentFilename)
        cfq = cfq.filter(~ContentFilename.cafilename_id.in_(cafq))
        cfq.delete()

        # delete any paths we are storing which have no binary associated with
        # them
        capq = s.query(ContentAssociation.filepath_id).distinct()
        cpq = s.query(ContentFilepath)
        cpq = cpq.filter(~ContentFilepath.cafilepath_id.in_(capq))
        cpq.delete()

        s.commit()


    def bootstrap_bin(self):
        """
        scan the existing debs in the pool to populate the bin_contents table
        """
        pooldir = Config()[ 'Dir::Pool' ]

        s = DBConn().session()

        #        for binary in s.query(DBBinary).all() ):
        binary = s.query(DBBinary).first()
        if binary:
            filename = binary.poolfile.filename
             # Check for existing contents
            existingq = s.execute( "select 1 from bin_contents where binary_id=:id", {'id':binary.binary_id} );
            if existingq.fetchone():
                log.debug( "already imported: %s" % (filename))
            else:
                # We don't have existing contents so import them
                log.debug( "scanning: %s" % (filename) )

                debfile = os.path.join(pooldir, filename)
                if os.path.exists(debfile):
                    Binary(debfile, self.reject).scan_package(binary.binary_id, True)
                else:
                    log.error("missing .deb: %s" % filename)



    def bootstrap(self):
        """
        scan the existing debs in the pool to populate the contents database tables
        """
        pooldir = Config()[ 'Dir::Pool' ]

        s = DBConn().session()

        for suite in s.query(Suite).all():
            for arch in get_suite_architectures(suite.suite_name, skipsrc=True, skipall=True, session=s):
                q = s.query(BinAssociation).join(Suite)
                q = q.join(Suite).filter_by(suite_name=suite.suite_name)
                q = q.join(DBBinary).join(Architecture).filter_by(arch.arch_string)
                for ba in q:
                    filename = ba.binary.poolfile.filename
                    # Check for existing contents
                    existingq = s.query(ContentAssociations).filter_by(binary_pkg=ba.binary_id).limit(1)
                    if existingq.count() > 0:
                        log.debug( "already imported: %s" % (filename))
                    else:
                        # We don't have existing contents so import them
                        log.debug( "scanning: %s" % (filename) )
                        debfile = os.path.join(pooldir, filename)
                        if os.path.exists(debfile):
                            Binary(debfile, self.reject).scan_package(ba.binary_id, True)
                        else:
                            log.error("missing .deb: %s" % filename)


    def generate(self):
        """
        Generate Contents-$arch.gz files for every available arch in each given suite.
        """
        session = DBConn().session()

        arch_all_id = get_architecture("all", session).arch_id

        # The MORE fun part. Ok, udebs need their own contents files, udeb, and udeb-nf (not-free)
        # This is HORRIBLY debian specific :-/
        for dtype, section, fn_pattern in \
              [('deb',  None,                        "dists/%s/Contents-%s.gz"),
               ('udeb', "debian-installer",          "dists/%s/Contents-udeb-%s.gz"),
               ('udeb', "non-free/debian-installer", "dists/%s/Contents-udeb-nf-%s.gz")]:

            overridetype = get_override_type(dtype, session)

            # For udebs, we only look in certain sections (see the for loop above)
            if section is not None:
                section = get_section(section, session)

            # Get our suites
            for suite in which_suites():
                # Which architectures do we need to work on
                arch_list = get_suite_architectures(suite.suite_name, skipsrc=True, skipall=True, session=session)

                # Set up our file writer dictionary
                file_writers = {}
                try:
                    # One file writer per arch
                    for arch in arch_list:
                        file_writers[arch.arch_id] = GzippedContentWriter(fn_pattern % (suite, arch.arch_string))

                    for r in get_suite_contents(suite, overridetype, section, session=session).fetchall():
                        filename, section, package, arch_id = r

                        if arch_id == arch_all_id:
                            # It's arch all, so all contents files get it
                            for writer in file_writers.values():
                                writer.write(filename, section, package)
                        else:
                            if file_writers.has_key(arch_id):
                                file_writers[arch_id].write(filename, section, package)

                finally:
                    # close all the files
                    for writer in file_writers.values():
                        writer.finish()

################################################################################

def main():
    cnf = Config()

    arguments = [('h',"help", "%s::%s" % (options_prefix,"Help")),
                 ('s',"suite", "%s::%s" % (options_prefix,"Suite"),"HasArg"),
                 ('q',"quiet", "%s::%s" % (options_prefix,"Quiet")),
                 ('v',"verbose", "%s::%s" % (options_prefix,"Verbose")),
                ]

    commands = {'generate' : Contents.generate,
                'bootstrap_bin' : Contents.bootstrap_bin,
                'cruft' : Contents.cruft,
                }

    args = apt_pkg.ParseCommandLine(cnf.Cnf, arguments,sys.argv)

    if (len(args) < 1) or not commands.has_key(args[0]):
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

    commands[args[0]](Contents())

def which_suites(session):
    """
    return a list of suites to operate on
    """
    if Config().has_key( "%s::%s" %(options_prefix,"Suite")):
        suites = utils.split_args(Config()[ "%s::%s" %(options_prefix,"Suite")])
    else:
        suites = Config().SubTree("Suite").List()

    return [get_suite(s.lower(), session) for s in suites]


if __name__ == '__main__':
    main()
