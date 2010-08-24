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

################################################################################

def usage (exit_code=0):
    print """Generate changelog between two suites

       Usage:
       make-changelog -s <suite> -b <base_suite> [OPTION]...
       make-changelog -T

Options:

  -h, --help                show this help and exit
  -s, --suite               suite providing packages to compare
  -b, --base-suite          suite to be taken as reference for comparison
  -n, --binnmu              display binNMUs uploads instead of source ones
  -T, --testing             display changes entering testing"""

    sys.exit(exit_code)

def get_source_uploads(suite, base_suite, session):
    """
    Returns changelogs for source uploads where version is newer than base.
    """

    query = """WITH base AS (
                 SELECT source, max(version) AS version
                 FROM source_suite
                 WHERE suite_name = :base_suite
                 GROUP BY source
                 UNION (SELECT source, CAST(0 AS debversion) AS version
                 FROM source_suite
                 WHERE suite_name = :suite
                 EXCEPT SELECT source, CAST(0 AS debversion) AS version
                 FROM source_suite
                 WHERE suite_name = :base_suite
                 ORDER BY source)),
               cur_suite AS (
                 SELECT source, max(version) AS version
                 FROM source_suite
                 WHERE suite_name = :suite
                 GROUP BY source)
               SELECT DISTINCT c.source, c.version, c.changelog
               FROM changelogs c
               JOIN base b ON b.source = c.source
               JOIN cur_suite cs ON cs.source = c.source
               WHERE c.version > b.version
               AND c.version <= cs.version
               AND c.architecture LIKE '%source%'
               ORDER BY c.source, c.version DESC"""

    return session.execute(query, {'suite': suite, 'base_suite': base_suite})

def get_binary_uploads(suite, base_suite, session):
    """
    Returns changelogs for binary uploads where version is newer than base.
    """

    query = """WITH base as (
                 SELECT s.source, max(b.version) AS version, a.arch_string
                 FROM source s
                 JOIN binaries b ON b.source = s.id
                 JOIN bin_associations ba ON ba.bin = b.id
                 JOIN architecture a ON a.id = b.architecture
                 WHERE ba.suite = (
                   SELECT id
                   FROM suite
                   WHERE suite_name = :base_suite)
                 GROUP BY s.source, a.arch_string),
               cur_suite as (
                 SELECT s.source, max(b.version) AS version, a.arch_string
                 FROM source s
                 JOIN binaries b ON b.source = s.id
                 JOIN bin_associations ba ON ba.bin = b.id
                 JOIN architecture a ON a.id = b.architecture
                 WHERE ba.suite = (
                   SELECT id
                   FROM suite
                   WHERE suite_name = :suite)
                 GROUP BY s.source, a.arch_string)
               SELECT DISTINCT c.source, c.version, c.architecture, c.changelog
               FROM changelogs c
               JOIN base b on b.source = c.source
               JOIN cur_suite cs ON cs.source = c.source
               WHERE c.version > b.version
               AND c.version <= cs.version
               AND c.architecture = b.arch_string
               AND c.architecture = cs.arch_string
               ORDER BY c.source, c.version DESC, c.architecture"""

    return session.execute(query, {'suite': suite, 'base_suite': base_suite})

def testing_summary(summary, session):
    """
    Returns changes introduced in packages entering testing.
    """

    query =  'SELECT source, changelog FROM changelogs WHERE'
    fd = open(summary, 'r')
    for package in fd.read().splitlines():
        package = package.split()
        if package[1] != package[2]:
            if package[1] == '(not_in_testing)':
                package[1] = 0
            query += " source = '%s' AND version > '%s' AND version <= '%s'" \
                     % (package[0], package[1], package[2])
            query += " AND architecture LIKE '%source%' OR"
    fd.close()
    query += ' False ORDER BY source, version DESC;'

    return session.execute(query)

def display_changes(uploads, index):
    prev_upload = None
    for upload in uploads:
        if prev_upload and prev_upload != upload[0]:
            print
        print upload[index]
        prev_upload = upload[0]

def main():
    Cnf = utils.get_conf()
    Arguments = [('h','help','Make-Changelog::Options::Help'),
                 ('s','suite','Make-Changelog::Options::Suite','HasArg'),
                 ('b','base-suite','Make-Changelog::Options::Base-Suite','HasArg'),
                 ('n','binnmu','Make-Changelog::Options::binNMU'),
                 ('T', 'testing','Make-Changelog::Options::Testing')]

    for i in ['help', 'suite', 'base-suite', 'binnmu', 'testing']:
        if not Cnf.has_key('Make-Changelog::Options::%s' % (i)):
            Cnf['Make-Changelog::Options::%s' % (i)] = ''

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)
    Options = Cnf.SubTree('Make-Changelog::Options')
    suite = Cnf['Make-Changelog::Options::Suite']
    base_suite = Cnf['Make-Changelog::Options::Base-Suite']
    binnmu = Cnf['Make-Changelog::Options::binNMU']
    testing = Cnf['Make-Changelog::Options::Testing']

    if Options['help'] or not (suite and base_suite) and not testing:
        usage()

    for s in suite, base_suite:
        if not testing and not get_suite(s):
            utils.fubar('Invalid suite "%s"' % s)

    session = DBConn().session()

    if testing:
        display_changes(testing_summary(Cnf['Changelogs::Testing'], session), 1)
    elif binnmu:
        display_changes(get_binary_uploads(suite, base_suite, session), 3)
    else:
        display_changes(get_source_uploads(suite, base_suite, session), 2)

    session.commit()

if __name__ == '__main__':
    main()
