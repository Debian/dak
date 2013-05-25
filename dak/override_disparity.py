#!/usr/bin/env python

"""
Generate a list of override disparities

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2010 Luca Falavigna <dktrkranz@debian.org>
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

# <adsb> Yay bugzilla *sigh*
# <phil> :)
# <Ganneff> quick, replace the bts with it
# * jcristau replaces dak with soyuz
# <adsb> and expects Ganneff to look after it?
# <jcristau> nah, elmo can do that
# * jcristau hides

################################################################################

import os
import sys
import apt_pkg
import yaml

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils

################################################################################

def usage (exit_code=0):
    print """Generate a list of override disparities

       Usage:
       dak override-disparity [-f <file>] [ -p <package> ] [ -s <suite> ]

Options:

  -h, --help                show this help and exit
  -f, --file                store output into given file
  -p, --package             limit check on given package only
  -s, --suite               choose suite to look for (default: unstable)"""

    sys.exit(exit_code)

def main():
    cnf = Config()
    Arguments = [('h','help','Override-Disparity::Options::Help'),
                 ('f','file','Override-Disparity::Options::File','HasArg'),
                 ('s','suite','Override-Disparity::Options::Suite','HasArg'),
                 ('p','package','Override-Disparity::Options::Package','HasArg')]

    for i in ['help', 'package']:
        if not cnf.has_key('Override-Disparity::Options::%s' % (i)):
            cnf['Override-Disparity::Options::%s' % (i)] = ''
    if not cnf.has_key('Override-Disparity::Options::Suite'):
        cnf['Override-Disparity::Options::Suite'] = 'unstable'

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree('Override-Disparity::Options')

    if Options['help']:
        usage()

    depends = {}
    session = DBConn().session()
    suite_name = Options['suite']
    suite = get_suite(suite_name, session)
    if suite is None:
        utils.fubar("Unknown suite '{0}'".format(suite_name))
    components = get_component_names(session)
    arches = set([x.arch_string for x in get_suite_architectures(suite_name)])
    arches -= set(['source', 'all'])
    for arch in arches:
        for component in components:
            Packages = utils.get_packages_from_ftp(suite.archive.path, suite_name, component, arch)
            while Packages.step():
                package = Packages.section.find('Package')
                dep_list = Packages.section.find('Depends')
                if Options['package'] and package != Options['package']:
                    continue
                if dep_list:
                    for d in apt_pkg.parse_depends(dep_list):
                        for i in d:
                            if not depends.has_key(package):
                                depends[package] = set()
                            depends[package].add(i[0])

    priorities = {}
    query = """SELECT DISTINCT o.package, p.level, p.priority, m.name
               FROM override o
               JOIN suite s ON s.id = o.suite
               JOIN priority p ON p.id = o.priority
               JOIN binaries b ON b.package = o.package
               JOIN maintainer m ON m.id = b.maintainer
               JOIN bin_associations ba ON ba.bin = b.id
               WHERE s.suite_name = '%s'
               AND ba.suite = s.id
               AND p.level <> 0""" % suite_name
    packages = session.execute(query)

    out = {}
    if Options.has_key('file'):
        outfile = file(os.path.expanduser(Options['file']), 'w')
    else:
        outfile = sys.stdout
    for p in packages:
        priorities[p[0]] = [p[1], p[2], p[3], True]
    for d in sorted(depends.keys()):
        for p in depends[d]:
            if priorities.has_key(d) and priorities.has_key(p):
                if priorities[d][0] < priorities[p][0]:
                     if priorities[d][3]:
                         if not out.has_key(d):
                             out[d] = {}
                         out[d]['priority'] = priorities[d][1]
                         out[d]['maintainer'] = unicode(priorities[d][2], 'utf-8')
                         out[d]['priority'] = priorities[d][1]
                         priorities[d][3] = False
                     if not out[d].has_key('dependency'):
                         out[d]['dependency'] = {}
                     out[d]['dependency'][p] = priorities[p][1]
    yaml.safe_dump(out, outfile, default_flow_style=False)
    if Options.has_key('file'):
        outfile.close()

if __name__ == '__main__':
    main()
