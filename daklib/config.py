#!/usr/bin/env python

"""
Config access class

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2008  Mark Hymers <mhy@debian.org>
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

# <NCommander> mhy, how about "Now with 20% more monty python references"

################################################################################

import apt_pkg
import socket

from singleton import Singleton

################################################################################

default_config = "/etc/dak/dak.conf" #: default dak config, defines host properties

def which_conf_file(Cnf):
    res = socket.gethostbyaddr(socket.gethostname())
    if Cnf.get("Config::" + res[0] + "::DakConfig"):
        return Cnf["Config::" + res[0] + "::DakConfig"]
    else:
        return default_config

class Config(Singleton):
    """
    A Config object is a singleton containing
    information about the DAK configuration
    """
    def __init__(self, *args, **kwargs):
        super(Config, self).__init__(*args, **kwargs)

    def _readconf(self):
        apt_pkg.init()

        self.Cnf = apt_pkg.newConfiguration()

        apt_pkg.ReadConfigFileISC(self.Cnf, default_config)

        # Check whether our dak.conf was the real one or
        # just a pointer to our main one
        res = socket.gethostbyaddr(socket.gethostname())
        conffile = self.Cnf.get("Config::" + res[0] + "::DakConfig")
        if conffile:
            apt_pkg.ReadConfigFileISC(self.Cnf, conffile)

        # Rebind some functions
        # TODO: Clean this up
        self.get = self.Cnf.get
        self.SubTree = self.Cnf.SubTree
        self.ValueList = self.Cnf.ValueList
        self.Find = self.Cnf.Find
        self.FindB = self.Cnf.FindB

    def _startup(self, *args, **kwargs):
        self._readconf()

    def has_key(self, name):
        return self.Cnf.has_key(name)

    def __getitem__(self, name):
        return self.Cnf[name]

    def __setitem__(self, name, value):
        self.Cnf[name] = value
