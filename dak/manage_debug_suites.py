#! /usr/bin/env python3

""" Manage debug suites

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2015, Ansgar Burchardt <ansgar@debian.org>

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
import sys

from daklib import daklog
from daklib.archive import ArchiveTransaction
from daklib.dbconn import *
from daklib.config import Config

################################################################################

Options = None
Logger = None

################################################################################


def usage(exit_code=0):
    print("""Usage: dak manage-debug-suites [-a|--all|<suite>...]
Manage the contents of one or more debug suites

  -a, --all                  run on all known debug suites
  -n, --no-action            don't do anything
  -h, --help                 show this help and exit""")

    sys.exit(exit_code)

################################################################################


def clean(debug_suite, transaction):
    session = transaction.session

    # Sanity check: make sure this is a debug suite or we would remove everything
    any_suite = session.query(Suite).filter_by(debug_suite=debug_suite).first()
    if any_suite is None:
        raise Exception("Suite '{0}' is not a debug suite".format(debug_suite.suite_name))

    # Only keep source packages that are still a base suite.
    # All other sources and their binary packages can go.
    query = """
    WITH
    sources_to_keep AS
      (SELECT DISTINCT sa.source
         FROM src_associations sa
         JOIN suite ON sa.suite = suite.id
        WHERE suite.debugsuite_id = :debugsuite_id),
    sources_removed AS
      (DELETE FROM src_associations sa
        WHERE sa.suite = :debugsuite_id
          AND sa.source NOT IN (SELECT source FROM sources_to_keep)
       RETURNING sa.source)
    DELETE FROM bin_associations ba
     USING binaries b
     WHERE ba.suite = :debugsuite_id
       AND ba.bin = b.id
       AND b.source NOT IN (SELECT source FROM sources_to_keep)
    RETURNING
      b.package,
      b.version,
      (SELECT arch_string FROM architecture WHERE id=b.architecture) AS architecture
    """
    result = session.execute(query, {"debugsuite_id": debug_suite.suite_id})
    for row in result:
        Logger.log(["remove", debug_suite.suite_name, row[0], row[1], row[2]])


def main():
    global Options, Logger

    cnf = Config()

    for i in ["Help", "No-Action", "All"]:
        key = "Manage-Debug-Suites::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    Arguments = [('h', "help", "Manage-Debug-Suites::Options::Help"),
                 ('n', "no-action", "Manage-Debug-Suites::Options::No-Action"),
                 ('a', "all", "Manage-Debug-Suites::Options::All")]

    debug_suite_names = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Manage-Debug-Suites::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger('manage-debug-suites', Options['No-Action'])

    with ArchiveTransaction() as transaction:
        session = transaction.session
        if Options['All']:
            if len(debug_suite_names) != 0:
                print("E: Cannot use both -a and a queue name")
                sys.exit(1)
            raise Exception("Not yet implemented.")
        else:
            debug_suites = session.query(Suite).filter(Suite.suite_name.in_(debug_suite_names))

        for debug_suite in debug_suites:
            Logger.log(['cleaning debug suite {0}'.format(debug_suite.suite_name)])
            clean(debug_suite, transaction)
        if not Options['No-Action']:
            transaction.commit()
        else:
            transaction.rollback()

    Logger.close()

#######################################################################################


if __name__ == '__main__':
    main()
