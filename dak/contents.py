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
import tempfile
import logging
import math
import gzip
import apt_pkg
from daklib import utils
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
        only operate on a signle suite

     -a, --arch={i386,amd64}
        only operate on a signle architecture
"""
    sys.exit(exit_code)

################################################################################

# where in dak.conf all of our configuration will be stowed

options_prefix = "Contents"
options_prefix = "%s::Opitons" % options_prefix

log = logging.getLogger()

################################################################################

# we unfortunately still have broken stuff in headers
latin1_q = """SET CLIENT_ENCODING TO 'LATIN1'"""

# get all the arches delivered for a given suite
# this should probably exist somehere common
arches_q = """PREPARE arches_q as
              SELECT s.architecture, a.arch_string
              FROM suite_architectures s
              JOIN architecture a ON (s.architecture=a.id)
                  WHERE suite = $1"""

# find me the .deb for a given binary id
debs_q = """PREPARE debs_q as
              SELECT b.id, f.filename FROM bin_assoc_by_arch baa
              JOIN binaries b ON baa.bin=b.id
              JOIN files f ON b.file=f.id
              WHERE suite = $1
                  AND arch = $2"""

# ask if we already have contents associated with this binary
olddeb_q = """PREPARE olddeb_q as
              SELECT 1 FROM content_associations
              WHERE binary_pkg = $1
              LIMIT 1"""

# find me all of the contents for a given .deb
contents_q = """PREPARE contents_q as
              SELECT (p.path||'/'||n.file) AS fn,
                      comma_separated_list(s.section||'/'||b.package)
              FROM content_associations c
              JOIN content_file_paths p ON (c.filepath=p.id)
              JOIN content_file_names n ON (c.filename=n.id)
              JOIN binaries b ON (b.id=c.binary_pkg)
              JOIN bin_associations ba ON (b.id=ba.bin)
              JOIN override o ON (o.package=b.package)
              JOIN section s ON (s.id=o.section)
              WHERE (b.architecture = $1 OR b.architecture = $2)
                  AND ba.suite = $3
                  AND o.suite = $4
                  AND b.type = 'deb'
                  AND o.type = '7'
              GROUP BY fn
              ORDER BY fn"""

# find me all of the contents for a given .udeb
udeb_contents_q = """PREPARE udeb_contents_q as
              SELECT (p.path||'/'||n.file) as fn,
                      comma_separated_list(s.section||'/'||b.package)
              FROM content_associations c
              JOIN content_file_paths p ON (c.filepath=p.id)
              JOIN content_file_names n ON (c.filename=n.id)
              JOIN binaries b ON (b.id=c.binary_pkg)
              JOIN bin_associations ba ON (b.id=ba.bin)
              JOIN override o ON (o.package=b.package)
              JOIN section s ON (s.id=o.section)
              WHERE s.id = $1
                  AND ba.suite = $2
                  AND o.suite = $3
                  AND b.type = 'udeb'
                  AND o.type = '8'
              GROUP BY fn
              ORDER BY fn"""

# clear out all of the temporarily stored content associations
# this should be run only after p-a has run.  after a p-a
# run we should have either accepted or rejected every package
# so there should no longer be anything in the queue
remove_temp_contents_cruft_q = """DELETE FROM temp_content_associations"""

# delete any filenames we are storing which have no binary associated with them
remove_filename_cruft_q = """DELETE FROM content_file_names
                             WHERE id IN (SELECT cfn.id FROM content_file_names cfn
                                          LEFT JOIN content_associations ca
                                            ON ca.filename=cfn.id
                                          WHERE ca.id IS NULL)""" );

# delete any paths we are storing which have no binary associated with them
remove_filepath_cruft_q = """DELETE FROM content_file_paths
                             WHERE id IN (SELECT cfn.id FROM content_file_paths cfn
                                          LEFT JOIN content_associations ca
                                             ON ca.filepath=cfn.id
                                          WHERE ca.id IS NULL)"""
class Contents(object):
    """
    Class capable of generating Contents-$arch.gz files

    Usage GenerateContents().generateContents( ["main","contrib","non-free"] )
    """

    def __init__(self):
        self.header = None

    def _getHeader(self):
        """
        Internal method to return the header for Contents.gz files

        This is boilerplate which explains the contents of the file and how
        it can be used.
        """
        if self.header == None:
            if Config().has_key("Contents::Header"):
                try:
                    h = open(os.path.join( Config()["Dir::Templates"],
                                           Config()["Contents::Header"] ), "r")
                    self.header = h.read()
                    print( "header: %s" % self.header )
                    h.close()
                except:
                    log.error( "error opening header file: %d\n%s" % (Config()["Contents::Header"],
                                                                      traceback.format_exc() ))
                    self.header = False
            else:
                print( "no header" )
                self.header = False

        return self.header

    # goal column for section column
    _goal_column = 54

    def _write_content_file(self, cursor, filename):
        """
        Internal method for writing all the results to a given file.
        The cursor should have a result set generated from a query already.
        """
        f = gzip.open(Config()["Dir::Root"] + filename, "w")
        try:
            header = self._getHeader()

            if header:
                f.write(header)

            while True:
                contents = cursor.fetchone()
                if not contents:
                    return

                num_tabs = max(1,
                               int( math.ceil( (self._goal_column - len(contents[0])) / 8) ) )
                f.write(contents[0] + ( '\t' * num_tabs ) + contents[-1] + "\n")

        finally:
            f.close()

    def cruft(self):
        """
        remove files/paths from the DB which are no longer referenced
        by binaries and clean the temporary table
        """
        cursor = DBConn().cursor();
        cursor.execute( "BEGIN WORK" )
        cursor.execute( remove_temp_contents_cruft_q )
        cursor.execute( remove_filename_cruft_q )
        cursor.execute( remove_filepath_cruft_q )
        cursor.execute( "COMMIT" )


    def bootstrap(self):
        """
        scan the existing debs in the pool to populate the contents database tables
        """
        pooldir = Config()[ 'Dir::Pool' ]

        cursor = DBConn().cursor();
        cursor.execute( latin1_q )
        cursor.execute( debs_q )
        cursor.execute( olddeb_q )
        cursor.execute( arches_q )

        suites = self._suites()
        for suite in [i.lower() for i in suites]:
            suite_id = DBConn().get_suite_id(suite)

            arch_list = self._arches(cursor, suite_id)
            arch_all_id = DBConn().get_architecture_id("all")
            for arch_id in arch_list:
                cursor.execute( "EXECUTE debs_q(%d, %d)" % ( suite_id, arch_id[0] ) )

                debs = cursor.fetchall()
                count = 0
                for deb in debs:
                    count += 1
                    cursor.execute( "EXECUTE olddeb_q(%d)" % (deb[0] ) )
                    old = cursor.fetchone()
                    if old:
                        log.debug( "already imported: %s" % deb[1] )
                    else:
                        debfile = os.path.join( pooldir, deb[1] )
                        if os.path.exists( debfile ):
                            contents = utils.generate_contents_information( debfile )
                            DBConn().insert_content_paths(deb[0], contents)
                            log.info( "imported (%d/%d): %s" % (count,len(debs),deb[1] ) )
                        else:
                            log.error( "missing .deb: %s" % deb[1] )

    def generate(self):
        """
        Generate Contents-$arch.gz files for every aviailable arch in each given suite.
        """
        cursor = DBConn().cursor();

        cursor.execute( arches_q )
        cursor.execute( contents_q )
        cursor.execute( udeb_contents_q )

        suites = self._suites()

        # Get our suites, and the architectures
        for suite in [i.lower() for i in suites]:
            suite_id = DBConn().get_suite_id(suite)
            arch_list = self._arches(cursor, suite_id)

            arch_all_id = DBConn().get_architecture_id("all")

            for arch_id in arch_list:
                cursor.execute( "EXECUTE contents_q(%d,%d,%d,%d)" % (arch_id[0], arch_all_id, suite_id, suite_id))
                self._write_content_file(cursor, "dists/%s/Contents-%s.gz" % (suite, arch_id[1]))

            # The MORE fun part. Ok, udebs need their own contents files, udeb, and udeb-nf (not-free)
            # This is HORRIBLY debian specific :-/
            # First off, udeb
            section_id = DBConn().get_section_id('debian-installer') # all udebs should be here)
            if section_id != -1:
                cursor.execute("EXECUTE udeb_contents_q(%d,%d,%d)" % (section_id, suite_id, suite_id))
                self._write_content_file(cursor, "dists/%s/Contents-udeb.gz" % suite)

            # Once more, with non-free
            section_id = DBConn().get_section_id('non-free/debian-installer') # all udebs should be here)

            if section_id != -1:
                cursor.execute("EXECUTE udeb_contents_q(%d,%d,%d)" % (section_id, suite_id, suite_id))
                self._write_content_file(cursor, "dists/%s/Contents-udeb-nf.gz" % suite)


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
        arch_list = [ ]
        if Config().has_key( "%s::%s" %(options_prefix,"Arch")):
            archs = utils.split_args(Config()[ "%s::%s" %(options_prefix,"Arch")])
            for arch_name in archs:
                arch_list.append((DBConn().get_architecture_id(arch_name), arch_name))
        else:
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
                 ('a',"arch", "%s::%s" % (options_prefix,"Arch"),"HasArg"),
                ]

    commands = {'generate' : Contents.generate,
                'bootstrap' : Contents.bootstrap,
                'cruft' : Contents.cruft,
                }

    level=logging.INFO
    if cnf.has_key("%s::%s" % (options_prefix,"Quiet")):
        level=logging.ERROR

    elif cnf.has_key("%s::%s" % (options_prefix,"Verbose")):
        level=logging.DEBUG


    logging.basicConfig( level=level,
                         format='%(asctime)s %(levelname)s %(message)s',
                         stream = sys.stderr )

    args = apt_pkg.ParseCommandLine(cnf.Cnf, arguments,sys.argv)

    if (len(args) < 1) or not commands.has_key(args[0]):
        usage()

    if cnf.has_key("%s::%s" % (options_prefix,"Help")):
        usage()

    commands[args[0]](Contents())

if __name__ == '__main__':
    main()
