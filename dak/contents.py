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
import traceback
import Queue
import apt_pkg
import datetime #just for debugging, can be removed
from daklib import utils
from daklib.binary import Binary
from daklib.config import Config
from daklib.dbconn import DBConn
################################################################################

log=None

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

#log = logging.getLogger()

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

# find me all of the contents for a given .deb
contents_q = """PREPARE contents_q(int,int) as
                SELECT file, section, package
                FROM deb_contents
                WHERE suite = $1
                AND (arch = $2 or arch=2)"""
#                ORDER BY file"""
                
# find me all of the contents for a given .udeb
udeb_contents_q = """PREPARE udeb_contents_q(int,int,text, int) as
                SELECT file, section, package, arch
                FROM udeb_contents
                WHERE suite = $1
                AND otype = $2
                AND section = $3
                and arch = $4
                ORDER BY file"""


# clear out all of the temporarily stored content associations
# this should be run only after p-a has run.  after a p-a
# run we should have either accepted or rejected every package
# so there should no longer be anything in the queue
remove_pending_contents_cruft_q = """DELETE FROM pending_content_associations"""

class EndOfContents(object):
    pass

class OneAtATime(object):
    """
    """
    def __init__(self):
        self.next_in_line = None
        self.next_lock = threading.Condition()

    def enqueue(self, next):
        self.next_lock.acquire()
        while self.next_in_line:
            self.next_lock.wait()
            
        assert( not self.next_in_line )
        self.next_in_line = next
        self.next_lock.notify()
        self.next_lock.release()

    def dequeue(self):
        self.next_lock.acquire()
        while not self.next_in_line:
            self.next_lock.wait()
        result = self.next_in_line
        self.next_in_line = None
        self.next_lock.notify()
        self.next_lock.release()
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
                 suite_id,
                 arch_str,
                 arch_id):

        self.filename = filename
        self.filenames = {}
        self.sorted_keys = None
        self.suite_str = suite_str
        self.suite_id = suite_id
        self.arch_str = arch_str
        self.arch_id = arch_id
        self.cursor = None
        self.filehandle = None

    def __str__(self):
        return self.filename
    __repr__ = __str__


    def cleanup(self):
        self.filenames = None
        self.sortedkeys = None
        self.filehandle.close()
        self.cursor.close()

    def query(self):
        self.cursor = DBConn().cursor();

        self.cursor.execute("""SELECT file, section || '/' || package
        FROM deb_contents
        WHERE ( arch=2 or arch = %d) AND suite = %d
        """ % (self.arch_id, self.suite_id))

    def ingest(self):
        while True:
            r = self.cursor.fetchone()
            if not r:
                break
            filename, package = r
            if self.filenames.has_key(filename):
                self.filenames[filename] += ",%s" % (package)
            else:
                self.filenames[filename] = "%s" % (package)
        self.cursor.close()

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
                    cursor1.execute( "SELECT 1 FROM deb_contents WHERE binary_id = %d LIMIT 1" % (deb[0] ) )
                    old = cursor1.fetchone()
                    if old:
                        log.log( "already imported: %s" % (deb[1]) )
                    else:
#                        log.debug( "scanning: %s" % (deb[1]) )
                        log.log( "scanning: %s" % (deb[1]) )
                        debfile = os.path.join( pooldir, deb[1] )
                        if os.path.exists( debfile ):
                            Binary(debfile, self.reject).scan_package(deb[0], True)
                        else:
                            log.error("missing .deb: %s" % deb[1])


    def generate(self):
        """
        Generate contents files for both deb and udeb
        """
        DBConn().prepare("arches_q", arches_q)
        self.deb_generate()
#        self.udeb_generate()

    def deb_generate(self):
        """
        Generate Contents-$arch.gz files for every available arch in each given suite.
        """
        cursor = DBConn().cursor()
        debtype_id = DBConn().get_override_type_id("deb")
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
            suite_id = DBConn().get_suite_id(suite)
            arch_list = self._arches(cursor, suite_id)

            for (arch_id,arch_str) in arch_list:
                print( "suite: %s, arch: %s time: %s" %(suite_id, arch_id, datetime.datetime.now().isoformat()) )

#                filename = "dists/%s/Contents-%s.gz" % (suite, arch_str)
                filename = "dists/%s/Contents-%s" % (suite, arch_str)
                cf = ContentFile(filename, suite, suite_id, arch_str, arch_id)
                inputtoquery.enqueue( cf )

        inputtoquery.enqueue( EndOfContents() )
        gt.join()

    def udeb_generate(self):
        """
        Generate Contents-$arch.gz files for every available arch in each given suite.
        """
        cursor = DBConn().cursor()

        DBConn().prepare("udeb_contents_q", udeb_contents_q)
        udebtype_id=DBConn().get_override_type_id("udeb")
        suites = self._suites()

#        for section, fn_pattern in [("debian-installer","dists/%s/Contents-udeb-%s.gz"),
#                                    ("non-free/debian-installer", "dists/%s/Contents-udeb-nf-%s.gz")]:

        for section, fn_pattern in [("debian-installer","dists/%s/Contents-udeb-%s"),
                                    ("non-free/debian-installer", "dists/%s/Contents-udeb-nf-%s")]:

            section_id = DBConn().get_section_id(section) # all udebs should be here)
            if section_id != -1:

                # Get our suites, and the architectures
                for suite in [i.lower() for i in suites]:
                    suite_id = DBConn().get_suite_id(suite)
                    arch_list = self._arches(cursor, suite_id)

                    for arch_id in arch_list:

                        writer = GzippedContentWriter(fn_pattern % (suite, arch_id[1]))
                        try:

                            cursor.execute("EXECUTE udeb_contents_q(%d,%d,%d)" % (suite_id, udebtype_id, section_id, arch_id))

                            while True:
                                r = cursor.fetchone()
                                if not r:
                                    break

                                filename, section, package, arch = r
                                writer.write(filename, section, package)
                        finally:
                            writer.close()



################################################################################

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
#    log = logging.Logger(cnf, "contents")
                         
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

#     level=logging.INFO
#     if cnf.has_key("%s::%s" % (options_prefix,"Quiet")):
#         level=logging.ERROR

#     elif cnf.has_key("%s::%s" % (options_prefix,"Verbose")):
#         level=logging.DEBUG


#     logging.basicConfig( level=level,
#                          format='%(asctime)s %(levelname)s %(message)s',
#                          stream = sys.stderr )

    commands[args[0]](Contents())

if __name__ == '__main__':
    main()
