#!/usr/bin/env python

""" Manage build queues

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>

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

################################################################################

Options = None
Logger = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak manage-build-queues [OPTIONS] buildqueue1 buildqueue2
Manage the contents of one or more build queues

  -a, --all                  run on all known build queues
  -n, --no-action            don't do anything
  -h, --help                 show this help and exit"""

    sys.exit(exit_code)

################################################################################

def main ():
    global Options, Logger

    cnf = Config()

    for i in ["Help", "No-Action", "All"]:
        if not cnf.has_key("Manage-Build-Queues::Options::%s" % (i)):
            cnf["Manage-Build-Queues::Options::%s" % (i)] = ""

    Arguments = [('h',"help","Manage-Build-Queues::Options::Help"),
                 ('n',"no-action","Manage-Build-Queues::Options::No-Action"),
                 ('a',"all","Manage-Build-Queues::Options::All")]

    queue_names = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Manage-Build-Queues::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger('manage-build-queues', Options['No-Action'])

    starttime = datetime.now()

    session = DBConn().session()

    if Options["All"]:
        if len(queue_names) != 0:
            print "E: Cannot use both -a and a queue_name"
            sys.exit(1)
        queues = session.query(BuildQueue).all()

    else:
        queues = []
        for q in queue_names:
            queue = get_build_queue(q.lower(), session)
            if queue:
                queues.append(queue)
            else:
                Logger.log(['cannot find queue %s' % q])

    # For each given queue, look up object and call manage_queue
    for q in queues:
        Logger.log(['cleaning queue %s using datetime %s' % (q.queue_name, starttime)])
        q.clean_and_update(starttime, Logger, dryrun=Options["No-Action"])

    Logger.close()

#######################################################################################

if __name__ == '__main__':
    main()
