#!/usr/bin/python

"""
Modify external overrides.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011  Ansgar Burchardt <ansgar@debian.org>
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

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils, daklog

import apt_pkg
import sys

def usage():
    print """Usage: dak external-overrides COMMAND
Modify external overrides.

  -h, --help show this help and exit.

Commands can use a long or abbreviated form:

    remove KEY                 remove external overrides for KEY
    rm KEY

    import KEY                 import external overrides for KEY
    i KEY                      NOTE: This will replace existing overrides.

    show-key KEY               show external overrides for KEY
    s-k KEY

    show-package PACKAGE       show external overrides for PACKAGE
    s-p PACKAGE

For the 'import' command, external overrides are read from standard input and
should be given as lines of the form 'PACKAGE KEY VALUE'.
"""
    sys.exit()

#############################################################################

def external_overrides_import(key, file):
    session = DBConn().session()

    session.query(ExternalOverride).filter_by(key=key).delete()

    for line in file:
        (package, key, value) = line.strip().split(None, 2)
        eo = ExternalOverride()
        eo.package = package
        eo.key = key
        eo.value = value
        session.add(eo)

    session.commit()

#############################################################################

def main():
    cnf = Config()

    Arguments = [('h',"help","External-Overrides::Options::Help")]

    (command, arg) = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    try:
        Options = cnf.SubTree("External-Overrides::Options")
    except KeyError:
        Options = {}

    if Options.has_key("Help"):
        usage()

    logger = daklog.Logger(cnf, 'external-overrides')

    if command in ('import', 'i'):
        external_overrides_import(arg, sys.stdin)
    else:
        print "E: Unknown commands."

if __name__ == '__main__':
    main()
