#!/usr/bin/env python

""" Sync PostgreSQL users with system users """
# Copyright (C) 2001, 2002, 2006  James Troup <james@nocrew.org>

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

# <aj> ARRRGGGHHH
# <aj> what's wrong with me!?!?!?
# <aj> i was just nice to some mormon doorknockers!!!
# <Omnic> AJ?!?!
# <aj> i know!!!!!
# <Omnic> I'm gonna have to kick your ass when you come over
# <Culus> aj: GET THE HELL OUT OF THE CABAL! :P

################################################################################

import pwd
import sys
import re
import apt_pkg

from daklib.config import Config
from daklib.dbconn import *
from daklib import utils

################################################################################

def usage (exit_code=0):
    print """Usage: dak import-users-from-passwd [OPTION]...
Sync PostgreSQL's users with system users.

  -h, --help                 show this help and exit
  -n, --no-action            don't do anything
  -q, --quiet                be quiet about what is being done
  -v, --verbose              explain what is being done"""
    sys.exit(exit_code)

################################################################################

def main ():
    cnf = Config()

    Arguments = [('n', "no-action", "Import-Users-From-Passwd::Options::No-Action"),
                 ('q', "quiet", "Import-Users-From-Passwd::Options::Quiet"),
                 ('v', "verbose", "Import-Users-From-Passwd::Options::Verbose"),
                 ('h', "help", "Import-Users-From-Passwd::Options::Help")]
    for i in [ "no-action", "quiet", "verbose", "help" ]:
        if not cnf.has_key("Import-Users-From-Passwd::Options::%s" % (i)):
            cnf["Import-Users-From-Passwd::Options::%s" % (i)] = ""

    arguments = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Import-Users-From-Passwd::Options")

    if Options["Help"]:
        usage()
    elif arguments:
        utils.warn("dak import-users-from-passwd takes no non-option arguments.")
        usage(1)

    session = DBConn().session()
    valid_gid = int(cnf.get("Import-Users-From-Passwd::ValidGID",""))

    passwd_unames = {}
    for entry in pwd.getpwall():
        uname = entry[0]
        gid = entry[3]
        if valid_gid and gid != valid_gid:
            if Options["Verbose"]:
                print "Skipping %s (GID %s != Valid GID %s)." % (uname, gid, valid_gid)
            continue
        passwd_unames[uname] = ""

    postgres_unames = {}
    q = session.execute("SELECT usename FROM pg_user")
    for i in q.fetchall():
        uname = i[0]
        postgres_unames[uname] = ""

    known_postgres_unames = {}
    for i in cnf.get("Import-Users-From-Passwd::KnownPostgres","").split(","):
        uname = i.strip()
        known_postgres_unames[uname] = ""

    keys = postgres_unames.keys()
    keys.sort()
    for uname in keys:
        if not passwd_unames.has_key(uname) and not known_postgres_unames.has_key(uname):
            print "I: Deleting %s from Postgres, no longer in passwd or list of known Postgres users" % (uname)
            q = session.execute('DROP USER "%s"' % (uname))

    keys = passwd_unames.keys()
    keys.sort()
    safe_name = re.compile('^[A-Za-z0-9]+$')
    for uname in keys:
        if not postgres_unames.has_key(uname):
            if not Options["Quiet"]:
                print "Creating %s user in Postgres." % (uname)
            if not Options["No-Action"]:
                if safe_name.match(uname):
                    # NB: I never figured out how to use a bind parameter for this query
                    # XXX: Fix this as it looks like a potential SQL injection attack to me
                    #      (hence the safe_name match we do)
                    try:
                        q = session.execute('CREATE USER "%s"' % (uname))
                        session.commit()
                    except Exception as e:
                        utils.warn("Could not create user %s (%s)" % (uname, str(e)))
                        session.rollback()
                else:
                    print "NOT CREATING USER %s.  Doesn't match safety regex" % uname

    session.commit()

#######################################################################################

if __name__ == '__main__':
    main()
