#!/usr/bin/env python

""" Check for users with no packages in the archive """
# Copyright (C) 2003, 2006  James Troup <james@nocrew.org>

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

import ldap, sys, time
import apt_pkg

from daklib.dbconn import *
from daklib.config import Config
from daklib.utils import fubar

################################################################################

def usage(exit_code=0):
    print """Usage: dak find-null-maintainers
Checks for users with no packages in the archive

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def get_ldap_value(entry, value):
    ret = entry.get(value)
    if not ret:
        return ""
    else:
        # FIXME: what about > 0 ?
        return ret[0]

def main():
    cnf = Config()

    Arguments = [('h',"help","Find-Null-Maintainers::Options::Help")]
    for i in [ "help" ]:
        if not cnf.has_key("Find-Null-Maintainers::Options::%s" % (i)):
            cnf["Find-Null-Maintainers::Options::%s" % (i)] = ""

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.subtree("Find-Null-Maintainers::Options")
    if Options["Help"]:
        usage()

    if not cnf.has_key('Import-LDAP-Fingerprints::LDAPServer'):
        fubar("Import-LDAP-Fingerprints::LDAPServer not configured")

    if not cnf.has_key('Import-LDAP-Fingerprints::LDAPDn'):
        fubar("Import-LDAP-Fingerprints::LDAPDn not configured")

    session = DBConn().session()

    print "Getting info from the LDAP server..."
    LDAPDn = cnf["Import-LDAP-Fingerprints::LDAPDn"]
    LDAPServer = cnf["Import-LDAP-Fingerprints::LDAPServer"]
    l = ldap.open(LDAPServer)
    l.simple_bind_s("","")
    Attrs = l.search_s(LDAPDn, ldap.SCOPE_ONELEVEL,
                       "(&(keyfingerprint=*)(gidnumber=%s))" % (cnf["Import-Users-From-Passwd::ValidGID"]),
                       ["uid", "cn", "mn", "sn", "createTimestamp"])


    db_uid = {}
    db_unstable_uid = {}

    print "Getting UID info for entire archive..."
    q = session.execute("SELECT DISTINCT u.uid FROM uid u, fingerprint f WHERE f.uid = u.id")
    for i in q.fetchall():
        db_uid[i[0]] = ""

    print "Getting UID info for unstable..."
    q = session.execute("""
SELECT DISTINCT u.uid FROM suite su, src_associations sa, source s, fingerprint f, uid u
 WHERE f.uid = u.id AND sa.source = s.id AND sa.suite = su.id
   AND su.suite_name = 'unstable' AND s.sig_fpr = f.id
UNION
SELECT DISTINCT u.uid FROM suite su, bin_associations ba, binaries b, fingerprint f, uid u
 WHERE f.uid = u.id AND ba.bin = b.id AND ba.suite = su.id
   AND su.suite_name = 'unstable' AND b.sig_fpr = f.id""")
    for i in q.fetchall():
        db_unstable_uid[i[0]] = ""

    now = time.time()

    for i in Attrs:
        entry = i[1]
        uid = entry["uid"][0]
        created = time.mktime(time.strptime(entry["createTimestamp"][0][:8], '%Y%m%d'))
        diff = now - created
        # 31536000 is 1 year in seconds, i.e. 60 * 60 * 24 * 365
        if diff < 31536000 / 2:
            when = "Less than 6 months ago"
        elif diff < 31536000:
            when = "Less than 1 year ago"
        elif diff < 31536000 * 1.5:
            when = "Less than 18 months ago"
        elif diff < 31536000 * 2:
            when = "Less than 2 years ago"
        elif diff < 31536000 * 3:
            when = "Less than 3 years ago"
        else:
            when = "More than 3 years ago"
        name = " ".join([get_ldap_value(entry, "cn"),
                         get_ldap_value(entry, "mn"),
                         get_ldap_value(entry, "sn")])
        if not db_uid.has_key(uid):
            print "NONE %s (%s) %s" % (uid, name, when)
        else:
            if not db_unstable_uid.has_key(uid):
                print "NOT_UNSTABLE %s (%s) %s" % (uid, name, when)

############################################################

if __name__ == '__main__':
    main()
