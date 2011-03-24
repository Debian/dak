#!/usr/bin/env python

""" Create all the Release files

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2011  Joerg Jaspert <joerg@debian.org>
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

# <mhy> I wish they wouldnt leave biscuits out, thats just tempting. Damnit.

################################################################################

import sys
import os
import os.path
import stat
import time
import gzip
import bz2
import apt_pkg
from tempfile import mkstemp, mkdtemp
import commands
from multiprocessing import Pool, TimeoutError

from daklib import utils, daklog
from daklib.regexes import re_getsarelease, re_includeinarelease
from daklib.dak_exceptions import *
from daklib.dbconn import *
from daklib.config import Config

################################################################################
Options = None                 #: Commandline arguments parsed into this
Logger = None                  #: Our logging object
results = []                   #: Results of the subprocesses

################################################################################

def usage (exit_code=0):
    """ Usage information"""

    print """Usage: dak generate-releases [OPTIONS]
Generate the Release files

  -s, --suite=SUITE(s)       process this suite
                             Default: All suites not marked 'untouchable'
  -f, --force                Allow processing of untouchable suites
                             CAREFUL: Only to be used at (point) release time!
  -h, --help                 show this help and exit

SUITE can be a space seperated list, e.g.
   --suite=unstable testing
  """
    sys.exit(exit_code)

########################################################################

def get_result(arg):
    global results
    if arg:
        results.append(arg)

## FIXME: Hardcoded for now. This needs to go via database, but mhy is working on that part.
##        until that is done, we just hardcode it here.
SC = { "unstable": ("main", "contrib", "non-free"),
       "oldstable": ("main", "contrib", "non-free"),
       "testing": ("main", "contrib", "non-free"),
       "testing-proposed-updates": ("main", "contrib", "non-free"),
       "experimental": ("main", "contrib", "non-free"),
       "proposed-updates": ("main", "contrib", "non-free"),
       "oldstable-proposed-updates": ("main", "contrib", "non-free"),
       "squeeze-updates": ("main", "contrib", "non-free"),
       "stable": ("main", "contrib", "non-free"),
       "squeeze-backports": ("main", "contrib", "non-free"),
       "lenny-backports": ("main", "contrib", "non-free"),
       "lenny-backports-sloppy": ("main", "contrib", "non-free"),
       }


def generate_release_files(suite, tmppath):
    """
    Generate Release files for the given suite

    @type suite: string
    @param suite: Suite name

    @type tmppath: string
    @param tmppath: The temporary path to work in
    """

    architectures = get_suite_architectures(suite.suite_name, skipall=True, skipsrc=True)

    # Attribs contains a list of field names to fetch from suite table. Should the entry in the
    # suite table be named differently, |realname will help it out.
    attribs = ( ('Origin', 'origin'), ('Label', 'label'), ('Suite', 'suite_name'),
                ('Version', 'version'), ('Codename', 'codename'), ('Description', 'description'))
    # A "Sub" Release file has slightly different fields
    subattribs=( ('Origin', 'origin'), ('Label', 'label'), ('Archive', 'suite_name'),
                 ('Version', 'version'))
    # Boolean stuff. If we find it true in database, write out "yes" into the release file
    boolattrs=('notautomatic', 'butautomaticupgrades')
    KEYWORD = 0
    DBFIELD = 1

    cnf = Config()

    outfile=os.path.join(cnf["Dir::Root"], suite.suite_name, "Release")
    print "Working on: %s" % (outfile)
#    out = open(outfile, "w")
    out = open("/tmp/lala", "w")

    for key in attribs:
        if getattr(suite, key[DBFIELD]) is None:
            continue
        out.write("%s: %s\n" % (key[KEYWORD], getattr(suite, key[DBFIELD])))

    out.write("Date: %s\n" % (time.strftime("%a, %d %b %Y %H:%M:%S UTC", time.gmtime(time.time()))))
    if suite.validtime:
        validtime=float(suite.validtime)
        out.write("Valid-Until: %s\n" % (time.strftime("%a, %d %b %Y %H:%M:%S UTC", time.gmtime(time.time()+validtime))))

    for key in boolattrs:
        if hasattr(suite, key):
            if getattr(suite, key):
                out.write("%s: yes\n" % (key.capitalize()))
    out.write("Architectures: %s\n" % (" ".join([a.arch_string for a in architectures])))
    suite_suffix = "%s" % (cnf.Find("Dinstall::SuiteSuffix"))
    ## FIXME: Components need to be adjusted to whatever will be in the db. see comment above at SC
    out.write("Components: %s\n" % ( " ".join(map(lambda x: "%s%s" % (suite_suffix, x), SC[suite.suite_name]  ))))

    for comp in SC[suite.suite_name]:
        for dirpath, dirnames, filenames in os.walk("%sdists/%s/%s" % (cnf["Dir::Root"], suite.suite_name, comp), topdown=True):
            if not re_getsarelease.match(dirpath):
                continue

            outfile=os.path.join(dirpath, "Release")
            print "Processing %s" % (outfile)
            # subrel = open(outfile, "w")
            subrel = open("/tmp/lala2", "w")

            ## FIXME: code dupe, line 127.
            for key in subattribs:
                if getattr(suite, key[DBFIELD]) is None:
                    continue
                subrel.write("%s: %s\n" % (key[KEYWORD], getattr(suite, key[DBFIELD])))

            for key in boolattrs:
                if hasattr(suite, key):
                    if getattr(suite, key):
                        subrel.write("%s: yes\n" % (key.capitalize()))
            subrel.write("Component: %s%s\n" % (suite_suffix, comp))
            subrel.close()

    # Now that we have done the groundwork, we want to get off and add the files with
    # their checksums to the main Release file
    files = []
    oldcwd = os.getcwd()

    os.chdir("%sdists/%s" % (cnf["Dir::Root"], suite.suite_name))

    for dirpath, dirnames, filenames in os.walk(".", topdown=True):
        if dirpath == '.':
            continue
        for entry in filenames:
            if not re_includeinarelease.match(entry):
                continue
            if entry.endswith(".gz"):
                filename="zcat|%s" % (os.path.join(dirpath.lstrip('./'), entry))
            elif entry.endswith(".bz2"):
                filename="bzcat|%s" % (os.path.join(dirpath.lstrip('./'), entry))
            else:
                filename=os.path.join(dirpath.lstrip('./'), entry)
            files.append(filename)

    decompressors = { 'zcat' : gzip.GzipFile,
                      'bzcat' : bz2.BZ2File }

    hashfuncs = { 'MD5Sum' : apt_pkg.md5sum,
                  'SHA1' : apt_pkg.sha1sum,
                  'SHA256' : apt_pkg.sha256sum }

    for entry in files:
        entryhash = ""
        entrylen = ""
        comp = None
        if entry.find('|') > 0:
            k=entry.split('|')
            comp=k[0]
            filename=k[1]
        else:
            filename=entry

    os.chdir(oldcwd)
    return


def main ():
    global Options, Logger, results

    cnf = Config()

    for i in ["Help", "Suite", "Force"]:
        if not cnf.has_key("Generate-Releases::Options::%s" % (i)):
            cnf["Generate-Releases::Options::%s" % (i)] = ""

    Arguments = [('h',"help","Generate-Releases::Options::Help"),
                 ('s',"suite","Generate-Releases::Options::Suite"),
                 ('f',"force","Generate-Releases::Options::Force")]

    suite_names = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Generate-Releases::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger(cnf, 'generate-releases')

    session = DBConn().session()

    if Options["Suite"]:
        suites = []
        for s in suite_names:
            suite = get_suite(s.lower(), session)
            if suite:
                suites.append(suite)
            else:
                print "cannot find suite %s" % s
                Logger.log(['cannot find suite %s' % s])
    else:
        suites=session.query(Suite).filter(Suite.untouchable == False).all()

    startdir = os.getcwd()
    os.chdir(cnf["Dir::TempPath"])

    broken=[]
    # For each given suite, run one process
    results=[]
    for s in suites:
        # Setup a multiprocessing Pool. As many workers as we have CPU cores.
#        pool = Pool()
#        Logger.log(['Release file for Suite: %s' % (s.suite_name)])
#        pool.apply_async(generate_release_files, (s, cnf["Dir::TempPath"]), callback=get_result)
        # As long as we test, just one and not with mp module
        generate_release_files(s, cnf["Dir::TempPath"])
        break

    # No more work will be added to our pool, close it and then wait for all to finish
#    pool.close()
#    pool.join()

    if len(results) > 0:
        Logger.log(['Release file generation broken: %s' % (results)])
        print "Release file generation broken: %s" % (results)
        sys.exit(1)

    os.chdir(startdir)
    # this script doesn't change the database
    session.close()
    Logger.close()

#######################################################################################

if __name__ == '__main__':
    main()
