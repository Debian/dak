#!/usr/bin/env python

"""
Generate Maintainers file used by e.g. the Debian Bug Tracking System
@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
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

# ``As opposed to "Linux sucks. Respect my academic authoritah, damn
#   you!" or whatever all this hot air amounts to.''
#                             -- ajt@ in _that_ thread on debian-devel@

################################################################################

import sys
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils
from daklib import textutils
from daklib.regexes import re_comments

################################################################################

maintainer_from_source_cache = {}   #: caches the maintainer name <email> per source_id
packages = {}                       #: packages data to write out
fixed_maintainer_cache = {}         #: caches fixed ( L{daklib.textutils.fix_maintainer} ) maintainer data

################################################################################

def usage (exit_code=0):
    print """Usage: dak make-maintainers [OPTION] EXTRA_FILE[...]
Generate an index of packages <=> Maintainers.

  -u, --uploaders            create uploaders index
  -h, --help                 show this help and exit
"""
    sys.exit(exit_code)

################################################################################

def fix_maintainer (maintainer):
    """
    Fixup maintainer entry, cache the result.

    @type maintainer: string
    @param maintainer: A maintainer entry as passed to L{daklib.textutils.fix_maintainer}

    @rtype: tuple
    @returns: fixed maintainer tuple
    """
    global fixed_maintainer_cache

    if not fixed_maintainer_cache.has_key(maintainer):
        fixed_maintainer_cache[maintainer] = textutils.fix_maintainer(maintainer)[0]

    return fixed_maintainer_cache[maintainer]

def get_maintainer(maintainer, session):
    """
    Retrieves maintainer name from database, passes it through fix_maintainer and
    passes on whatever that returns.

    @type maintainer: int
    @param maintainer: maintainer_id
    """
    q = session.execute("SELECT name FROM maintainer WHERE id = :id", {'id': maintainer}).fetchall()
    return fix_maintainer(q[0][0])

def get_maintainer_from_source(source_id, session):
    """
    Returns maintainer name for given source_id.

    @type source_id: int
    @param source_id: source package id

    @rtype: string
    @return: maintainer name/email
    """
    global maintainer_from_source_cache

    if not maintainer_from_source_cache.has_key(source_id):
        q = session.execute("""SELECT m.name FROM maintainer m, source s
                                WHERE s.id = :sourceid AND s.maintainer = m.id""",
                            {'sourceid': source_id})
        maintainer = q.fetchall()[0][0]
        maintainer_from_source_cache[source_id] = fix_maintainer(maintainer)

    return maintainer_from_source_cache[source_id]

################################################################################

def main():
    cnf = Config()

    Arguments = [('h',"help","Make-Maintainers::Options::Help"),
                 ('u',"uploaders","Make-Maintainers::Options::Uploaders")]
    if not cnf.has_key("Make-Maintainers::Options::Help"):
        cnf["Make-Maintainers::Options::Help"] = ""
    if not cnf.has_key("Make-Maintainers::Options::Uploaders"):
        cnf["Make-Maintainers::Options::Uploaders"] = ""

    extra_files = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Make-Maintainers::Options")

    if Options["Help"]:
        usage()

    gen_uploaders = False
    if Options["Uploaders"]:
        gen_uploaders = True

    session = DBConn().session()

    for suite in cnf.SubTree("Suite").List():
        suite = suite.lower()
        suite_priority = int(cnf["Suite::%s::Priority" % (suite)])

        # Source packages
        if gen_uploaders:
            q = session.execute("""SELECT s.source, s.version, m.name
                                     FROM src_associations sa, source s, suite su, maintainer m, src_uploaders srcu
                                    WHERE su.suite_name = :suite_name
                                      AND sa.suite = su.id AND sa.source = s.id
                                      AND m.id = srcu.maintainer
                                      AND srcu.source = s.id""",
                                    {'suite_name': suite})
        else:
            q = session.execute("""SELECT s.source, s.version, m.name
                                     FROM src_associations sa, source s, suite su, maintainer m
                                    WHERE su.suite_name = :suite_name
                                      AND sa.suite = su.id AND sa.source = s.id
                                      AND m.id = s.maintainer""",
                                    {'suite_name': suite})

        for source in q.fetchall():
            package = source[0]
            version = source[1]
            maintainer = fix_maintainer(source[2])
            if gen_uploaders:
                key = (package, maintainer)
            else:
                key = package

            if packages.has_key(key):
                if packages[key]["priority"] <= suite_priority:
                    if apt_pkg.VersionCompare(packages[key]["version"], version) < 0:
                        packages[key] = { "maintainer": maintainer, "priority": suite_priority, "version": version }
            else:
                packages[key] = { "maintainer": maintainer, "priority": suite_priority, "version": version }

        # Binary packages
        if gen_uploaders:
            q = session.execute("""SELECT b.package, b.source, srcu.maintainer, b.version
                                     FROM bin_associations ba, binaries b, suite s, src_uploaders srcu
                                    WHERE s.suite_name = :suite_name
                                      AND ba.suite = s.id AND ba.bin = b.id
                                      AND b.source = srcu.source""",
                                   {'suite_name': suite})
        else:
            q = session.execute("""SELECT b.package, b.source, b.maintainer, b.version
                                     FROM bin_associations ba, binaries b, suite s
                                    WHERE s.suite_name = :suite_name
                                      AND ba.suite = s.id AND ba.bin = b.id""",
                                   {'suite_name': suite})


        for binary in q.fetchall():
            package = binary[0]
            source_id = binary[1]
            version = binary[3]
            # Use the source maintainer first; falling back on the binary maintainer as a last resort only
            if source_id and not gen_uploaders:
                maintainer = get_maintainer_from_source(source_id, session)
            else:
                maintainer = get_maintainer(binary[2], session)
            if gen_uploaders:
                key = (package, maintainer)
            else:
                key = package

            if packages.has_key(key):
                if packages[key]["priority"] <= suite_priority:
                    if apt_pkg.VersionCompare(packages[key]["version"], version) < 0:
                        packages[key] = { "maintainer": maintainer, "priority": suite_priority, "version": version }
            else:
                packages[key] = { "maintainer": maintainer, "priority": suite_priority, "version": version }

    # Process any additional Maintainer files (e.g. from pseudo packages)
    for filename in extra_files:
        extrafile = utils.open_file(filename)
        for line in extrafile.readlines():
            line = re_comments.sub('', line).strip()
            if line == "":
                continue
            split = line.split()
            lhs = split[0]
            maintainer = fix_maintainer(" ".join(split[1:]))
            if lhs.find('~') != -1:
                (package, version) = lhs.split('~', 1)
            else:
                package = lhs
                version = '*'
            if not gen_uploaders:
                key = package
            else:
                key = (package, maintainer)
            # A version of '*' overwhelms all real version numbers
            if not packages.has_key(key) or version == '*' \
               or apt_pkg.VersionCompare(packages[key]["version"], version) < 0:
                packages[key] = { "maintainer": maintainer, "version": version }
        extrafile.close()

    package_keys = packages.keys()
    package_keys.sort()
    if gen_uploaders:
        for (package, maintainer) in package_keys:
            key = (package, maintainer)
            lhs = "~".join([package, packages[key]["version"]])
            print "%-30s %s" % (lhs, maintainer)
    else:
        for package in package_keys:
            lhs = "~".join([package, packages[package]["version"]])
            print "%-30s %s" % (lhs, packages[package]["maintainer"])

################################################################################

if __name__ == '__main__':
    main()
