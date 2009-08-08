#!/usr/bin/env python

""" Check for fixable discrepancies between stable and unstable """
# Copyright (C) 2000, 2001, 2002, 2003, 2006  James Troup <james@nocrew.org>

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

import sys
import apt_pkg

from daklib.dbconn import *
from daklib.config import Config

################################################################################

def usage(exit_code=0):
    print """Usage: dak compare-suites
Looks for fixable descrepancies between stable and unstable.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def main ():
    cnf = Config()
    Arguments = [('h',"help","Compare-Suites::Options::Help")]

    for i in [ "help" ]:
        if not cnf.has_key("Compare-Suites::Options::%s" % (i)):
            cnf["Compare-Suites::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.SubTree("Compare-Suites::Options")
    if Options["Help"]:
        usage()

    session = DBConn().session()

    src_suite = get_suite("stable")
    dst_suite = get_suite("unstable")

    arch_all = get_architecture("all")
    dsc_type = get_override_type("dsc")

    # Arch: all doesn't work; consider packages which go from
    # arch: all to arch: any, e.g. debconf... needs more checks
    # and thought later.
    for arch in get_suite_architectures(src_suite.suite_name, skipsrc=True, skipall=True):
        q = session.execute("""
SELECT b_src.package, b_src.version, a.arch_string
  FROM binaries b_src, bin_associations ba, override o, architecture a
  WHERE ba.bin = b_src.id AND ba.suite = :src_suite_id AND b_src.architecture = :arch_id
        AND a.id = b_src.architecture AND o.package = b_src.package
        AND o.suite = :dst_suite_id AND o.type != :arch_id AND NOT EXISTS
    (SELECT 1 FROM bin_associations ba2, binaries b_dst
       WHERE ba2.bin = b_dst.id AND b_dst.package = b_src.package
             AND (b_dst.architecture = :arch_id OR b_dst.architecture = :arch_all_id)
             AND ba2.suite = :dst_suite_id AND EXISTS
               (SELECT 1 FROM bin_associations ba3, binaries b2
                  WHERE ba3.bin = b2.id AND ba3.suite = :dst_suite_id AND b2.package = b_dst.package))
ORDER BY b_src.package;"""
              % {'src_suite_id': src_suite.suite_id,
                  'arch_id': arch.arch_id,
                  'dst_suite_id': dst_suite.suite_id,
                  'dsc_type_id': dsc_type.overridetype_id,
                  'arch_all_id': arch_all.arch_id})

        for i in q.fetchall():
            print " ".join(i)

#######################################################################################

if __name__ == '__main__':
    main()
