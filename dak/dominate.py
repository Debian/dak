#!/usr/bin/python

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
import apt_pkg, sys

Options = None
Logger = None

def fetch(reason, query, args, session):
    idList = []
    for row in session.execute(query, args).fetchall():
        (id, package, version, suite_name, architecture) = row
        if Options['No-Action']:
            print "Delete %s %s from %s architecture %s (%s, %d)" % \
                (package, version, suite_name, architecture, reason, id)
        else:
            Logger.log([reason, package, version, suite_name, \
	        architecture, id])
        idList.append(id)
    return idList

def obsoleteAnyByAllAssociations(suite, session):
    query = """
        SELECT obsolete.id, package, obsolete.version, suite_name, arch_string
            FROM obsolete_any_by_all_associations AS obsolete
            JOIN architecture ON obsolete.architecture = architecture.id
            JOIN suite ON obsolete.suite = suite.id
            WHERE suite = :suite
    """
    return fetch('newer_all', query, { 'suite': suite }, session)

def obsoleteAnyAssociations(suite, session):
    query = """
        SELECT obsolete.id, package, obsolete.version, suite_name, arch_string
            FROM obsolete_any_associations AS obsolete
            JOIN architecture ON obsolete.architecture = architecture.id
            JOIN suite ON obsolete.suite = suite.id
            WHERE suite = :suite
    """
    return fetch('newer_any', query, { 'suite': suite }, session)

def obsoleteSrcAssociations(suite, session):
    query = """
        SELECT obsolete.id, source, obsolete.version, suite_name,
	    'source' AS arch_string
            FROM obsolete_src_associations AS obsolete
            JOIN suite ON obsolete.suite = suite.id
            WHERE suite = :suite
    """
    return fetch('old_and_unreferenced', query, { 'suite': suite }, session)

def obsoleteAllAssociations(suite, session):
    query = """
        SELECT obsolete.id, package, obsolete.version, suite_name,
	    'all' AS arch_string
            FROM obsolete_all_associations AS obsolete
            JOIN suite ON obsolete.suite = suite.id
            WHERE suite = :suite
    """
    return fetch('old_and_unreferenced', query, { 'suite': suite }, session)

def deleteAssociations(table, idList, session):
    query = """
        DELETE
            FROM %s
            WHERE id = :id
    """ % table
    session.execute(query, [{'id': id} for id in idList])

def doDaDoDa(suite, session):
    # keep this part disabled because it is too dangerous
    #idList = obsoleteAnyByAllAssociations(suite, session)
    #deleteAssociations('bin_associations', idList, session)

    idList = obsoleteAnyAssociations(suite, session)
    deleteAssociations('bin_associations', idList, session)

    idList = obsoleteSrcAssociations(suite, session)
    deleteAssociations('src_associations', idList, session)

    idList = obsoleteAllAssociations(suite, session)
    deleteAssociations('bin_associations', idList, session)

def usage():
    print """Usage: dak dominate [OPTIONS]
Remove obsolete source and binary associations from suites.

    -s, --suite=SUITE          act on this suite
    -h, --help                 show this help and exit
    -n, --no-action            don't commit changes
    -f, --force                also clean up untouchable suites

SUITE can be comma (or space) separated list, e.g.
    --suite=testing,unstable"""
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
    if 'Suite' not in Options:
        query_suites = DBConn().session().query(Suite)
        suites = [suite.suite_name for suite in query_suites]
        cnf['Obsolete::Options::Suite'] = str(','.join(suites))

    Logger = daklog.Logger("dominate")
    session = DBConn().session()
    for suite_name in utils.split_args(Options['Suite']):
        suite = session.query(Suite).filter_by(suite_name = suite_name).one()

        # Skip policy queues. We don't want to remove obsolete packages from those.
        policy_queue = session.query(PolicyQueue).filter_by(suite=suite).first()
        if policy_queue is not None:
            continue

        if not suite.untouchable or Options['Force']:
            doDaDoDa(suite.suite_id, session)
    if Options['No-Action']:
        session.rollback()
    else:
        session.commit()
    Logger.close()

if __name__ == '__main__':
    main()

