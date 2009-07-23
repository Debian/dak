#!/usr/bin/env python

""" Dump variables from a .dak file to stdout """
# Copyright (C) 2001, 2002, 2004, 2006  James Troup <james@nocrew.org>

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

# <elmo> ooooooooooooooohhhhhhhhhhhhhhhhhhhhhhhhh            dddddddddeeeeeeeaaaaaaaarrrrrrrrrrr
# <elmo> iiiiiiiiiiiii          tttttttttthhhhhhhhiiiiiiiiiiiinnnnnnnnnkkkkkkkkkkkkk              iiiiiiiiiiiiii       mmmmmmmmmmeeeeeeeesssssssssssssssseeeeeeeddd           uuuupppppppppppp       ttttttttthhhhhhhheeeeeeee          xxxxxxxssssssseeeeeeeeettttttttttttt             aaaaaaaarrrrrrrggggggsssssssss
#
# ['xset r rate 30 250' bad, mmkay]

################################################################################

import sys
import apt_pkg
from daklib.changes import Changes
from daklib import utils

################################################################################

def usage(exit_code=0):
    print """Usage: dak decode-dot-dak FILE...
Dumps the info in .dak FILE(s).

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def main():
    Cnf = utils.get_conf()
    Arguments = [('h',"help","Decode-Dot-Dak::Options::Help")]
    for i in [ "help" ]:
        if not Cnf.has_key("Decode-Dot-Dak::Options::%s" % (i)):
            Cnf["Decode-Dot-Dak::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Decode-Dot-Dak::Options")
    if Options["Help"]:
        usage()


    for arg in sys.argv[1:]:
        arg = utils.validate_changes_file_arg(arg,require_changes=-1)
        k = Changes()
        k.load_dot_dak(arg)
        print arg
        print k

################################################################################

if __name__ == '__main__':
    main()
