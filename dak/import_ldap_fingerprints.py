#!/usr/bin/env python

# Sync fingerprint and uid tables with a debian.org LDAP DB
# Copyright (C) 2003, 2004, 2006  James Troup <james@nocrew.org>

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

# <elmo>  ping@debian.org ?
# <aj>    missing@ ? wtfru@ ?
# <elmo>  giggle
# <elmo>  I like wtfru
# <aj>    all you have to do is retrofit wtfru into an acronym and no one
#         could possibly be offended!
# <elmo>  aj: worried terriers for russian unity ?
# <aj>    uhhh
# <aj>    ooookkkaaaaay
# <elmo>  wthru is a little less offensive maybe?  but myabe that's
#         just because I read h as heck, not hell
# <elmo>  ho hum
# <aj>    (surely the "f" stands for "freedom" though...)
# <elmo>  where the freedom are you?
# <aj>    'xactly
# <elmo>  or worried terriers freed (of) russian unilateralism ?
# <aj>    freedom -- it's the "foo" of the 21st century
# <aj>    oo, how about "wat@" as in wherefore art thou?
# <neuro> or worried attack terriers
# <aj>    Waning Trysts Feared - Return? Unavailable?
# <aj>    (i find all these terriers more worrying, than worried)
# <neuro> worrying attack terriers, then

################################################################################

import commands, ldap, pg, re, sys
import apt_pkg
import daklib.database as database
import daklib.utils as utils

################################################################################

Cnf = None
projectB = None

re_gpg_fingerprint = re.compile(r"^\s+Key fingerprint = (.*)$", re.MULTILINE)
re_debian_address = re.compile(r"^.*<(.*)@debian\.org>$", re.MULTILINE)

################################################################################

def usage(exit_code=0):
    print """Usage: dak import-ldap-fingerprints
Syncs fingerprint and uid tables with a debian.org LDAP DB

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def get_ldap_value(entry, value):
    ret = entry.get(value)
    if not ret or ret[0] == "" or ret[0] == "-":
        return ""
    else:
        # FIXME: what about > 0 ?
        return ret[0] + " "

def get_ldap_name(entry):
    name = get_ldap_value(entry, "cn")
    name += get_ldap_value(entry, "mn")
    name += get_ldap_value(entry, "sn")
    return name.rstrip()

def escape_string(str):
    return str.replace("'", "\\'")

def main():
    global Cnf, projectB

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Import-LDAP-Fingerprints::Options::Help")]
    for i in [ "help" ]:
        if not Cnf.has_key("Import-LDAP-Fingerprints::Options::%s" % (i)):
            Cnf["Import-LDAP-Fingerprints::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Import-LDAP-Fingerprints::Options")
    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    LDAPDn = Cnf["Import-LDAP-Fingerprints::LDAPDn"]
    LDAPServer = Cnf["Import-LDAP-Fingerprints::LDAPServer"]
    l = ldap.open(LDAPServer)
    l.simple_bind_s("","")
    Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
                       "(&(keyfingerprint=*)(gidnumber=%s))" % (Cnf["Import-Users-From-Passwd::ValidGID"]),
                       ["uid", "keyfingerprint", "cn", "mn", "sn"])


    projectB.query("BEGIN WORK")


    # Sync LDAP with DB
    db_fin_uid = {}
    db_uid_name = {}
    ldap_fin_uid_id = {}
    q = projectB.query("""
SELECT f.fingerprint, f.id, u.uid FROM fingerprint f, uid u WHERE f.uid = u.id
 UNION SELECT f.fingerprint, f.id, null FROM fingerprint f where f.uid is null""")
    for i in q.getresult():
        (fingerprint, fingerprint_id, uid) = i
        db_fin_uid[fingerprint] = (uid, fingerprint_id)

    q = projectB.query("SELECT id, name FROM uid")
    for i in q.getresult():
        (uid, name) = i
        db_uid_name[uid] = name

    for i in Attrs:
        entry = i[1]
        fingerprints = entry["keyFingerPrint"]
        uid = entry["uid"][0]
        name = get_ldap_name(entry)
        uid_id = database.get_or_set_uid_id(uid)

        if not db_uid_name.has_key(uid_id) or db_uid_name[uid_id] != name:
            q = projectB.query("UPDATE uid SET name = '%s' WHERE id = %d" % (escape_string(name), uid_id))
            print "Assigning name of %s as %s" % (uid, name)

        for fingerprint in fingerprints:
            ldap_fin_uid_id[fingerprint] = (uid, uid_id)
            if db_fin_uid.has_key(fingerprint):
                (existing_uid, fingerprint_id) = db_fin_uid[fingerprint]
                if not existing_uid:
                    q = projectB.query("UPDATE fingerprint SET uid = %s WHERE id = %s" % (uid_id, fingerprint_id))
                    print "Assigning %s to 0x%s." % (uid, fingerprint)
                elif existing_uid == uid:
                    pass
                elif existing_uid[:3] == "dm:":
                    q = projectB.query("UPDATE fingerprint SET uid = %s WHERE id = %s" % (uid_id, fingerprint_id))
                    print "Promoting DM %s to DD %s with keyid 0x%s." % (existing_uid, uid, fingerprint)
                else:
                    utils.warn("%s has %s in LDAP, but projectB says it should be %s." % (uid, fingerprint, existing_uid))

    # Try to update people who sign with non-primary key
    q = projectB.query("SELECT fingerprint, id FROM fingerprint WHERE uid is null")
    for i in q.getresult():
        (fingerprint, fingerprint_id) = i
        cmd = "gpg --no-default-keyring %s --fingerprint %s" \
              % (utils.gpg_keyring_args(), fingerprint)
        (result, output) = commands.getstatusoutput(cmd)
        if result == 0:
            m = re_gpg_fingerprint.search(output)
            if not m:
                print output
                utils.fubar("0x%s: No fingerprint found in gpg output but it returned 0?\n%s" % (fingerprint, utils.prefix_multi_line_string(output, " [GPG output:] ")))
            primary_key = m.group(1)
            primary_key = primary_key.replace(" ","")
            if not ldap_fin_uid_id.has_key(primary_key):
                utils.warn("0x%s (from 0x%s): no UID found in LDAP" % (primary_key, fingerprint))
            else:
                (uid, uid_id) = ldap_fin_uid_id[primary_key]
                q = projectB.query("UPDATE fingerprint SET uid = %s WHERE id = %s" % (uid_id, fingerprint_id))
                print "Assigning %s to 0x%s." % (uid, fingerprint)
        else:
            extra_keyrings = ""
            for keyring in Cnf.ValueList("Import-LDAP-Fingerprints::ExtraKeyrings"):
                extra_keyrings += " --keyring=%s" % (keyring)
            cmd = "gpg %s %s --list-key %s" \
                  % (utils.gpg_keyring_args(), extra_keyrings, fingerprint)
            (result, output) = commands.getstatusoutput(cmd)
            if result != 0:
                cmd = "gpg --keyserver=%s --allow-non-selfsigned-uid --recv-key %s" % (Cnf["Import-LDAP-Fingerprints::KeyServer"], fingerprint)
                (result, output) = commands.getstatusoutput(cmd)
                if result != 0:
                    print "0x%s: NOT found on keyserver." % (fingerprint)
                    print cmd
                    print result
                    print output
                    continue
                else:
                    cmd = "gpg --list-key %s" % (fingerprint)
                    (result, output) = commands.getstatusoutput(cmd)
                    if result != 0:
                        print "0x%s: --list-key returned error after --recv-key didn't." % (fingerprint)
                        print cmd
                        print result
                        print output
                        continue
            m = re_debian_address.search(output)
            if m:
                guess_uid = m.group(1)
            else:
                guess_uid = "???"
            name = " ".join(output.split('\n')[0].split()[3:])
            print "0x%s -> %s -> %s" % (fingerprint, name, guess_uid)

            # FIXME: make me optionally non-interactive
            # FIXME: default to the guessed ID
            uid = None
            while not uid:
                uid = utils.our_raw_input("Map to which UID ? ")
                Attrs = l.search_s(LDAPDn,ldap.SCOPE_ONELEVEL,"(uid=%s)" % (uid), ["cn","mn","sn"])
                if not Attrs:
                    print "That UID doesn't exist in LDAP!"
                    uid = None
                else:
                    entry = Attrs[0][1]
                    name = get_ldap_name(entry)
                    prompt = "Map to %s - %s (y/N) ? " % (uid, name.replace("  "," "))
                    yn = utils.our_raw_input(prompt).lower()
                    if yn == "y":
                        uid_id = database.get_or_set_uid_id(uid)
                        projectB.query("UPDATE fingerprint SET uid = %s WHERE id = %s" % (uid_id, fingerprint_id))
                        print "Assigning %s to 0x%s." % (uid, fingerprint)
                    else:
                        uid = None
    projectB.query("COMMIT WORK")

############################################################

if __name__ == '__main__':
    main()
