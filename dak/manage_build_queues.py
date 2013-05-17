#!/usr/bin/env python

""" Manage build queues

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
@copyright: 2012, Ansgar Burchardt <ansgar@debian.org>

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

import apt_pkg
from datetime import datetime, timedelta
import sys

from daklib import daklog
from daklib.archive import ArchiveTransaction
from daklib.dbconn import *
from daklib.config import Config

################################################################################

Options = None
Logger = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak manage-build-queues [OPTIONS] buildqueue1 buildqueue2
Manage the contents of one or more build queues

  -a, --all                  run on all known build queues
  -n, --no-action            don't do anything
  -h, --help                 show this help and exit"""

    sys.exit(exit_code)

################################################################################

def clean(build_queue, transaction, now=None):
    session = transaction.session
    if now is None:
        now = datetime.now()

    delete_before = now - timedelta(seconds=build_queue.stay_of_execution)
    suite = build_queue.suite

    # Remove binaries subject to the following conditions:
    # 1. Keep binaries that are in policy queues.
    # 2. Remove binaries that are not in suites.
    # 3. Remove binaries that have been in the build queue for some time.
    query = """
        SELECT b.*
          FROM binaries b
          JOIN bin_associations ba ON b.id = ba.bin
         WHERE ba.suite = :suite_id
           AND NOT EXISTS
               (SELECT 1 FROM policy_queue_upload_binaries_map pqubm
                         JOIN policy_queue_upload pqu ON pqu.id = pqubm.policy_queue_upload_id
                         JOIN policy_queue pq ON pq.id = pqu.policy_queue_id
                         JOIN suite s ON s.policy_queue_id = pq.id
                         JOIN suite_build_queue_copy sbqc ON sbqc.suite = s.id
                        WHERE pqubm.binary_id = ba.bin AND pq.send_to_build_queues
                          AND sbqc.build_queue_id = :build_queue_id)
           AND (ba.created < :delete_before
                OR NOT EXISTS
                   (SELECT 1 FROM bin_associations ba2
                             JOIN suite_build_queue_copy sbqc ON sbqc.suite = ba2.suite
                            WHERE ba2.bin = ba.bin AND sbqc.build_queue_id = :build_queue_id))"""
    binaries = session.query(DBBinary).from_statement(query) \
        .params({'build_queue_id': build_queue.queue_id, 'suite_id': suite.suite_id, 'delete_before': delete_before})
    for binary in binaries:
        Logger.log(["removed binary from build queue", build_queue.queue_name, binary.package, binary.version])
        transaction.remove_binary(binary, suite)

    # Remove sources
    # Conditions are similar as for binaries, but we also keep sources
    # if there is a binary in the build queue that uses it.
    query = """
        SELECT s.*
          FROM source s
          JOIN src_associations sa ON s.id = sa.source
         WHERE sa.suite = :suite_id
           AND NOT EXISTS
               (SELECT 1 FROM policy_queue_upload pqu
                         JOIN policy_queue pq ON pq.id = pqu.policy_queue_id
                         JOIN suite s ON s.policy_queue_id = pq.id
                         JOIN suite_build_queue_copy sbqc ON sbqc.suite = s.id
                        WHERE pqu.source_id = sa.source AND pq.send_to_build_queues
                          AND sbqc.build_queue_id = :build_queue_id)
           AND (sa.created < :delete_before
                OR NOT EXISTS
                   (SELECT 1 FROM src_associations sa2
                             JOIN suite_build_queue_copy sbqc ON sbqc.suite = sa2.suite
                            WHERE sbqc.build_queue_id = :build_queue_id
                              AND sa2.source = sa.source))
           AND NOT EXISTS
               (SELECT 1 FROM bin_associations ba
                         JOIN binaries b ON ba.bin = b.id
                        WHERE ba.suite = :suite_id
                          AND b.source = s.id)"""
    sources = session.query(DBSource).from_statement(query) \
        .params({'build_queue_id': build_queue.queue_id, 'suite_id': suite.suite_id, 'delete_before': delete_before})
    for source in sources:
        Logger.log(["removed source from build queue", build_queue.queue_name, source.source, source.version])
        transaction.remove_source(source, suite)

def main ():
    global Options, Logger

    cnf = Config()

    for i in ["Help", "No-Action", "All"]:
        if not cnf.has_key("Manage-Build-Queues::Options::%s" % (i)):
            cnf["Manage-Build-Queues::Options::%s" % (i)] = ""

    Arguments = [('h',"help","Manage-Build-Queues::Options::Help"),
                 ('n',"no-action","Manage-Build-Queues::Options::No-Action"),
                 ('a',"all","Manage-Build-Queues::Options::All")]

    queue_names = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Manage-Build-Queues::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger('manage-build-queues', Options['No-Action'])

    starttime = datetime.now()

    session = DBConn().session()

    with ArchiveTransaction() as transaction:
        session = transaction.session
        if Options['All']:
            if len(queue_names) != 0:
                print "E: Cannot use both -a and a queue name"
                sys.exit(1)
            queues = session.query(BuildQueue)
        else:
            queues = session.query(BuildQueue).filter(BuildQueue.queue_name.in_(queue_names))

        for q in queues:
            Logger.log(['cleaning queue %s using datetime %s' % (q.queue_name, starttime)])
            clean(q, transaction, now=starttime)
        if not Options['No-Action']:
            transaction.commit()
        else:
            transaction.rollback()

    Logger.close()

#######################################################################################

if __name__ == '__main__':
    main()
