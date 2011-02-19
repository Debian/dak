#!/usr/bin/env python

""" Produces a set of graphs of NEW/BYHAND/DEFERRED

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2011 Paul Wise <pabs@debian.org>
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

import os
import sys

import rrdtool
import apt_pkg

from daklib import utils
from daklib.dak_exceptions import *

Cnf = None
default_names = ["byhand", "new", "deferred"]

################################################################################

def usage(exit_code=0):
    print """Usage: dak graph
Graphs the number of packages in queue directories (usually new and byhand).

  -h, --help                show this help and exit.
  -r, --rrd=key             Directory where rrd files to be updated are stored
  -x, --extra-rrd=key       File containing extra options to rrdtool graphing
  -i, --images=key          Directory where image graphs to be updated are stored
  -n, --names=key           A comma seperated list of rrd files to be scanned

"""
    sys.exit(exit_code)

################################################################################

def graph(rrd_dir, image_dir, name, extra_args, graph, title, start, year_lines=False):
    image_file = os.path.join(image_dir, "%s-%s.png" % (name, graph))
    rrd_file = os.path.join(rrd_dir, "%s.rrd" % name)
    rrd_args = [image_file, "--start", start]
    rrd_args += ("""
--end
now
--width
600
--height
150
--vertical-label
packages
--title
Package count: %s
--lower-limit
0
-E
""" % title).strip().split("\n")

    if year_lines:
        rrd_args += ["--x-grid", "MONTH:1:YEAR:1:YEAR:1:31536000:%Y"]

    rrd_args += ("""
DEF:ds1=%s:ds1:AVERAGE
LINE2:ds1#D9382B:Total package count:
VDEF:lds1=ds1,LAST
VDEF:minds1=ds1,MINIMUM
VDEF:maxds1=ds1,MAXIMUM
VDEF:avgds1=ds1,AVERAGE
GPRINT:lds1:%%3.0lf
GPRINT:minds1:\tMin\\: %%3.0lf
GPRINT:maxds1:\tMax\\: %%3.0lf
GPRINT:avgds1:\tAvg\\: %%3.0lf\\j
DEF:ds0=%s:ds0:AVERAGE
VDEF:lds0=ds0,LAST
VDEF:minds0=ds0,MINIMUM
VDEF:maxds0=ds0,MAXIMUM
VDEF:avgds0=ds0,AVERAGE
LINE2:ds0#3069DA:Package count in %s:
GPRINT:lds0:%%3.0lf
GPRINT:minds0:\tMin\\: %%3.0lf
GPRINT:maxds0:\tMax\\: %%3.0lf
GPRINT:avgds0:\tAvg\\: %%3.0lf\\j
""" % (rrd_file, rrd_file, name.upper())).strip().split("\n")

    rrd_args += extra_args
    rrdtool.graph(*rrd_args)

################################################################################

def main():
    global Cnf

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Graph::Options::Help"),
                 ('x',"extra-rrd","Graph::Options::Extra-Rrd", "HasArg"),
                 ('r',"rrd","Graph::Options::Rrd", "HasArg"),
                 ('i',"images","Graph::Options::Images", "HasArg"),
                 ('n',"names","Graph::Options::Names", "HasArg")]
    for i in [ "help" ]:
        if not Cnf.has_key("Graph::Options::%s" % (i)):
            Cnf["Graph::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Graph::Options")
    if Options["Help"]:
        usage()

    names = []

    if Cnf.has_key("Graph::Options::Names"):
        for i in Cnf["Graph::Options::Names"].split(","):
            names.append(i)
    elif Cnf.has_key("Graph::Names"):
        names = Cnf.ValueList("Graph::Names")
    else:
        names = default_names

    extra_rrdtool_args = []

    if Cnf.has_key("Graph::Options::Extra-Rrd"):
        for i in Cnf["Graph::Options::Extra-Rrd"].split(","):
            f = open(i)
            extra_rrdtool_args.extend(f.read().strip().split("\n"))
            f.close()
    elif Cnf.has_key("Graph::Extra-Rrd"):
        for i in Cnf.ValueList("Graph::Extra-Rrd"):
            f = open(i)
            extra_rrdtool_args.extend(f.read().strip().split("\n"))
            f.close()

    if Cnf.has_key("Graph::Options::Rrd"):
        rrd_dir = Cnf["Graph::Options::Rrd"]
    elif Cnf.has_key("Dir::Rrd"):
        rrd_dir = Cnf["Dir::Rrd"]
    else:
        print >> sys.stderr, "No directory to read RRD files from\n"
        sys.exit(1)

    if Cnf.has_key("Graph::Options::Images"):
        image_dir = Cnf["Graph::Options::Images"]
    else:
        print >> sys.stderr, "No directory to write graph images to\n"
        sys.exit(1)

    for name in names:
        stdargs = [rrd_dir, image_dir, name, extra_rrdtool_args]
        graph(*(stdargs+['day', 'day', 'now-1d']))
        graph(*(stdargs+['week', 'week', 'now-1w']))
        graph(*(stdargs+['month', 'month', 'now-1m']))
        graph(*(stdargs+['year', 'year', 'now-1y']))
        graph(*(stdargs+['5years', '5 years', 'now-5y', True]))
        graph(*(stdargs+['10years', '10 years', 'now-10y', True]))

################################################################################

if __name__ == '__main__':
    main()
