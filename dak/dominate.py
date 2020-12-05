#! /usr/bin/env python3

"""
Remove obsolete source and binary associations from suites.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Torsten Werner <twerner@debian.org>
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

from daklib.dbconn import *
from daklib.config import Config
from daklib import daklog, utils
import apt_pkg
import sys

from sqlalchemy.sql import exists, text
from tabulate import tabulate


Options = None
Logger = None


def retrieve_associations(suites, session):
    return session.execute(text('''
WITH
  -- Provide (source, suite) tuple of all source packages to remain
  remain_source AS (
    SELECT
        *
      FROM (
        SELECT
            source.id AS source_id,
            src_associations.suite AS suite_id,
            -- generate rank over versions of a source package in one suite
            -- "1" being the newest
            dense_rank() OVER (
              PARTITION BY source.source, src_associations.suite
              ORDER BY source.version DESC
            ) AS version_rank
          FROM
            source
            INNER JOIN src_associations ON
              src_associations.source = source.id
              AND src_associations.suite = ANY(:suite_ids)
        ) AS source_ranked
      WHERE
        version_rank = 1
  ),
  -- Provide (source, arch, suite) tuple of all binary packages to remain
  remain_binaries AS (
    SELECT
        *
      FROM (
        SELECT
            binaries.id,
            binaries.architecture AS arch_id,
            bin_associations.suite AS suite_id,
            source.id AS source_id,
            architecture.arch_string AS arch,
            -- arch of newest version
            first_value(architecture.arch_string) OVER (
              PARTITION BY binaries.package, bin_associations.suite
              ORDER BY binaries.version DESC
              ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            ) as arch_first,
            -- generate rank over versions of a source package in one suite
            -- "1" being the newest
            -- if newest package is arch-any, we use the rank only over current arch
            dense_rank() OVER (
              PARTITION BY binaries.package, binaries.architecture, bin_associations.suite
              ORDER BY binaries.version DESC
            ) AS version_rank_any,
            -- if newest package is arch-all, we use the rank over all arches
            -- this makes it possible to replace all by any and any by all
            dense_rank() OVER (
              PARTITION BY binaries.package, bin_associations.suite
              ORDER BY binaries.version DESC
            ) AS version_rank_all
          FROM
            binaries
            INNER JOIN source ON source.id = binaries.source
            INNER JOIN bin_associations ON
              bin_associations.bin = binaries.id
              AND bin_associations.suite = ANY(:suite_ids)
            INNER JOIN architecture ON architecture.id = binaries.architecture
        ) AS source_rank
      WHERE
        -- we only want to retain the newest of each
        CASE
          WHEN arch != 'all' AND arch_first != 'all' THEN version_rank_any = 1
          ELSE version_rank_all = 1
        END
  ),
  -- Figure out which source we should remove
  -- A binary forces the corresponding source to remain
  dominate_source AS (
    SELECT
        source.source AS source_package,
        source.version AS source_version,
        source.source AS package,
        source.version,
        'source'::text AS arch,
        suite.suite_name AS suite,
        src_associations.id AS assoc_id
      FROM
        source
        INNER JOIN src_associations ON
          src_associations.source = source.id
          AND src_associations.suite = ANY(:suite_ids)
        INNER join suite ON suite.id = src_associations.suite
        LEFT JOIN remain_binaries ON
          remain_binaries.source_id = source.id
          AND remain_binaries.suite_id = src_associations.suite
        LEFT JOIN remain_source ON
          remain_source.source_id = source.id
          AND remain_source.suite_id = src_associations.suite
      WHERE
        remain_binaries.source_id IS NULL
        AND remain_source.source_id IS NULL
  ),
  -- Figure out which arch-any binaries we should remove
  dominate_binaries AS (
    SELECT
        source.source AS source_package,
        source.version AS source_version,
        binaries.package AS package,
        binaries.version,
        architecture.arch_string AS arch,
        suite.suite_name AS suite,
        bin_associations.id AS assoc_id
      FROM
        binaries
        INNER JOIN source ON source.id = binaries.source
        INNER JOIN bin_associations ON
          bin_associations.bin = binaries.id
          AND bin_associations.suite = ANY(:suite_ids)
        INNER JOIN architecture ON architecture.id = binaries.architecture
        INNER join suite ON suite.id = bin_associations.suite
        LEFT JOIN remain_binaries ON
          remain_binaries.id = binaries.id
          AND remain_binaries.arch_id = binaries.architecture
          AND remain_binaries.suite_id = bin_associations.suite
      WHERE
        remain_binaries.source_id IS NULL
        AND binaries.architecture != (SELECT id from architecture WHERE arch_string = 'all')
  ),
  -- Figure out which arch-all binaries we should remove
  -- A arch-any binary forces the related arch-all binaries to remain
  dominate_binaries_all AS (
    SELECT
        source.source AS source_package,
        source.version AS source_version,
        binaries.package AS package,
        binaries.version,
        architecture.arch_string AS arch,
        suite.suite_name AS suite,
        bin_associations.id AS assoc_id
      FROM
        binaries
        INNER JOIN source ON source.id = binaries.source
        INNER JOIN bin_associations ON
          bin_associations.bin = binaries.id
          AND bin_associations.suite = ANY(:suite_ids)
        INNER JOIN architecture ON architecture.id = binaries.architecture
        INNER join suite ON suite.id = bin_associations.suite
        LEFT JOIN remain_binaries ON
          remain_binaries.id = binaries.id
          AND remain_binaries.arch_id = binaries.architecture
          AND remain_binaries.suite_id = bin_associations.suite
        LEFT JOIN remain_binaries AS remain_binaries_any ON
          remain_binaries_any.source_id = source.id
          AND remain_binaries_any.suite_id = bin_associations.suite
          AND remain_binaries_any.arch_id != (SELECT id from architecture WHERE arch_string = 'all')
      WHERE
        remain_binaries.source_id IS NULL
        AND remain_binaries_any.source_id IS NULL
        AND binaries.architecture = (SELECT id from architecture WHERE arch_string = 'all')
  )
SELECT
    *
  FROM
    dominate_source
  UNION SELECT
    *
  FROM
    dominate_binaries
  UNION SELECT
    *
  FROM
    dominate_binaries_all
  ORDER BY
    source_package, source_version, package, version, arch, suite
''').params(
    suite_ids=[s.suite_id for s in suites],
))


def delete_associations_table(table, ids, session):
    result = session.execute(text('''
        DELETE
            FROM {}
            WHERE id = ANY(:assoc_ids)
    '''.format(table)).params(
        assoc_ids=list(ids),
    ))

    assert result.rowcount == len(ids), 'Rows deleted are not equal to deletion requests'


def delete_associations(assocs, session):
    ids_bin = set()
    ids_src = set()

    for e in assocs:
        Logger.log(['newer', e.package, e.version, e.suite, e.arch, e.assoc_id])

        if e.arch == 'source':
            ids_src.add(e.assoc_id)
        else:
            ids_bin.add(e.assoc_id)

    delete_associations_table('bin_associations', ids_bin, session)
    delete_associations_table('src_associations', ids_src, session)


def usage():
    print("""Usage: dak dominate [OPTIONS]
Remove obsolete source and binary associations from suites.

    -s, --suite=SUITE          act on this suite
    -h, --help                 show this help and exit
    -n, --no-action            don't commit changes
    -f, --force                also clean up untouchable suites

SUITE can be comma (or space) separated list, e.g.
    --suite=testing,unstable""")
    sys.exit()


def main():
    global Options, Logger
    cnf = Config()
    Arguments = [('h', "help",      "Obsolete::Options::Help"),
                 ('s', "suite",     "Obsolete::Options::Suite", "HasArg"),
                 ('n', "no-action", "Obsolete::Options::No-Action"),
                 ('f', "force",     "Obsolete::Options::Force")]
    cnf['Obsolete::Options::Help'] = ''
    cnf['Obsolete::Options::No-Action'] = ''
    cnf['Obsolete::Options::Force'] = ''
    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Obsolete::Options")
    if Options['Help']:
        usage()

    if not Options['No-Action']:
        Logger = daklog.Logger("dominate")
    session = DBConn().session()

    suites_query = (session
            .query(Suite)
            .order_by(Suite.suite_name)
            .filter(~exists().where(Suite.suite_id == PolicyQueue.suite_id)))
    if 'Suite' in Options:
        suites_query = suites_query.filter(Suite.suite_name.in_(utils.split_args(Options['Suite'])))
    if not Options['Force']:
        suites_query = suites_query.filter_by(untouchable=False)
    suites = suites_query.all()

    assocs = list(retrieve_associations(suites, session))

    if Options['No-Action']:
        headers = ('source package', 'source version', 'package', 'version', 'arch', 'suite', 'id')
        print((tabulate(assocs, headers, tablefmt="orgtbl")))
        session.rollback()

    else:
        delete_associations(assocs, session)
        session.commit()

    if Logger:
        Logger.close()


if __name__ == '__main__':
    main()
