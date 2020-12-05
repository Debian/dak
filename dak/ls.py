#! /usr/bin/env python3

"""
Display information about package(s) (suite, version, etc.)

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
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

# <aj> ooo, elmo has "special powers"
# <neuro> ooo, does he have lasers that shoot out of his eyes?
# <aj> dunno
# <aj> maybe he can turn invisible? that'd sure help with improved transparency!

################################################################################

import sys
import apt_pkg

from daklib.config import Config
from daklib.ls import list_packages
from daklib import utils

################################################################################


def usage(exit_code=0):
    print("""Usage: dak ls [OPTION] PACKAGE[...]
Display information about PACKAGE(s).

  -a, --architecture=ARCH    only show info for ARCH(s)
  -b, --binary-type=TYPE     only show info for binary TYPE
  -c, --component=COMPONENT  only show info for COMPONENT(s)
  -g, --greaterorequal       show buildd 'dep-wait pkg >= {highest version}' info
  -G, --greaterthan          show buildd 'dep-wait pkg >> {highest version}' info
  -h, --help                 show this help and exit
  -r, --regex                treat PACKAGE as a regex
  -s, --suite=SUITE          only show info for this suite
  -S, --source-and-binary    show info for the binary children of source pkgs
  -f, --format=control-suite use same format as control-suite for output

ARCH, COMPONENT and SUITE can be comma (or space) separated lists, e.g.
    --architecture=amd64,i386""")
    sys.exit(exit_code)

################################################################################


def main():
    cnf = Config()

    Arguments = [('a', "architecture", "Ls::Options::Architecture", "HasArg"),
                 ('b', "binarytype", "Ls::Options::BinaryType", "HasArg"),
                 ('c', "component", "Ls::Options::Component", "HasArg"),
                 ('f', "format", "Ls::Options::Format", "HasArg"),
                 ('g', "greaterorequal", "Ls::Options::GreaterOrEqual"),
                 ('G', "greaterthan", "Ls::Options::GreaterThan"),
                 ('r', "regex", "Ls::Options::Regex"),
                 ('s', "suite", "Ls::Options::Suite", "HasArg"),
                 ('S', "source-and-binary", "Ls::Options::Source-And-Binary"),
                 ('h', "help", "Ls::Options::Help")]
    for i in ["architecture", "binarytype", "component", "format",
               "greaterorequal", "greaterthan", "regex", "suite",
               "source-and-binary", "help"]:
        key = "Ls::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    packages = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Ls::Options")

    if Options["Help"]:
        usage()
    if not packages:
        utils.fubar("need at least one package name as an argument.")

    # Handle buildd maintenance helper options
    if Options["GreaterOrEqual"] or Options["GreaterThan"]:
        if Options["GreaterOrEqual"] and Options["GreaterThan"]:
            utils.fubar("-g/--greaterorequal and -G/--greaterthan are mutually exclusive.")
        if not Options["Suite"]:
            Options["Suite"] = "unstable"

    kwargs = dict()

    if Options["Regex"]:
        kwargs['regex'] = True
    if Options["Source-And-Binary"]:
        kwargs['source_and_binary'] = True
    if Options["Suite"]:
        kwargs['suites'] = utils.split_args(Options['Suite'])
    if Options["Architecture"]:
        kwargs['architectures'] = utils.split_args(Options['Architecture'])
    if Options['BinaryType']:
        kwargs['binary_types'] = utils.split_args(Options['BinaryType'])
    if Options['Component']:
        kwargs['components'] = utils.split_args(Options['Component'])

    if Options['Format']:
        kwargs['format'] = Options['Format']
    if Options['GreaterOrEqual']:
        kwargs['highest'] = '>='
    elif Options['GreaterThan']:
        kwargs['highest'] = '>>'

    for line in list_packages(packages, **kwargs):
        print(line)

######################################################################################


if __name__ == '__main__':
    main()
