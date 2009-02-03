#!/usr/bin/env python

import os
import pg
import sys
from daklib import database
from daklib import utils

################################################################################

projectB = None #: database connection, pgobject

################################################################################

# Usage: dak make-pkg_file_mapping
#
# Prints out, for every file in the pool, which source package and version it
# belongs to and for binary packages additionally which arch, binary package
# and binary package version it has in a standard rfc2822-like format.

# Copyright 2009 Peter Palfrader <peter@palfrader.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

################################################################################

def build_mapping():
    # The ORDER BY is in the queries so that compression of the output works
    # better.  It's the difference between a 9 megabyte bzip2 and a 2.5 mb
    # bzip2 file.

    query_sources = """
    SELECT
        source.source,
        source.version,
        './pool/' || files.filename AS path
    FROM source
      JOIN dsc_files ON source.id=dsc_files.source
      JOIN files ON files.id=dsc_files.file
    ORDER BY source, version
    """

    query_binaries = """
    SELECT
        source.source,
        source.version,
        architecture.arch_string AS arch,
        './pool/' || files.filename AS path,
        binaries.package,
        binaries.version AS bin_version
    FROM source
      JOIN binaries ON source.id=binaries.source
      JOIN files ON binaries.file=files.id
      JOIN architecture ON architecture.id=binaries.architecture
    ORDER BY source, version, package, bin_version
    """

    for i in projectB.query(query_sources).getresult():
        (source, version, path) = i
        print "Path: %s"%path
        print "Source: %s"%source
        print "Source-Version: %s"%version
        print

    for i in projectB.query(query_binaries).getresult():
        (source, version, arch, path, bin, binv) = i
        print "Path: %s"%path
        print "Source: %s"%source
        print "Source-Version: %s"%version
        print "Architecture: %s"%arch
        print "Binary: %s"%bin
        print "Binary-Version: %s"%binv
        print

################################################################################

def main():
    global projectB

    Cnf = utils.get_conf()
    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    build_mapping()

#########################################################################################

if __name__ == '__main__':
    main()


# vim:set et:
# vim:set ts=4:
# vim:set shiftwidth=4:
