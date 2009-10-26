#!/usr/bin/env python

""" Imports a keyring into the database """
# Copyright (C) 2007  Anthony Towns <aj@erisian.com.au>

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
import apt_pkg, ldap, email.Utils

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils


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

################################################################################

def get_ldap_name(entry):
    name = []
    for k in ["cn", "mn", "sn"]:
        ret = entry.get(k)
        if ret and ret[0] != "" and ret[0] != "-":
            name.append(ret[0])
    return " ".join(name)

################################################################################

class Keyring(object):
    gpg_invocation = "gpg --no-default-keyring --keyring %s" +\
                     " --with-colons --fingerprint --fingerprint"
    keys = {}
    fpr_lookup = {}

    def de_escape_gpg_str(self, str):
        esclist = re.split(r'(\\x..)', str)
        for x in range(1,len(esclist),2):
            esclist[x] = "%c" % (int(esclist[x][2:],16))
        return "".join(esclist)

    def __init__(self, keyring):
        self.cnf = Config()
        k = os.popen(self.gpg_invocation % keyring, "r")
        keys = self.keys
        key = None
        fpr_lookup = self.fpr_lookup
        signingkey = False
        for line in k.xreadlines():
            field = line.split(":")
            if field[0] == "pub":
                key = field[4]
                (name, addr) = email.Utils.parseaddr(field[9])
                name = re.sub(r"\s*[(].*[)]", "", name)
                if name == "" or addr == "" or "@" not in addr:
                    name = field[9]
                    addr = "invalid-uid"
                name = self.de_escape_gpg_str(name)
                keys[key] = {"email": addr}
                if name != "": keys[key]["name"] = name
                keys[key]["aliases"] = [name]
                keys[key]["fingerprints"] = []
                signingkey = True
            elif key and field[0] == "sub" and len(field) >= 12:
                signingkey = ("s" in field[11])
            elif key and field[0] == "uid":
                (name, addr) = email.Utils.parseaddr(field[9])
                if name and name not in keys[key]["aliases"]:
                    keys[key]["aliases"].append(name)
            elif signingkey and field[0] == "fpr":
                keys[key]["fingerprints"].append(field[9])
                fpr_lookup[field[9]] = key

    def generate_desired_users(self):
        if Options["Generate-Users"]:
            format = Options["Generate-Users"]
            return self.generate_users_from_keyring(format)
        if Options["Import-Ldap-Users"]:
            return self.import_users_from_ldap()
        return ({}, {})

    def import_users_from_ldap(self):
        LDAPDn = self.cnf["Import-LDAP-Fingerprints::LDAPDn"]
        LDAPServer = self.cnf["Import-LDAP-Fingerprints::LDAPServer"]
        l = ldap.open(LDAPServer)
        l.simple_bind_s("","")
        Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
               "(&(keyfingerprint=*)(gidnumber=%s))" % (self.cnf["Import-Users-From-Passwd::ValidGID"]),
               ["uid", "keyfingerprint", "cn", "mn", "sn"])

        ldap_fin_uid_id = {}

        byuid = {}
        byname = {}
        keys = self.keys
        fpr_lookup = self.fpr_lookup

        for i in Attrs:
            entry = i[1]
            uid = entry["uid"][0]
            name = get_ldap_name(entry)
            fingerprints = entry["keyFingerPrint"]
            keyid = None
            for f in fingerprints:
                key = fpr_lookup.get(f, None)
                if key not in keys: continue
                keys[key]["uid"] = uid

                if keyid != None: continue
                keyid = database.get_or_set_uid_id(uid)
                byuid[keyid] = (uid, name)
                byname[uid] = (keyid, name)

        return (byname, byuid)

    def generate_users_from_keyring(self, format):
        byuid = {}
        byname = {}
        keys = self.keys
        any_invalid = False
        for x in keys.keys():
            if keys[x]["email"] == "invalid-uid":
                any_invalid = True
                keys[x]["uid"] = format % "invalid-uid"
            else:
                uid = format % keys[x]["email"]
                keyid = database.get_or_set_uid_id(uid)
                byuid[keyid] = (uid, keys[x]["name"])
                byname[uid] = (keyid, keys[x]["name"])
                keys[x]["uid"] = uid
        if any_invalid:
            uid = format % "invalid-uid"
            keyid = database.get_or_set_uid_id(uid)
            byuid[keyid] = (uid, "ungeneratable user id")
            byname[uid] = (keyid, "ungeneratable user id")
        return (byname, byuid)

################################################################################

def usage (exit_code=0):
    print """Usage: dak import-keyring [OPTION]... [KEYRING]
  -h, --help                  show this help and exit.
  -L, --import-ldap-users     generate uid entries for keyring from LDAP
  -U, --generate-users FMT    generate uid entries from keyring as FMT"""
    sys.exit(exit_code)


################################################################################

def main():
    global Options

    cnf = Config()
    Arguments = [('h',"help","Import-Keyring::Options::Help"),
                 ('L',"import-ldap-users","Import-Keyring::Options::Import-Ldap-Users"),
                 ('U',"generate-users","Import-Keyring::Options::Generate-Users", "HasArg"),
                ]

    for i in [ "help", "report-changes", "generate-users", "import-ldap-users" ]:
        if not cnf.has_key("Import-Keyring::Options::%s" % (i)):
            cnf["Import-Keyring::Options::%s" % (i)] = ""

    keyring_names = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)

    ### Parse options

    Options = cnf.SubTree("Import-Keyring::Options")
    if Options["Help"]:
        usage()

    if len(keyring_names) != 1:
        usage(1)

    ### Keep track of changes made

    changes = []   # (uid, changes strings)

    ### Initialise
    session = DBConn().session()

    ### Cache all the existing fingerprint entries
    db_fin_info = get_fingerprint_info(session)

    ### Parse the keyring

    keyringname = keyring_names[0]
    keyring = Keyring(keyringname)

    is_dm = "false"
    if cnf.has_key("Import-Keyring::"+keyringname+"::Debian-Maintainer"):
        session.execute("UPDATE keyrings SET debian_maintainer = :dm WHERE name = :name",
                        {'dm': cnf["Import-Keyring::"+keyringname+"::Debian-Maintainer"],
                         'name': keyringname.split("/")[-1]})

        is_dm = cnf["Import-Keyring::"+keyringname+"::Debian-Maintainer"]

    keyring_id = get_or_set_keyring(
        keyringname.split("/")[-1], session,
    ).keyring_id

    ### Generate new uid entries if they're needed (from LDAP or the keyring)
    (desuid_byname, desuid_byid) = keyring.generate_desired_users()

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
            fpr[y] = (keyid,keyring_id)

    # For any keys that used to be in this keyring, disassociate them.
    # We don't change the uid, leaving that for historical info; if
    # the id should change, it'll be set when importing another keyring.

    for f,(u,fid,kr) in db_fin_info.iteritems():
        if kr != keyring_id: continue
        if f in fpr: continue
        changes.append((db_uid_byid.get(u, [None])[0], "Removed key: %s" % (f)))
        session.execute("UPDATE fingerprint SET keyring = NULL WHERE id = :fprid", {'fprid': fid})

    # For the keys in this keyring, add/update any fingerprints that've
    # changed.

    for f in fpr:
        newuid = fpr[f][0]
        newuiduid = db_uid_byid.get(newuid, [None])[0]
        (olduid, oldfid, oldkid) = db_fin_info.get(f, [-1,-1,-1])
        if olduid == None: olduid = -1
        if oldkid == None: oldkid = -1
        if oldfid == -1:
            changes.append((newuiduid, "Added key: %s" % (f)))
            if newuid:
                session.execute("""INSERT INTO fingerprint (fingerprint, uid, keyring)
                                        VALUES (:fpr, :uid, :keyring)""",
                                {'fpr': f, 'uid': uid, 'keyring': keyring_id})
            else:
                session.execute("""INSERT INTO fingerprint (fingerprint, keyring)
                                        VALUES (:fpr, :keyring)""",
                                {'fpr': f, 'keyring': keyring_id})
        else:
            if newuid and olduid != newuid:
                if olduid != -1:
                    changes.append((newuiduid, "Linked key: %s" % f))
                    changes.append((newuiduid, "  (formerly belonging to %s)" % (db_uid_byid[olduid][0])))
                else:
                    changes.append((newuiduid, "Linked key: %s" % f))
                    changes.append((newuiduid, "  (formerly unowned)"))
                session.execute("UPDATE fingerprint SET uid = :uid WHERE id = :fpr",
                                {'uid': newuid, 'fpr': oldfid})

            if oldkid != keyring_id:
                # Only change the keyring if it won't result in a loss of permissions
                q = session.execute("SELECT debian_maintainer FROM keyrings WHERE id = :keyring",
                                    {'keyring': keyring_id})
                if is_dm == "false" and not q.fetchall()[0][0]:
                    session.execute("UPDATE fingerprint SET keyring = :keyring WHERE id = :fpr",
                                    {'keyring': keyring_id, 'fpr': oldfid})
                else:
                    print "Key %s exists in both DM and DD keyrings. Not demoting." % (f)

    # All done!
    session.commit()

    changesd = {}
    for (k, v) in changes:
        if k not in changesd: changesd[k] = ""
        changesd[k] += "    %s\n" % (v)

    keys = changesd.keys()
    keys.sort()
    for k in keys:
        print "%s\n%s\n" % (k, changesd[k])

################################################################################

if __name__ == '__main__':
    main()
