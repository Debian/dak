#! /usr/bin/env python
#
# Copyright (C) 2012, Ansgar Burchardt <ansgar@debian.org>
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

import apt_pkg
import sys

from daklib.config import Config
from daklib.dbconn import DBConn, Fingerprint, Keyring, Uid, ACL

def usage():
    print """Usage:
  dak acl set-fingerprints <acl-name>
  dak acl export-per-source <acl-name>

  set-fingerprints:
    Reads list of fingerprints from stdin and sets the ACL <acl-name> to these.
    Accepted input formats are "uid:<uid>", "name:<name>" and
    "fpr:<fingerprint>".

  export-per-source:
    Export per source upload rights for ACL <acl-name>.
"""

def get_fingerprint(entry, session):
    """get fingerprint for given ACL entry

    The entry is a string in one of these formats::

        uid:<uid>
        name:<name>
        fpr:<fingerprint>
        keyring:<keyring-name>

    @type  entry: string
    @param entry: ACL entry

    @param session: database session

    @rtype:  L{daklib.dbconn.Fingerprint} or C{None}
    @return: fingerprint for the entry
    """
    field, value = entry.split(":", 1)
    q = session.query(Fingerprint).join(Fingerprint.keyring).filter(Keyring.active == True)

    if field == 'uid':
        q = q.join(Fingerprint.uid).filter(Uid.uid == value)
    elif field == 'name':
        q = q.join(Fingerprint.uid).filter(Uid.name == value)
    elif field == 'fpr':
        q = q.filter(Fingerprint.fingerprint == value)
    elif field == 'keyring':
        q = q.filter(Keyring.keyring_name == value)
    else:
        raise Exception('Unknown selector "{0}".'.format(field))

    return q.all()

def acl_set_fingerprints(acl_name, entries):
    session = DBConn().session()
    acl = session.query(ACL).filter_by(name=acl_name).one()

    acl.fingerprints.clear()
    for entry in entries:
        entry = entry.strip()
        if entry.startswith('#') or len(entry) == 0:
            continue

        fps = get_fingerprint(entry, session)
        if len(fps) == 0:
            print "Unknown key for '{0}'".format(entry)
        else:
            acl.fingerprints.update(fps)

    session.commit()

def acl_export_per_source(acl_name):
    session = DBConn().session()
    acl = session.query(ACL).filter_by(name=acl_name).one()

    query = r"""
      SELECT
        f.fingerprint,
        (SELECT COALESCE(u.name, '') || ' <' || u.uid || '>'
           FROM uid u
           JOIN fingerprint f2 ON u.id = f2.uid
          WHERE f2.id = f.id) AS name,
        STRING_AGG(
          a.source
          || COALESCE(' (' || (SELECT fingerprint FROM fingerprint WHERE id = a.created_by_id) || ')', ''),
          E',\n ' ORDER BY a.source)
      FROM acl_per_source a
      JOIN fingerprint f ON a.fingerprint_id = f.id
      LEFT JOIN uid u ON f.uid = u.id
      WHERE a.acl_id = :acl_id
      GROUP BY f.id, f.fingerprint
      ORDER BY name
      """

    for row in session.execute(query, {'acl_id': acl.id}):
        print "Fingerprint:", row[0]
        print "Uid:", row[1]
        print "Allow:", row[2]
        print

    session.rollback()
    session.close()

def main(argv=None):
    if argv is None:
        argv = sys.argv

    if len(argv) != 3:
        usage()
        sys.exit(1)

    if argv[1] == 'set-fingerprints':
        acl_set_fingerprints(argv[2], sys.stdin)
    elif argv[1] == 'export-per-source':
        acl_export_per_source(argv[2])
    else:
        usage()
        sys.exit(1)
