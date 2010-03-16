#!/usr/bin/env python

"""
Generate changelog entry between two suites

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

# <bdefreese> !dinstall
# <dak> bdefreese: I guess the next dinstall will be in 0hr 1min 35sec
# <bdefreese> Wow I have great timing
# <DktrKranz> dating with dinstall, part II
# <bdefreese> heh
# <Ganneff> dating with that monster? do you have good combat armor?
# <bdefreese> +5 Plate :)
# <Ganneff> not a good one then
# <Ganneff> so you wont even manage to bypass the lesser monster in front, unchecked
# <DktrKranz> asbesto belt
# <Ganneff> helps only a step
# <DktrKranz> the Ultimate Weapon: cron_turned_off
# <bdefreese> heh
# <Ganneff> thats debadmin limited
# <Ganneff> no option for you
# <DktrKranz> bdefreese: it seems ftp-masters want dinstall to sexual harass us, are you good in running?
# <Ganneff> you can run but you can not hide
# <bdefreese> No, I'm old and fat :)
# <Ganneff> you can roll but you can not hide
# <Ganneff> :)
# <bdefreese> haha
# <DktrKranz> damn dinstall, you racist bastard

################################################################################

import sys
import apt_pkg
from daklib.dbconn import *
from daklib import utils
from daklib.queue import Upload

################################################################################

suites = {'proposed-updates': 'proposedupdates',
          'oldstable-proposed-updates': 'oldproposedupdates'}

def usage (exit_code=0):
    print """Usage: make-changelog -s <suite> -b <base_suite> [OPTION]...
Generate changelog between two suites

Options:

  -h, --help                show this help and exit
  -s, --suite               suite providing packages to compare
  -b, --base-suite          suite to be taken as reference for comparison"""

    sys.exit(exit_code)

def get_new_packages(suite, base_suite):
    """
    Returns a dict of sources and versions where version is newer in base.
    """

    suite_sources = dict()
    base_suite_sources = dict()
    new_in_suite = dict()
    session = DBConn().session()

    # Get source details from given suites
    for i in get_all_sources_in_suite(suite, session):
        suite_sources[i[0]] = i[1]
    for i in get_all_sources_in_suite(base_suite, session):
        base_suite_sources[i[0]] = i[1]

    # Compare if version in suite is greater than the base_suite one
    for i in suite_sources.keys():
        if i not in suite_sources.keys():
            new_in_suite[i] = (suite_sources[i], 0)
        elif apt_pkg.VersionCompare(suite_sources[i], base_suite_sources[i]) > 0:
            new_in_suite[i] = (suite_sources[i], base_suite_sources[i])

    return new_in_suite

def generate_changelog(suite, source, versions):
    """
    Generates changelog data returned from changelogs table
    """
    query = """
    SELECT changelog FROM changelogs
    WHERE suite = :suite
    AND source = :source
    AND version > :base
    AND version <= :current
    ORDER BY source, version DESC"""
    session = DBConn().session()

    result = session.execute(query, {'suite': suites[suite], 'source': source, \
                             'base': versions[1], 'current': versions[0]})
    session.commit()
    for r in result.fetchall():
        for i in range(0, len(r)):
            print r[i]

def main():
    Cnf = utils.get_conf()
    Arguments = [('h','help','Make-Changelog::Options::Help'),
                 ('s','suite','Make-Changelog::Options::Suite', 'HasArg'),
                 ('b','base-suite','Make-Changelog::Options::Base-Suite', 'HasArg')]

    for i in ['help', 'suite', 'base-suite']:
        if not Cnf.has_key('Make-Changelog::Options::%s' % (i)):
            Cnf['Make-Changelog::Options::%s' % (i)] = ''

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)
    Options = Cnf.SubTree('Make-Changelog::Options')
    suite = Cnf['Make-Changelog::Options::Suite']
    base_suite = Cnf['Make-Changelog::Options::Base-Suite']

    if Options['help'] or not (suite and base_suite):
        usage()

    for s in suite, base_suite:
        if not get_suite(s):
            utils.fubar('Invalid suite "%s"' % s)

    new_packages = get_new_packages(suite, base_suite)
    for package in sorted(new_packages.keys()):
        generate_changelog(suite, package, new_packages[package])

if __name__ == '__main__':
    main()
