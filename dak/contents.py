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
import math
import gzip
import threading
import Queue
import apt_pkg
from daklib import utils
from daklib.binary import Binary
from daklib.config import Config
from daklib.dbconn import DBConn
################################################################################

def usage (exit_code=0):
    print """Usage: dak contents [options] command [arguments]

COMMANDS
    generate
        generate Contents-$arch.gz files

    bootstrap
        scan the debs in the existing pool and load contents in the the database

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

# get all the arches delivered for a given suite
# this should probably exist somehere common
arches_q = """PREPARE arches_q(int) as
              SELECT s.architecture, a.arch_string
              FROM suite_architectures s
              JOIN architecture a ON (s.architecture=a.id)
                  WHERE suite = $1"""

# find me the .deb for a given binary id
debs_q = """PREPARE debs_q(int, int) as
              SELECT b.id, f.filename FROM bin_assoc_by_arch baa
              JOIN binaries b ON baa.bin=b.id
              JOIN files f ON b.file=f.id
              WHERE suite = $1
                  AND arch = $2"""

# ask if we already have contents associated with this binary
olddeb_q = """PREPARE olddeb_q(int) as
              SELECT 1 FROM content_associations
              WHERE binary_pkg = $1
              LIMIT 1"""

# find me all of the contents for a given .deb
contents_q = """PREPARE contents_q(int,int) as
                SELECT (p.path||'/'||n.file) AS fn,
                        s.section,
                        b.package,
                        b.architecture
               FROM content_associations c join content_file_paths p ON (c.filepath=p.id)
               JOIN content_file_names n ON (c.filename=n.id)
               JOIN binaries b ON (b.id=c.binary_pkg)
               JOIN override o ON (o.package=b.package)
               JOIN section s ON (s.id=o.section)
               WHERE o.suite = $1 AND o.type = $2
               AND b.type='deb'
               ORDER BY fn"""

# find me all of the contents for a given .udeb
udeb_contents_q = """PREPARE udeb_contents_q(int,int,int) as
              SELECT (p.path||'/'||n.file) AS fn,
                        s.section,
                        b.package,
                        b.architecture
               FROM content_associations c join content_file_paths p ON (c.filepath=p.id)
               JOIN content_file_names n ON (c.filename=n.id)
               JOIN binaries b ON (b.id=c.binary_pkg)
               JOIN override o ON (o.package=b.package)
               JOIN section s ON (s.id=o.section)
               WHERE o.suite = $1 AND o.type = $2
               AND s.id = $3
               AND b.type='udeb'
               ORDER BY fn"""

#               FROM content_file_paths p join content_associations c ON (c.filepath=p.id)
#               JOIN content_file_names n ON (c.filename=n.id)
#               JOIN binaries b ON (b.id=c.binary_pkg)
#               JOIN override o ON (o.package=b.package)
#               JOIN section s ON (s.id=o.section)
#               WHERE o.suite = $1 AND o.type = $2
#               AND s.id = $3
#               AND b.id in (SELECT ba.bin from bin_associations ba join binaries b on b.id=ba.bin where (b.architecture=$3 or b.architecture=$4)and ba.suite=$1 and b.type='udeb')
#               GROUP BY fn
#               ORDER BY fn;"""



# clear out all of the temporarily stored content associations
# this should be run only after p-a has run.  after a p-a
# run we should have either accepted or rejected every package
# so there should no longer be anything in the queue
remove_pending_contents_cruft_q = """DELETE FROM pending_content_associations"""

# delete any filenames we are storing which have no binary associated with them
remove_filename_cruft_q = """DELETE FROM content_file_names
                             WHERE id IN (SELECT cfn.id FROM content_file_names cfn
                                          LEFT JOIN content_associations ca
                                            ON ca.filename=cfn.id
                                          WHERE ca.id IS NULL)"""

# delete any paths we are storing which have no binary associated with them
remove_filepath_cruft_q = """DELETE FROM content_file_paths
                             WHERE id IN (SELECT cfn.id FROM content_file_paths cfn
                                          LEFT JOIN content_associations ca
                                             ON ca.filepath=cfn.id
                                          WHERE ca.id IS NULL)"""

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
        @ptype filename: string
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

    Usage GenerateContents().generateContents( ["main","contrib","non-free"] )
    """

    def __init__(self):
        self.header = None

    def reject(self, message):
        log.error("E: %s" % message)

    # goal column for section column
    _goal_column = 54

    def cruft(self):
        """
        remove files/paths from the DB which are no longer referenced
        by binaries and clean the temporary table
        """
        cursor = DBConn().cursor();
        cursor.execute( "BEGIN WORK" )
        cursor.execute( remove_pending_contents_cruft_q )
        cursor.execute( remove_filename_cruft_q )
        cursor.execute( remove_filepath_cruft_q )
        cursor.execute( "COMMIT" )


    def bootstrap(self):
        """
        scan the existing debs in the pool to populate the contents database tables
        """
        pooldir = Config()[ 'Dir::Pool' ]

        cursor = DBConn().cursor();
        DBConn().prepare("debs_q",debs_q)
        DBConn().prepare("olddeb_q",olddeb_q)
        DBConn().prepare("arches_q",arches_q)

        suites = self._suites()
        for suite in [i.lower() for i in suites]:
            suite_id = DBConn().get_suite_id(suite)

            arch_list = self._arches(cursor, suite_id)
            arch_all_id = DBConn().get_architecture_id("all")
            for arch_id in arch_list:
                cursor.execute( "EXECUTE debs_q(%d, %d)" % ( suite_id, arch_id[0] ) )

                count = 0
                while True:
                    deb = cursor.fetchone()
                    if not deb:
                        break
                    count += 1
                    cursor1 = DBConn().cursor();
                    cursor1.execute( "EXECUTE olddeb_q(%d)" % (deb[0] ) )
                    old = cursor1.fetchone()
                    if old:
                        log.debug( "already imported: %s" % (deb[1]) )
                    else:
                        log.debug( "scanning: %s" % (deb[1]) )
                        debfile = os.path.join( pooldir, deb[1] )
                        if os.path.exists( debfile ):
                            Binary(debfile, self.reject).scan_package(deb[0],True)
                        else:
                            log.error("missing .deb: %s" % deb[1])

    def generate(self):
        """
        Generate Contents-$arch.gz files for every available arch in each given suite.
        """
        cursor = DBConn().cursor()

        DBConn().prepare("arches_q", arches_q)
        DBConn().prepare("contents_q", contents_q)
        DBConn().prepare("udeb_contents_q", udeb_contents_q)

        debtype_id=DBConn().get_override_type_id("deb")
        udebtype_id=DBConn().get_override_type_id("udeb")

        arch_all_id = DBConn().get_architecture_id("all")
        suites = self._suites()


        # Get our suites, and the architectures
        for suite in [i.lower() for i in suites]:
            suite_id = DBConn().get_suite_id(suite)
            arch_list = self._arches(cursor, suite_id)

            file_writers = {}

            try:
                for arch_id in arch_list:
                    file_writers[arch_id[0]] = GzippedContentWriter("dists/%s/Contents-%s.gz" % (suite, arch_id[1]))

                cursor.execute("EXECUTE contents_q(%d,%d);" % (suite_id, debtype_id))

                while True:
                    r = cursor.fetchone()
                    if not r:
                        break

                    filename, section, package, arch = r

                    if not file_writers.has_key( arch ):
                        continue

                    if arch == arch_all_id:
                        ## its arch all, so all contents files get it
                        for writer in file_writers.values():
                            writer.write(filename, section, package)

                    else:
                        file_writers[arch].write(filename, section, package)

            finally:
                # close all the files
                for writer in file_writers.values():
                    writer.finish()


            # The MORE fun part. Ok, udebs need their own contents files, udeb, and udeb-nf (not-free)
            # This is HORRIBLY debian specific :-/
        for section, fn_pattern in [("debian-installer","dists/%s/Contents-udeb-%s.gz"),
                                    ("non-free/debian-installer", "dists/%s/Contents-udeb-nf-%s.gz")]:

            section_id = DBConn().get_section_id(section) # all udebs should be here)
            if section_id != -1:

                # Get our suites, and the architectures
                for suite in [i.lower() for i in suites]:
                    suite_id = DBConn().get_suite_id(suite)
                    arch_list = self._arches(cursor, suite_id)

                    file_writers = {}

                    try:
                        for arch_id in arch_list:
                            file_writers[arch_id[0]] = GzippedContentWriter(fn_pattern % (suite, arch_id[1]))

                        cursor.execute("EXECUTE udeb_contents_q(%d,%d,%d)" % (suite_id, udebtype_id, section_id))

                        while True:
                            r = cursor.fetchone()
                            if not r:
                                break

                            filename, section, package, arch = r

                            if not file_writers.has_key( arch ):
                                continue

                            if arch == arch_all_id:
                                ## its arch all, so all contents files get it
                                for writer in file_writers.values():
                                    writer.write(filename, section, package)

                            else:
                                file_writers[arch].write(filename, section, package)
                    finally:
                        # close all the files
                        for writer in file_writers.values():
                            writer.finish()



################################################################################

    def _suites(self):
        """
        return a list of suites to operate on
        """
        if Config().has_key( "%s::%s" %(options_prefix,"Suite")):
            suites = utils.split_args(Config()[ "%s::%s" %(options_prefix,"Suite")])
        else:
            suites = Config().SubTree("Suite").List()

        return suites

    def _arches(self, cursor, suite):
        """
        return a list of archs to operate on
        """
        arch_list = []
        cursor.execute("EXECUTE arches_q(%d)" % (suite))
        while True:
            r = cursor.fetchone()
            if not r:
                break

            if r[1] != "source" and r[1] != "all":
                arch_list.append((r[0], r[1]))

        return arch_list

################################################################################


def main():
    cnf = Config()

    arguments = [('h',"help", "%s::%s" % (options_prefix,"Help")),
                 ('s',"suite", "%s::%s" % (options_prefix,"Suite"),"HasArg"),
                 ('q',"quiet", "%s::%s" % (options_prefix,"Quiet")),
                 ('v',"verbose", "%s::%s" % (options_prefix,"Verbose")),
                ]

    commands = {'generate' : Contents.generate,
                'bootstrap' : Contents.bootstrap,
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

if __name__ == '__main__':
    main()
