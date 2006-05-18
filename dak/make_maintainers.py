#!/usr/bin/env python

# Generate Maintainers file used by e.g. the Debian Bug Tracking System
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>

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

# ``As opposed to "Linux sucks. Respect my academic authoritah, damn
#   you!" or whatever all this hot air amounts to.''
#                             -- ajt@ in _that_ thread on debian-devel@

################################################################################

import pg, sys
import apt_pkg
import daklib.database
import daklib.utils

################################################################################

projectB = None
Cnf = None
maintainer_from_source_cache = {}
packages = {}
fixed_maintainer_cache = {}

################################################################################

def usage (exit_code=0):
    print """Usage: dak make-maintainers [OPTION] EXTRA_FILE[...]
Generate an index of packages <=> Maintainers.

  -h, --help                 show this help and exit
"""
    sys.exit(exit_code)

################################################################################

def fix_maintainer (maintainer):
    global fixed_maintainer_cache

    if not fixed_maintainer_cache.has_key(maintainer):
        fixed_maintainer_cache[maintainer] = daklib.utils.fix_maintainer(maintainer)[0]

    return fixed_maintainer_cache[maintainer]

def get_maintainer (maintainer):
    return fix_maintainer(daklib.database.get_maintainer(maintainer))

def get_maintainer_from_source (source_id):
    global maintainer_from_source_cache

    if not maintainer_from_source_cache.has_key(source_id):
        q = projectB.query("SELECT m.name FROM maintainer m, source s WHERE s.id = %s and s.maintainer = m.id" % (source_id))
        maintainer = q.getresult()[0][0]
        maintainer_from_source_cache[source_id] = fix_maintainer(maintainer)

    return maintainer_from_source_cache[source_id]

################################################################################

def main():
    global Cnf, projectB

    Cnf = daklib.utils.get_conf()

    Arguments = [('h',"help","Make-Maintainers::Options::Help")]
    if not Cnf.has_key("Make-Maintainers::Options::Help"):
	Cnf["Make-Maintainers::Options::Help"] = ""

    extra_files = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Make-Maintainers::Options")

    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)

    for suite in Cnf.SubTree("Suite").List():
        suite = suite.lower()
        suite_priority = int(Cnf["Suite::%s::Priority" % (suite)])

        # Source packages
        q = projectB.query("SELECT s.source, s.version, m.name FROM src_associations sa, source s, suite su, maintainer m WHERE su.suite_name = '%s' AND sa.suite = su.id AND sa.source = s.id AND m.id = s.maintainer" % (suite))
        sources = q.getresult()
        for source in sources:
            package = source[0]
            version = source[1]
            maintainer = fix_maintainer(source[2])
            if packages.has_key(package):
                if packages[package]["priority"] <= suite_priority:
                    if apt_pkg.VersionCompare(packages[package]["version"], version) < 0:
                        packages[package] = { "maintainer": maintainer, "priority": suite_priority, "version": version }
            else:
                packages[package] = { "maintainer": maintainer, "priority": suite_priority, "version": version }

        # Binary packages
        q = projectB.query("SELECT b.package, b.source, b.maintainer, b.version FROM bin_associations ba, binaries b, suite s WHERE s.suite_name = '%s' AND ba.suite = s.id AND ba.bin = b.id" % (suite))
        binaries = q.getresult()
        for binary in binaries:
            package = binary[0]
            source_id = binary[1]
            version = binary[3]
            # Use the source maintainer first; falling back on the binary maintainer as a last resort only
            if source_id:
                maintainer = get_maintainer_from_source(source_id)
            else:
                maintainer = get_maintainer(binary[2])
            if packages.has_key(package):
                if packages[package]["priority"] <= suite_priority:
                    if apt_pkg.VersionCompare(packages[package]["version"], version) < 0:
                        packages[package] = { "maintainer": maintainer, "priority": suite_priority, "version": version }
            else:
                packages[package] = { "maintainer": maintainer, "priority": suite_priority, "version": version }

    # Process any additional Maintainer files (e.g. from non-US or pseudo packages)
    for filename in extra_files:
        file = daklib.utils.open_file(filename)
        for line in file.readlines():
            line = daklib.utils.re_comments.sub('', line).strip()
            if line == "":
                continue
            split = line.split()
            lhs = split[0]
            maintainer = fix_maintainer(" ".join(split[1:]))
            if lhs.find('~') != -1:
                (package, version) = lhs.split('~')
            else:
                package = lhs
                version = '*'
            # A version of '*' overwhelms all real version numbers
            if not packages.has_key(package) or version == '*' \
               or apt_pkg.VersionCompare(packages[package]["version"], version) < 0:
                packages[package] = { "maintainer": maintainer, "version": version }
        file.close()

    package_keys = packages.keys()
    package_keys.sort()
    for package in package_keys:
        lhs = "~".join([package, packages[package]["version"]])
        print "%-30s %s" % (lhs, packages[package]["maintainer"])

################################################################################

if __name__ == '__main__':
    main()

