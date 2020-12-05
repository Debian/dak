#! /usr/bin/env python3
#
# Copyright (C) 2015, Ansgar Burchardt <ansgar@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from daklib.archive import ArchiveTransaction
from daklib.dbconn import *
import daklib.daklog
import daklib.utils

from sqlalchemy.orm.exc import NoResultFound
import sqlalchemy.sql as sql
import sys

"""
Idea:

dak update-suite testing testing-kfreebsd
 -> grab all source & binary packages from testing with a higher version
    than in testing-kfreebsd (or not in -kfreebsd) and copy them
 -> limited to architectures in testing-kfreebsd
 -> obeys policy queues
 -> copies to build queues

dak update-suite --create-in=ftp-master stable testing
 -> create suite "testing" based on "stable" in archive "ftp-master"

Additional switches:
 --skip-policy-queue:    skip target suite's policy queue
 --skip-build-queues:    do not copy to build queue
 --no-new-packages:      do not copy new packages
                         -> source-based, new binaries from existing sources will be added
 --only-new-packages:    do not update existing packages
                         -> source-based, do not copy new binaries w/o source!
 --also-policy-queue:    also copy pending packages from policy queue
 --update-overrides:     update overrides as well (if different overrides are used)
 --no-act
"""


def usage():
    print("dak update-suite [-n|--no-act] <origin> <target>")
    sys.exit(0)


class SuiteUpdater(object):
    def __init__(self, transaction, origin, target,
                 new_packages=True, also_from_policy_queue=False,
                 obey_policy_queue=True, obey_build_queues=True,
                 update_overrides=False, dry_run=False):
        self.transaction = transaction
        self.origin = origin
        self.target = target
        self.new_packages = new_packages
        self.also_from_policy_queue = also_from_policy_queue
        self.obey_policy_queue = obey_policy_queue
        self.obey_build_queues = obey_build_queues
        self.update_overrides = update_overrides
        self.dry_run = dry_run

        if obey_policy_queue and target.policy_queue_id is not None:
            raise Exception('Not implemented...')
        self.logger = None if dry_run else daklib.daklog.Logger("update-suite")

    def query_new_binaries(self, additional_sources):
        # Candidates are binaries in the origin suite, and optionally in its policy queue.
        query = """
          SELECT b.*
          FROM binaries b
          JOIN bin_associations ba ON b.id = ba.bin AND ba.suite = :origin
        """
        if self.also_from_policy_queue:
            query += """
              UNION
              SELECT b.*
              FROM binaries b
              JOIN policy_queue_upload_binaries_map pqubm ON pqubm.binary_id = b.id
              JOIN policy_queue_upload pqu ON pqu.id = pqubm.policy_queue_upload_id
              WHERE pqu.target_suite_id = :origin
                AND pqu.policy_queue_id = (SELECT policy_queue_id FROM suite WHERE id = :origin)
            """

        # Only take binaries that are for a architecture part of the target suite,
        # and whose source was just added to the target suite (i.e. listed in additional_sources)
        #     or that have the source already available in the target suite
        #     or in the target suite's policy queue if we obey policy queues,
        # and filter out binaries with a lower version than already in the target suite.
        if self.obey_policy_queue:
            cond_source_in_policy_queue = """
              EXISTS (SELECT 1
                      FROM policy_queue_upload pqu
                      WHERE tmp.source = pqu.source_id
                        AND pqu.target_suite_id = :target
                        AND pqu.policy_queue_id = (SELECT policy_queue_id FROM suite WHERE id = :target))
            """
        else:
            cond_source_in_policy_queue = "FALSE"
        query = """
          WITH tmp AS ({0})
          SELECT DISTINCT *
          FROM tmp
          WHERE tmp.architecture IN (SELECT architecture FROM suite_architectures WHERE suite = :target)
            AND (tmp.source IN :additional_sources
                 OR EXISTS (SELECT 1
                            FROM src_associations sa
                            WHERE tmp.source = sa.source AND sa.suite = :target)
                 OR {1})
            AND NOT EXISTS (SELECT 1
                            FROM binaries b2
                            JOIN bin_associations ba2 ON b2.id = ba2.bin AND ba2.suite = :target
                            WHERE tmp.package = b2.package AND tmp.architecture = b2.architecture AND b2.version >= tmp.version)
          ORDER BY package, version, architecture
        """.format(query, cond_source_in_policy_queue)

        # An empty tuple generates a SQL statement with "tmp.source IN ()"
        # which is not valid. Inject an invalid value in this case:
        # "tmp.source IN (NULL)" is always false.
        if len(additional_sources) == 0:
            additional_sources = tuple([None])

        params = {
            'origin': self.origin.suite_id,
            'target': self.target.suite_id,
            'additional_sources': additional_sources,
        }

        return self.transaction.session.query(DBBinary).from_statement(sql.text(query)).params(params)

    def query_new_sources(self):
        # Candidates are source packages in the origin suite, and optionally in its policy queue.
        query = """
          SELECT s.*
          FROM source s
          JOIN src_associations sa ON s.id = sa.source AND sa.suite = :origin
        """
        if self.also_from_policy_queue:
            query += """
              UNION
              SELECT s.*
              FROM source s
              JOIN policy_queue_upload pqu ON pqu.source_id = s.id
              WHERE pqu.target_suite_id = :origin
                AND pqu.policy_queue_id = (SELECT policy_queue_id FROM suite WHERE id = :origin)
            """

        # Filter out source packages with a lower version than already in the target suite.
        query = """
          WITH tmp AS ({0})
          SELECT DISTINCT *
          FROM tmp
          WHERE NOT EXISTS (SELECT 1
                            FROM source s2
                            JOIN src_associations sa2 ON s2.id = sa2.source AND sa2.suite = :target
                            WHERE s2.source = tmp.source AND s2.version >= tmp.version)
        """.format(query)

        # Optionally filter out source packages that are not already in the target suite.
        if not self.new_packages:
            query += """
              AND EXISTS (SELECT 1
                          FROM source s2
                          JOIN src_associations sa2 ON s2.id = sa2.source AND sa2.suite = :target
                          WHERE s2.source = tmp.source)
            """

        query += "ORDER BY source, version"

        params = {'origin': self.origin.suite_id, 'target': self.target.suite_id}

        return self.transaction.session.query(DBSource).from_statement(sql.text(query)).params(params)

    def _components_for_binary(self, binary, suite):
        session = self.transaction.session
        return session.query(Component) \
                      .join(ArchiveFile, Component.component_id == ArchiveFile.component_id) \
                      .join(ArchiveFile.file).filter(PoolFile.file_id == binary.poolfile_id) \
                      .filter(ArchiveFile.archive_id == suite.archive_id)

    def install_binaries(self, binaries, suite):
        if len(binaries) == 0:
            return
        # If origin and target suites are in the same archive, we can skip the
        # overhead from ArchiveTransaction.copy_binary()
        if self.origin.archive_id == suite.archive_id:
            query = "INSERT INTO bin_associations (bin, suite) VALUES (:bin, :suite)"
            target_id = suite.suite_id
            params = [{'bin': b.binary_id, 'suite': target_id} for b in binaries]
            self.transaction.session.execute(query, params)
        else:
            for b in binaries:
                for c in self._components_for_binary(b, suite):
                    self.transaction.copy_binary(b, suite, c)

    def _components_for_source(self, source, suite):
        session = self.transaction.session
        return session.query(Component) \
                      .join(ArchiveFile, Component.component_id == ArchiveFile.component_id) \
                      .join(ArchiveFile.file).filter(PoolFile.file_id == source.poolfile_id) \
                      .filter(ArchiveFile.archive_id == suite.archive_id)

    def install_sources(self, sources, suite):
        if len(sources) == 0:
            return
        # If origin and target suites are in the same archive, we can skip the
        # overhead from ArchiveTransaction.copy_source()
        if self.origin.archive_id == suite.archive_id:
            query = "INSERT INTO src_associations (source, suite) VALUES (:source, :suite)"
            target_id = suite.suite_id
            params = [{'source': s.source_id, 'suite': target_id} for s in sources]
            self.transaction.session.execute(query, params)
        else:
            for s in sources:
                for c in self._components_for_source(s, suite):
                    self.transaction.copy_source(s, suite, c)

    def update_suite(self):
        targets = set([self.target])
        if self.obey_build_queues:
            targets.update([bq.suite for bq in self.target.copy_queues])
        target_names = sorted(s.suite_name for s in targets)
        target_name = ",".join(target_names)

        new_sources = self.query_new_sources().all()
        additional_sources = tuple(s.source_id for s in new_sources)
        for s in new_sources:
            self.log(["add-source", target_name, s.source, s.version])
        if not self.dry_run:
            for target in targets:
                self.install_sources(new_sources, target)

        new_binaries = self.query_new_binaries(additional_sources).all()
        for b in new_binaries:
            self.log(["add-binary", target_name, b.package, b.version, b.architecture.arch_string])
        if not self.dry_run:
            for target in targets:
                self.install_binaries(new_binaries, target)

    def log(self, args):
        if self.logger:
            self.logger.log(args)
        else:
            print(args)


def main():
    from daklib.config import Config
    config = Config()

    import apt_pkg
    arguments = [
        ('h', 'help', 'Update-Suite::Options::Help'),
        ('n', 'no-act', 'Update-Suite::options::NoAct'),
    ]
    argv = apt_pkg.parse_commandline(config.Cnf, arguments, sys.argv)
    try:
        options = config.subtree("Update-Suite::Options")
    except KeyError:
        options = {}

    if 'Help' in options or len(argv) != 2:
        usage()

    origin_name = argv[0]
    target_name = argv[1]
    dry_run = True if 'NoAct' in options else False

    with ArchiveTransaction() as transaction:
        session = transaction.session

        try:
            origin = session.query(Suite).filter_by(suite_name=origin_name).one()
        except NoResultFound:
            daklib.utils.fubar("Origin suite '{0}' is unknown.".format(origin_name))
        try:
            target = session.query(Suite).filter_by(suite_name=target_name).one()
        except NoResultFound:
            daklib.utils.fubar("Target suite '{0}' is unknown.".format(target_name))

        su = SuiteUpdater(transaction, origin, target, dry_run=dry_run)
        su.update_suite()

        if dry_run:
            transaction.rollback()
        else:
            transaction.commit()


if __name__ == '__main__':
    pass
