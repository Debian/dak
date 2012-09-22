#!/usr/bin/env python

""" Imports a keyring into the database """
# Copyright (C) 2007  Anthony Towns <aj@erisian.com.au>
# Copyright (C) 2009  Mark Hymers <mhy@debian.org>

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

import sys, os, re
import apt_pkg, ldap

from daklib.config import Config
from daklib.dbconn import *

# Globals
Options = None

################################################################################

def get_uid_info(session):
    byname = {}
    byid = {}
    q = session.execute("SELECT id, uid, name FROM uid")
    for (keyid, uid, name) in q.fetchall():
        byname[uid] = (keyid, name)
        byid[keyid] = (uid, name)

    return (byname, byid)

def get_fingerprint_info(session):
    fins = {}
    q = session.execute("SELECT f.fingerprint, f.id, f.uid, f.keyring FROM fingerprint f")
    for (fingerprint, fingerprint_id, uid, keyring) in q.fetchall():
        fins[fingerprint] = (uid, fingerprint_id, keyring)
    return fins

def list_uids(session, pattern):
    sql_pattern = "%%%s%%" % pattern
    message = "List UIDs matching pattern %s" % sql_pattern
    message += "\n" + ("=" * len(message))
    print message
    uid_query = session.query(Uid).filter(Uid.uid.ilike(sql_pattern))
    for uid in uid_query.all():
	print "\nuid %s" % uid.uid
	for fp in uid.fingerprint:
	    print "    fingerprint %s" % fp.fingerprint
	    keyring = "unknown"
	    if fp.keyring:
		keyring = fp.keyring.keyring_name
	    print "        keyring %s" % keyring

################################################################################

def usage (exit_code=0):
    print """Usage: dak import-keyring [OPTION]... [KEYRING]
  -h, --help                  show this help and exit.
  -L, --import-ldap-users     generate uid entries for keyring from LDAP
  -U, --generate-users FMT    generate uid entries from keyring as FMT
  -l, --list-uids STRING      list all uids matching *STRING*
  -n, --no-action             don't change database"""
    sys.exit(exit_code)


################################################################################

def main():
    global Options

    cnf = Config()
    Arguments = [('h',"help","Import-Keyring::Options::Help"),
                 ('L',"import-ldap-users","Import-Keyring::Options::Import-Ldap-Users"),
                 ('U',"generate-users","Import-Keyring::Options::Generate-Users", "HasArg"),
                 ('l',"list-uids","Import-Keyring::Options::List-UIDs", "HasArg"),
                 ('n',"no-action","Import-Keyring::Options::No-Action"),
                ]

    for i in [ "help", "report-changes", "generate-users",
	    "import-ldap-users", "list-uids", "no-action" ]:
        if not cnf.has_key("Import-Keyring::Options::%s" % (i)):
            cnf["Import-Keyring::Options::%s" % (i)] = ""

    keyring_names = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    ### Parse options

    Options = cnf.subtree("Import-Keyring::Options")

    if Options["Help"]:
        usage()

    ### Initialise
    session = DBConn().session()

    if Options["List-UIDs"]:
	list_uids(session, Options["List-UIDs"])
	sys.exit(0)

    if len(keyring_names) != 1:
        usage(1)

    ### Keep track of changes made
    changes = []   # (uid, changes strings)

    ### Cache all the existing fingerprint entries
    db_fin_info = get_fingerprint_info(session)

    ### Parse the keyring

    keyringname = keyring_names[0]
    keyring = get_keyring(keyringname, session)
    if not keyring:
        print "E: Can't load keyring %s from database" % keyringname
        sys.exit(1)

    keyring.load_keys(keyringname)

    ### Generate new uid entries if they're needed (from LDAP or the keyring)
    if Options["Generate-Users"]:
        format = Options["Generate-Users"]
        (desuid_byname, desuid_byid) = keyring.generate_users_from_keyring(Options["Generate-Users"], session)
    elif Options["Import-Ldap-Users"]:
        (desuid_byname, desuid_byid) = keyring.import_users_from_ldap(session)
    else:
        (desuid_byname, desuid_byid) = ({}, {})

    ### Cache all the existing uid entries
    (db_uid_byname, db_uid_byid) = get_uid_info(session)

    ### Update full names of applicable users
    for keyid in desuid_byid.keys():
        uid = (keyid, desuid_byid[keyid][0])
        name = desuid_byid[keyid][1]
        oname = db_uid_byid[keyid][1]
        if name and oname != name:
            changes.append((uid[1], "Full name: %s" % (name)))
            session.execute("UPDATE uid SET name = :name WHERE id = :keyid",
                            {'name': name, 'keyid': keyid})

    # The fingerprint table (fpr) points to a uid and a keyring.
    #   If the uid is being decided here (ldap/generate) we set it to it.
    #   Otherwise, if the fingerprint table already has a uid (which we've
    #     cached earlier), we preserve it.
    #   Otherwise we leave it as None

    fpr = {}
    for z in keyring.keys.keys():
        keyid = db_uid_byname.get(keyring.keys[z].get("uid", None), [None])[0]
        if keyid == None:
            keyid = db_fin_info.get(keyring.keys[z]["fingerprints"][0], [None])[0]
        for y in keyring.keys[z]["fingerprints"]:
            fpr[y] = (keyid, keyring.keyring_id)

    # For any keys that used to be in this keyring, disassociate them.
    # We don't change the uid, leaving that for historical info; if
    # the id should change, it'll be set when importing another keyring.

    for f,(u,fid,kr) in db_fin_info.iteritems():
        if kr != keyring.keyring_id:
            continue

        if f in fpr:
            continue

        changes.append((db_uid_byid.get(u, [None])[0], "Removed key: %s" % (f)))
        session.execute("""UPDATE fingerprint
                              SET keyring = NULL
                            WHERE id = :fprid""", {'fprid': fid})

    # For the keys in this keyring, add/update any fingerprints that've
    # changed.

    for f in fpr:
        newuid = fpr[f][0]
        newuiduid = db_uid_byid.get(newuid, [None])[0]

        (olduid, oldfid, oldkid) = db_fin_info.get(f, [-1,-1,-1])

        if olduid == None:
            olduid = -1

        if oldkid == None:
            oldkid = -1

        if oldfid == -1:
            changes.append((newuiduid, "Added key: %s" % (f)))
            fp = Fingerprint()
            fp.fingerprint = f
            fp.keyring_id = keyring.keyring_id
            if newuid:
                fp.uid_id = newuid

            session.add(fp)
            session.flush()

        else:
            if newuid and olduid != newuid and olduid == -1:
                changes.append((newuiduid, "Linked key: %s" % f))
                changes.append((newuiduid, "  (formerly unowned)"))
                session.execute("UPDATE fingerprint SET uid = :uid WHERE id = :fpr",
                                {'uid': newuid, 'fpr': oldfid})

            # Don't move a key from a keyring with a higher priority to a lower one
            if oldkid != keyring.keyring_id:
                movekey = False
                if oldkid == -1:
                    movekey = True
                else:
                    try:
                        oldkeyring = session.query(Keyring).filter_by(keyring_id=oldkid).one()
                    except NotFoundError:
                        print "ERROR: Cannot find old keyring with id %s" % oldkid
                        sys.exit(1)

                    if oldkeyring.priority < keyring.priority:
                        movekey = True

                # Only change the keyring if it won't result in a loss of permissions
                if movekey:
                    session.execute("""UPDATE fingerprint
                                          SET keyring = :keyring
                                        WHERE id = :fpr""",
                                    {'keyring': keyring.keyring_id,
                                     'fpr': oldfid})

                    session.flush()

                else:
                    print "Key %s exists in both %s and %s keyrings. Not demoting." % (f,
                                                                                       oldkeyring.keyring_name,
                                                                                       keyring.keyring_name)

    # All done!
    if Options["No-Action"]:
	session.rollback()
    else:
	session.commit()

    # Print a summary
    changesd = {}
    for (k, v) in changes:
        if k not in changesd:
            changesd[k] = ""
        changesd[k] += "    %s\n" % (v)

    keys = changesd.keys()
    keys.sort()
    for k in keys:
        print "%s\n%s\n" % (k, changesd[k])

################################################################################

if __name__ == '__main__':
    main()
