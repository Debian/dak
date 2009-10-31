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
import Queue
import apt_pkg
import datetime
import traceback
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

    bootstrap
        copy data from the bin_contents table into the deb_contents / udeb_contents tables

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

        return result


class ContentsWorkThread(threading.Thread):
    """
    """
    def __init__(self, upstream, downstream):
        threading.Thread.__init__(self)
        self.upstream = upstream
        self.downstream = downstream

    def run(self):
        while True:
            try:
                contents_file = self.upstream.dequeue()
                if isinstance(contents_file,EndOfContents):
                    if self.downstream:
                        self.downstream.enqueue(contents_file)
                    break

                s = datetime.datetime.now()
                print("%s start: %s" % (self,contents_file) )
                self._run(contents_file)
                print("%s finished: %s in %d seconds" % (self, contents_file, (datetime.datetime.now()-s).seconds ))
                if self.downstream:
                    self.downstream.enqueue(contents_file)
            except:
                traceback.print_exc()

class QueryThread(ContentsWorkThread):
    def __init__(self, upstream, downstream):
        ContentsWorkThread.__init__(self, upstream, downstream)

    def __str__(self):
        return "QueryThread"
    __repr__ = __str__

    def _run(self, contents_file):
        contents_file.query()

class IngestThread(ContentsWorkThread):
    def __init__(self, upstream, downstream):
        ContentsWorkThread.__init__(self, upstream, downstream)

    def __str__(self):
        return "IngestThread"
    __repr__ = __str__

    def _run(self, contents_file):
        contents_file.ingest()

class SortThread(ContentsWorkThread):
    def __init__(self, upstream, downstream):
        ContentsWorkThread.__init__(self, upstream, downstream)

    def __str__(self):
        return "SortThread"
    __repr__ = __str__

    def _run(self, contents_file):
        contents_file.sorted_keys = sorted(contents_file.filenames.keys())

class OutputThread(ContentsWorkThread):
    def __init__(self, upstream, downstream):
        ContentsWorkThread.__init__(self, upstream, downstream)

    def __str__(self):
        return "OutputThread"
    __repr__ = __str__

    def _run(self, contents_file):
        contents_file.open_file()
        for fname in contents_file.sorted_keys:
            contents_file.filehandle.write("%s\t%s\n" % (fname,contents_file.filenames[fname]))
        contents_file.sorted_keys = None
        contents_file.filenames.clear()
    
class GzipThread(ContentsWorkThread):
    def __init__(self, upstream, downstream):
        ContentsWorkThread.__init__(self, upstream, downstream)

    def __str__(self):
        return "GzipThread"
    __repr__ = __str__

    def _run(self, contents_file):
        os.system("gzip -f %s" % contents_file.filename)

class ContentFile(object):
    def __init__(self,
                 filename,
                 suite_str,
                 suite_id):

        self.filename = filename
        self.filenames = {}
        self.sorted_keys = None
        self.suite_str = suite_str
        self.suite_id = suite_id
        self.session = None
        self.filehandle = None
        self.results = None

    def __str__(self):
        return self.filename
    __repr__ = __str__


    def cleanup(self):
        self.filenames = None
        self.sortedkeys = None
        self.filehandle.close()
        self.session.close()

    def ingest(self):
        while True:
            r = self.results.fetchone()
            if not r:
                break
            filename, package = r
            self.filenames[filename]=package

        self.session.close()

#     def ingest(self):
#         while True:
#             r = self.results.fetchone()
#             if not r:
#                 break
#             filename, package = r
#             if self.filenames.has_key(filename):
#                 self.filenames[filename] += ",%s" % (package)
#             else:
#                 self.filenames[filename] = "%s" % (package)
#         self.session.close()

    def open_file(self):
        """
        opens a gzip stream to the contents file
        """
#        filepath = Config()["Contents::Root"] + self.filename
        self.filename = "/home/stew/contents/" + self.filename
        filedir = os.path.dirname(self.filename)
        if not os.path.isdir(filedir):
            os.makedirs(filedir)
#        self.filehandle = gzip.open(self.filename, "w")
        self.filehandle = open(self.filename, "w")
        self._write_header()

    def _write_header(self):
        self._get_header();
        self.filehandle.write(ContentFile.header)

    header=None

    @classmethod
    def _get_header(self):
        """
        Internal method to return the header for Contents.gz files

        This is boilerplate which explains the contents of the file and how
        it can be used.
        """
        if not ContentFile.header:
            if Config().has_key("Contents::Header"):
                try:
                    h = open(os.path.join( Config()["Dir::Templates"],
                                           Config()["Contents::Header"] ), "r")
                    ContentFile.header = h.read()
                    h.close()
                except:
                    log.error( "error opening header file: %d\n%s" % (Config()["Contents::Header"],
                                                                      traceback.format_exc() ))
                    ContentFile.header = None
            else:
                ContentFile.header = None

        return ContentFile.header


class DebContentFile(ContentFile):
    def __init__(self,
                 filename,
                 suite_str,
                 suite_id,
                 arch_str,
                 arch_id):
        ContentFile.__init__(self,
                             filename,
                             suite_str,
                             suite_id )
        self.arch_str = arch_str
        self.arch_id = arch_id

    def query(self):
        self.session = DBConn().session();

        self.results = self.session.execute("""SELECT filename, comma_separated_list(section || '/' || package)
        FROM deb_contents
        WHERE ( arch=2 or arch = :arch) AND suite = :suite
        """, { 'arch':self.arch_id, 'suite':self.suite_id } )

class UdebContentFile(ContentFile):
    def __init__(self,
                 filename,
                 suite_str,
                 suite_id,
                 section_name,
                 section_id):
        ContentFile.__init__(self,
                             filename,
                             suite_str,
                             suite_id )

    def query(self):
        self.session = DBConn().session();

        self.results = self.session.execute("""SELECT filename, comma_separated_list(section || '/' || package)
        FROM udeb_contents
        WHERE suite = :suite
        group by filename
        """ , { 'suite': self.suite_id } )

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

        for binary in s.query(DBBinary).yield_per(100):
            print( "binary: %s" % binary.package )
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
        s = DBConn().session()


        # get a mapping of all the override types we care about (right now .deb an .udeb)
        override_type_map = {};
        for override_type in s.query(OverrideType).all():
            if override_type.overridetype.endswith('deb' ):
                override_type_map[override_type.overridetype_id] = override_type.overridetype;

        for override in s.query(Override).yield_per(100):
            if not override_type_map.has_key(override.overridetype_id):
                #this isn't an override we care about
                continue

            binaries = s.execute("""SELECT b.id, b.architecture
                                    FROM binaries b
                                    JOIN bin_associations ba ON ba.bin=b.id
                                    WHERE ba.suite=:suite
                                    AND b.package=:package""", {'suite':override.suite_id, 'package':override.package})
            while True:
                binary = binaries.fetchone()
                if not binary:
                    break

                exists = s.execute("SELECT 1 FROM %s_contents WHERE binary_id=:id limit 1" % override_type_map[override.overridetype_id], {'id':binary.id})


                if exists.fetchone():
                    print '.',
                    continue
                else:
                    print '+',

                s.execute( """INSERT INTO %s_contents (filename,section,package,binary_id,arch,suite)
                              SELECT file, :section, :package, :binary_id, :arch, :suite
                              FROM bin_contents
                              WHERE binary_id=:binary_id;""" % override_type_map[override.overridetype_id],
                           { 'section' : override.section_id,
                             'package' : override.package,
                             'binary_id' : binary.id,
                             'arch' : binary.architecture,
                             'suite' : override.suite_id } )
                s.commit()

    def generate(self):
        """
        Generate contents files for both deb and udeb
        """
        self.deb_generate()
#        self.udeb_generate()

    def deb_generate(self):
        """
        Generate Contents-$arch.gz files for every available arch in each given suite.
        """
        session = DBConn().session()
        debtype_id = get_override_type("deb", session)
        suites = self._suites()

        inputtoquery = OneAtATime()
        querytoingest = OneAtATime()
        ingesttosort = OneAtATime()
        sorttooutput = OneAtATime()
        outputtogzip = OneAtATime()

        qt = QueryThread(inputtoquery,querytoingest)
        it = IngestThread(querytoingest,ingesttosort)
# these actually make things worse
#        it2 = IngestThread(querytoingest,ingesttosort)
#        it3 = IngestThread(querytoingest,ingesttosort)
#        it4 = IngestThread(querytoingest,ingesttosort)
        st = SortThread(ingesttosort,sorttooutput)
        ot = OutputThread(sorttooutput,outputtogzip)
        gt = GzipThread(outputtogzip, None)

        qt.start()
        it.start()
#        it2.start()
#        it3.start()
#        it2.start()
        st.start()
        ot.start()
        gt.start()
        
        # Get our suites, and the architectures
        for suite in [i.lower() for i in suites]:
            suite_id = get_suite(suite, session).suite_id
            print( "got suite_id: %s for suite: %s" % (suite_id, suite ) )
            arch_list = self._arches(suite_id, session)

            for (arch_id,arch_str) in arch_list:
                print( "suite: %s, arch: %s time: %s" %(suite_id, arch_id, datetime.datetime.now().isoformat()) )

#                filename = "dists/%s/Contents-%s.gz" % (suite, arch_str)
                filename = "dists/%s/Contents-%s" % (suite, arch_str)
                cf = DebContentFile(filename, suite, suite_id, arch_str, arch_id)
                inputtoquery.enqueue( cf )

        inputtoquery.enqueue( EndOfContents() )
        gt.join()

    def udeb_generate(self):
        """
        Generate Contents-$arch.gz files for every available arch in each given suite.
        """
        session = DBConn().session()
        udebtype_id=DBConn().get_override_type_id("udeb")
        suites = self._suites()

        inputtoquery = OneAtATime()
        querytoingest = OneAtATime()
        ingesttosort = OneAtATime()
        sorttooutput = OneAtATime()
        outputtogzip = OneAtATime()

        qt = QueryThread(inputtoquery,querytoingest)
        it = IngestThread(querytoingest,ingesttosort)
# these actually make things worse
#        it2 = IngestThread(querytoingest,ingesttosort)
#        it3 = IngestThread(querytoingest,ingesttosort)
#        it4 = IngestThread(querytoingest,ingesttosort)
        st = SortThread(ingesttosort,sorttooutput)
        ot = OutputThread(sorttooutput,outputtogzip)
        gt = GzipThread(outputtogzip, None)

        qt.start()
        it.start()
#        it2.start()
#        it3.start()
#        it2.start()
        st.start()
        ot.start()
        gt.start()
        
#        for section, fn_pattern in [("debian-installer","dists/%s/Contents-udeb-%s"),
#                                     ("non-free/debian-installer", "dists/%s/Contents-udeb-nf-%s")]:

#             section_id = DBConn().get_section_id(section) # all udebs should be here)
#             if section_id != -1:

                

#                 # Get our suites, and the architectures
#                 for suite in [i.lower() for i in suites]:
#                     suite_id = DBConn().get_suite_id(suite)
#                     arch_list = self._arches(suite_id, session)

#                     for arch_id in arch_list:

#                         writer = GzippedContentWriter(fn_pattern % (suite, arch_id[1]))
#                         try:

#                             results = session.execute("EXECUTE udeb_contents_q(%d,%d,%d)" % (suite_id, udebtype_id, section_id, arch_id))

#                             while True:
#                                 r = cursor.fetchone()
#                                 if not r:
#                                     break

#                                 filename, section, package, arch = r
#                                 writer.write(filename, section, package)
#                         finally:
#                             writer.close()




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
            for suite in which_suites(session):
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
    def _suites(self):
        """
        return a list of suites to operate on
        """
        if Config().has_key( "%s::%s" %(options_prefix,"Suite")):
            suites = utils.split_args(Config()[ "%s::%s" %(options_prefix,"Suite")])
        else:
            suites = [ 'unstable', 'testing' ]
#            suites = Config().SubTree("Suite").List()

        return suites

    def _arches(self, suite, session):
        """
        return a list of archs to operate on
        """
        arch_list = []
        arches = session.execute(
            """SELECT s.architecture, a.arch_string
            FROM suite_architectures s
            JOIN architecture a ON (s.architecture=a.id)
            WHERE suite = :suite_id""",
            {'suite_id':suite } )

        while True:
            r = arches.fetchone()
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

    commands = {'generate' : Contents.deb_generate,
                'bootstrap_bin' : Contents.bootstrap_bin,
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
