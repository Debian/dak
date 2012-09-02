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
from daklib.dbconn import DBConn, Fingerprint, Uid, ACL

def usage():
    print """Usage: dak acl set-fingerprints <acl-name>

Reads list of fingerprints from stdin and sets the ACL <acl-name> to these.
"""

def get_fingerprint(entry, session):
    """get fingerprint for given ACL entry

    The entry is a string in one of these formats::

        uid:<uid>
        name:<name>
        fpr:<fingerprint>

    @type  entry: string
    @param entry: ACL entry

    @param session: database session

    @rtype:  L{daklib.dbconn.Fingerprint} or C{None}
    @return: fingerprint for the entry
    """
    field, value = entry.split(":", 1)
    q = session.query(Fingerprint)

    if field == 'uid':
        q = q.join(Fingerprint.uid).filter(Uid.uid == value)
    elif field == 'name':
        q = q.join(Fingerprint.uid).filter(Uid.name == value)
    elif field == 'fpr':
        q = q.filter(Fingerprint.fingerprint == value)

    return q.all()

def acl_set_fingerprints(acl_name, entries):
    session = DBConn().session()
    acl = session.query(ACL).filter_by(name=acl_name).one()

    acl.fingerprints.clear()
    for entry in entries:
        entry = entry.strip()
        fps = get_fingerprint(entry, session)
        if len(fps) == 0:
            print "Unknown key for '{0}'".format(entry)
        else:
            acl.fingerprints.update(fps)

    session.commit()

def main(argv=None):
    if argv is None:
        argv = sys.argv

    if len(argv) != 3 or argv[1] != 'set-fingerprints':
        usage()
        sys.exit(1)

    acl_set_fingerprints(argv[2], sys.stdin)
