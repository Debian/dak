#!/usr/bin/env python

"""
Logging functions

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001, 2002, 2006  James Troup <james@nocrew.org>
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

import os
import pwd
import time
import sys
import utils

################################################################################

class Logger(object):
    "Logger object"
    __shared_state = {}

    def __init__(self, program='unknown', debug=False, print_starting=True, include_pid=False):
        self.__dict__ = self.__shared_state

        self.program = program
        self.debug = debug
        self.include_pid = include_pid

        if not getattr(self, 'logfile', None):
            self._open_log(debug)

        if print_starting:
            self.log(["program start"])

    def _open_log(self, debug):
        # Create the log directory if it doesn't exist
        from daklib.config import Config
        logdir = Config()["Dir::Log"]
        if not os.path.exists(logdir):
            umask = os.umask(00000)
            os.makedirs(logdir, 0o2775)
            os.umask(umask)

        # Open the logfile
        logfilename = "%s/%s" % (logdir, time.strftime("%Y-%m"))
        logfile = None

        if debug:
            logfile = sys.stderr
        else:
            umask = os.umask(0o0002)
            logfile = utils.open_file(logfilename, 'a')
            os.umask(umask)

        self.logfile = logfile

    def log (self, details):
        "Log an event"
        # Prepend timestamp, program name, and user name
        details.insert(0, utils.getusername())
        details.insert(0, self.program)
        timestamp = time.strftime("%Y%m%d%H%M%S")
        details.insert(0, timestamp)
        # Force the contents of the list to be string.join-able
        details = [ str(i) for i in details ]
        # Write out the log in TSV
        self.logfile.write("|".join(details)+'\n')
        # Flush the output to enable tail-ing
        self.logfile.flush()

    def close (self):
        "Close a Logger object"
        self.log(["program end"])
        self.logfile.flush()
        self.logfile.close()
