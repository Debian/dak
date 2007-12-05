#!/usr/bin/env python

# Imports a keyring into the database
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

import daklib.database, daklib.logging
import apt_pkg, pg
import sys, os, email.Utils, re

# Globals
Cnf = None
Options = None
projectB = None
Logger = None

################################################################################

# These could possibly be daklib.db functions, and reused by
# import-ldap-fingerprints

def get_uid_info():
    byname = {}
    byid = {}
    q = projectB.query("SELECT id, uid, name FROM uid")
    for (id, uid, name) in q.getresult():
        byname[uid] = (id, name)
	byid[id] = (uid, name)
    return (byname, byid)

def get_fingerprint_info():
    fins = {}
    q = projectB.query("SELECT f.fingerprint, f.id, f.uid, f.keyring FROM fingerprint f")
    for (fingerprint, fingerprint_id, uid, keyring) in q.getresult():
        fins[fingerprint] = (uid, fingerprint_id, keyring)
    return fins

################################################################################

class Keyring:
	gpg_invocation = "gpg --no-default-keyring --keyring %s" +\
			 " --with-colons --fingerprint --fingerprint"
	keys = {}

 	def de_escape_str(self, str):
		esclist = re.split(r'(\\x..)', str)
		for x in range(1,len(esclist),2):
			esclist[x] = "%c" % (int(esclist[x][2:],16))
		return "".join(esclist)

	def __init__(self, keyring):
		k = os.popen(self.gpg_invocation % keyring, "r")
		keys = self.keys
		key = None
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
				name = self.de_escape_str(name)
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

	def desired_users(self, format="%s"):
		if not Options["Generate-Users"]:
			return ({}, {})

		byuid = {}
		byname = {}
		keys = self.keys
		any_invalid = False
		for x in keys.keys():
			if keys[x]["email"] == "invalid-uid":
				any_invalid = True
			else:
				uid = format % keys[x]["email"]
				id = daklib.database.get_or_set_uid_id(uid)
				byuid[id] = (uid, keys[x]["name"])
				byname[uid] = (id, keys[x]["name"])
		if any_invalid:
			uid = format % "invalid-uid"
			id = daklib.database.get_or_set_uid_id(uid)
			byuid[id] = (uid, "ungeneratable user id")
			byname[uid] = (id, "ungeneratable user id")
		return (byname, byuid)

################################################################################

def usage (exit_code=0):
    print """Usage: dak import-keyring [OPTION]... [KEYRING]
  -h, --help                  show this help and exit.
  -U, --generate-users FMT    generate uid entries from keyring as FMT"""
    sys.exit(exit_code)


################################################################################

def main():
    global Cnf, projectB, Options

    Cnf = daklib.utils.get_conf()
    Arguments = [('h',"help","Import-Keyring::Options::Help"),
		 ('U',"generate-users","Import-Keyring::Options::Generate-Users", "HasArg"),
		]

    for i in [ "help", "report-changes", "generate-users" ]:
        if not Cnf.has_key("Import-Keyring::Options::%s" % (i)):
            Cnf["Import-Keyring::Options::%s" % (i)] = ""

    keyring_names = apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Import-Keyring::Options")
    if Options["Help"]:
        usage()

    uid_format = "%s"
    if Options["Generate-Users"]:
        uid_format = Options["Generate-Users"]

    changes = []   # (uid, changes strings)

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)

    projectB.query("BEGIN WORK")

    if len(keyring_names) != 1:
	usage(1)

    # Parse the keyring
    keyringname = keyring_names[0]
    keyring = Keyring(keyringname)

    keyring_id = daklib.database.get_or_set_keyring_id(
			keyringname.split("/")[-1])

    # If we're generating uids, make sure we have entries in the uid
    # table for every uid
    (desuid_byname, desuid_byid) = keyring.desired_users(uid_format)

    # Cache all the existing fingerprint and uid entries
    db_fin_info = get_fingerprint_info()
    (db_uid_byname, db_uid_byid) = get_uid_info()

    # Update full names of uids

    for id in desuid_byid.keys():
        uid = (id, desuid_byid[id][0])
        name = desuid_byid[id][1]
	oname = db_uid_byid[id][1]
    	if name and oname != name:
	    changes.append((uid[1], "Full name: %s\n" % (name)))
            projectB.query("UPDATE uid SET name = '%s' WHERE id = %s" %
	    	(pg.escape_string(name), id))

    # Work out what the fingerprint table should look like for the keys
    # in this keyring
    fpr = {}
    for z in keyring.keys.keys():
	id = db_uid_byname.get(uid_format % keyring.keys[z]["email"], [None])[0]
        if id == None:
	    id = db_fin_info.get(keyring.keys[z]["fingerprints"][0], [None])[0]
	for y in keyring.keys[z]["fingerprints"]:
	    fpr[y] = (id,keyring_id)

    # For any keys that used to be in this keyring, disassociate them.
    # We don't change the uid, leaving that to for historical info; if
    # the id should change, it'll be set when importing another keyring
    # or importing ldap fingerprints.

    for f,(u,fid,kr) in db_fin_info.iteritems():
        if kr != keyring_id: continue
	if f in fpr: continue
	changes.append((db_uid_byid.get(u, [None])[0], "Removed key: %s\n" % (f)))
	projectB.query("UPDATE fingerprint SET keyring = NULL WHERE id = %d" % (fid))
	
    # For the keys in this keyring, add/update any fingerprints that've
    # changed.

    for f in fpr:
        newuid = fpr[f][0]
	newuiduid = db_uid_byid.get(newuid, [None])[0] 
	(olduid, oldfid, oldkid) = db_fin_info.get(f, [-1,-1,-1])
	if olduid == None: olduid = -1
	if oldkid == None: oldkid = -1
	if oldfid == -1:
	    changes.append((newuiduid, "Added key: %s\n" % (f)))
            if newuid:
	        projectB.query("INSERT INTO fingerprint (fingerprint, uid, keyring) VALUES ('%s', %d, %d)" % (f, newuid, keyring_id))
	    else:
	        projectB.query("INSERT INTO fingerprint (fingerprint, keyring) VALUES ('%s', %d)" % (f, keyring_id))
	else:
	    if newuid and olduid != newuid:
		if olduid != -1:
		    changes.append((newuiduid, "Linked key: %s (formerly belonging to %s)" % (f, db_uid_byid[olduid][0])))
		else:
		    changes.append((newuiduid, "Linked key: %s (formerly unowned)\n" % (f)))
	        projectB.query("UPDATE fingerprint SET uid = %d WHERE id = %d" % (newuid, oldfid))

	    if oldkid != keyring_id:
	        projectB.query("UPDATE fingerprint SET keyring = %d WHERE id = %d" % (keyring_id, oldfid))

    # All done!

    projectB.query("COMMIT WORK")

    changesd = {}
    for (k, v) in changes:
        if k not in changesd: changesd[k] = ""
        changesd[k] += "    " + v

    keys = changesd.keys()
    keys.sort()
    for k in keys:
        print "%s\n%s" % (k, changesd[k])

################################################################################

if __name__ == '__main__':
    main()
