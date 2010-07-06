#!/usr/bin/env python

""" Generate Packages/Sources files

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
@copyright: 2010  Joerg Jaspert <joerg@debian.org>

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

import os
import os.path
import stat
import sys
from datetime import datetime
import apt_pkg

from daklib import daklog
from daklib.dbconn import *
from daklib.config import Config
from daklib.threadpool import ThreadPool

################################################################################

Options = None
Logger = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak generate-packages-sources [OPTIONS]
Generate the Packages/Sources files

  -s, --suite=SUITE(s)       process this suite
                             Default: All suites not marked 'untouchable'
  -f, --force                Allow processing of untouchable suites
                             CAREFUL: Only to be used at point release time!
  -h, --help                 show this help and exit

SUITE can be a space seperated list, e.g.
   --suite=unstable testing
  """

    sys.exit(exit_code)

################################################################################

def main ():
    global Options, Logger

    cnf = Config()

    for i in ["Help", "Suite", "Force"]:
        if not cnf.has_key("Generate-Packages-Sources::Options::%s" % (i)):
            cnf["Generate-Packages-Sources::Options::%s" % (i)] = ""

    Arguments = [('h',"help","Generate-Packages-Sources::Options::Help"),
                 ('s',"suite","Generate-Packages-Sources::Options::Suite"),
                 ('f',"force","Generate-Packages-Sources::Options::Force")]

    suite_names = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Generate-Packages-Sources::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger(cnf, 'generate-packages-sources')

    session = DBConn().session()

    if Options["Suite"]:
        # Something here
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

    threadpool = ThreadPool()
    # For each given suite, each architecture, run one apt-ftparchive
    for s in suites:
        arch_list=get_suite_architectures(s.suite_name, skipsrc=False, skipall=False, session=session)
        for a in arch_list:
            Logger.log(['generating output for Suite %s, Architecture %s' % (s.suite_name, a.arch_string)])
            print 'generating output for Suite %s, Architecture %s' % (s.suite_name, a.arch_string)
            threadpool.queueTask(s.generate_packages_sources, (a.arch_string))

    threadpool.joinAll()
    # this script doesn't change the database
    session.close()
    Logger.close()

#######################################################################################

if __name__ == '__main__':
    main()
