#!/usr/bin/env python
# vim:set et sw=4:

"""
Urgency Logger class for dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001 - 2006 James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
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

###############################################################################

import os
import time

from config import Config
from utils import warn, open_file, move

###############################################################################

class UrgencyLog(object):
    "Urgency Logger object"

    __shared_state = {}

    def __init__(self, *args, **kwargs):
        self.__dict__ = self.__shared_state

        if not getattr(self, 'initialised', False):
            self.initialised = True

            self.timestamp = time.strftime("%Y%m%d%H%M%S")

            cnf = Config()
            if cnf.has_key("Dir::UrgencyLog"):
                # Create the log directory if it doesn't exist
                self.log_dir = cnf["Dir::UrgencyLog"]

                if not os.path.exists(self.log_dir) or not os.access(self.log_dir, os.W_OK):
                    warn("UrgencyLog directory %s does not exist or is not writeable, using /srv/ftp.debian.org/tmp/ instead" % (self.log_dir))
                    self.log_dir = '/srv/ftp.debian.org/tmp/'

                # Open the logfile
                self.log_filename = "%s/.install-urgencies-%s.new" % (self.log_dir, self.timestamp)
                self.log_file = open_file(self.log_filename, 'w')

            else:
                self.log_dir = None
                self.log_filename = None
                self.log_file = None

            self.writes = 0

    def log(self, source, version, urgency):
        "Log an event"

        # Don't try and log if Dir::UrgencyLog is not configured
        if self.log_file is None:
            return

        self.log_file.write(" ".join([source, version, urgency])+'\n')
        self.log_file.flush()
        self.writes += 1

    def close(self):
        "Close a Logger object"
        # Don't try and log if Dir::UrgencyLog is not configured
        if self.log_file is None:
            return

        self.log_file.flush()
        self.log_file.close()

        if self.writes:
            new_filename = "%s/install-urgencies-%s" % (self.log_dir, self.timestamp)
            move(self.log_filename, new_filename)
        else:
            os.unlink(self.log_filename)

