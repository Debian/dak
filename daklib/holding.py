#!/usr/bin/env python
# vim:set et sw=4:

"""
Simple singleton class for storing info about Holding directory

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
from errno import ENOENT, EEXIST, EACCES
import shutil

from config import Config
from utils import fubar

###############################################################################

class Holding(object):
    __shared_state = {}

    def __init__(self, *args, **kwargs):
        self.__dict__ = self.__shared_state

        if not getattr(self, 'initialised', False):
            self.initialised = True

            self.in_holding = {}
            self.holding_dir = Config()["Dir::Holding"]
            # ftptrainees haven't access to holding, use a temp directory instead
            if not os.access(self.holding_dir, os.W_OK):
                self.holding_dir = Config()["Dir::TempPath"]

    def chdir_to_holding(self):
        os.chdir(self.holding_dir)

    def copy_to_holding(self, filename):
        base_filename = os.path.basename(filename)

        dest = os.path.join(self.holding_dir, base_filename)
        try:
            fd = os.open(dest, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o640)
            os.close(fd)
        except OSError as e:
            # Shouldn't happen, but will if, for example, someone lists a
            # file twice in the .changes.
            if e.errno == EEXIST:
                return "%s: already exists in holding area; can not overwrite." % (base_filename)

        try:
            shutil.copy(filename, dest)
        except IOError as e:
            # In either case (ENOENT or EACCES) we want to remove the
            # O_CREAT | O_EXCLed ghost file, so add the file to the list
            # of 'in holding' even if it's not the real file.
            if e.errno == ENOENT:
                os.unlink(dest)
                return "%s: can not copy to holding area: file not found." % (base_filename)

            elif e.errno == EACCES:
                os.unlink(dest)
                return "%s: can not copy to holding area: read permission denied." % (base_filename)

        self.in_holding[base_filename] = ""

        return None

    def clean(self):
        cwd = os.getcwd()
        os.chdir(self.holding_dir)
        for f in self.in_holding.keys():
            # TODO: Sanitize path in a much better manner...
            if os.path.exists(f):
                if f.find('/') != -1:
                    fubar("WTF? clean_holding() got a file ('%s') with / in it!" % (f))
                else:
                    os.unlink(f)
        self.in_holding = {}
        os.chdir(cwd)

