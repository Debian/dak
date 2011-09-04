#!/usr/bin/env python
# coding=utf8

"""
Adding table to get rid of queue/done checks

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
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

################################################################################


################################################################################

import psycopg2
import time
import os
import datetime
from daklib.dak_exceptions import DBUpdateError, InvalidDscError, ChangesUnicodeError
from daklib.config import Config
from daklib.changes import Changes
from daklib.utils import parse_changes, warn, gpgv_get_status_output, process_gpgv_output

################################################################################

def check_signature (sig_filename, data_filename=""):
    keyrings = [
        "/home/joerg/keyring/keyrings/debian-keyring.gpg",
        "/home/joerg/keyring/keyrings/debian-maintainers.gpg",
        "/home/joerg/keyring/keyrings/debian-role-keys.gpg",
        "/home/joerg/keyring/keyrings/emeritus-keyring.pgp",
        "/home/joerg/keyring/keyrings/emeritus-keyring.gpg",
        "/home/joerg/keyring/keyrings/removed-keys.gpg",
        "/home/joerg/keyring/keyrings/removed-keys.pgp"
        ]

    keyringargs = " ".join(["--keyring %s" % x for x in keyrings ])

    # Build the command line
    status_read, status_write = os.pipe()
    cmd = "gpgv --status-fd %s %s %s" % (status_write, keyringargs, sig_filename)

    # Invoke gpgv on the file
    (output, status, exit_status) = gpgv_get_status_output(cmd, status_read, status_write)

    # Process the status-fd output
    (keywords, internal_error) = process_gpgv_output(status)

    # If we failed to parse the status-fd output, let's just whine and bail now
    if internal_error:
        warn("Couldn't parse signature")
        return None

    # usually one would check for bad things here. We, however, do not care.

    # Next check gpgv exited with a zero return code
    if exit_status:
        warn("Couldn't parse signature")
        return None

    # Sanity check the good stuff we expect
    if not keywords.has_key("VALIDSIG"):
        warn("Couldn't parse signature")
    else:
        args = keywords["VALIDSIG"]
        if len(args) < 1:
            warn("Couldn't parse signature")
        else:
            fingerprint = args[0]

    return fingerprint

################################################################################

def do_update(self):
    print "Adding known_changes table"

    try:
        c = self.db.cursor()
        c.execute("""
                    CREATE TABLE known_changes (
                    id SERIAL PRIMARY KEY,
                    changesname TEXT NOT NULL,
                    seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                    source TEXT NOT NULL,
                    binaries TEXT NOT NULL,
                    architecture TEXT NOT NULL,
                    version TEXT NOT NULL,
                    distribution TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    maintainer TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    changedby TEXT NOT NULL,
                    date TEXT NOT NULL,
                    UNIQUE (changesname)
            )
        """)
        c.execute("CREATE INDEX changesname_ind ON known_changes(changesname)")
        c.execute("CREATE INDEX changestimestamp_ind ON known_changes(seen)")
        c.execute("CREATE INDEX changessource_ind ON known_changes(source)")
        c.execute("CREATE INDEX changesdistribution_ind ON known_changes(distribution)")
        c.execute("CREATE INDEX changesurgency_ind ON known_changes(urgency)")

        c.execute("GRANT ALL ON known_changes TO ftpmaster;")
        c.execute("GRANT SELECT ON known_changes TO public;")

        c.execute("UPDATE config SET value = '18' WHERE name = 'db_revision'")
        self.db.commit()

        print "Done. Now looking for old changes files"
        count = 0
        failure = 0
        cnf = Config()
        for directory in [ "Accepted", "Byhand", "Done", "New", "ProposedUpdates", "OldProposedUpdates" ]:
            checkdir = cnf["Dir::Queue::%s" % (directory) ]
            if os.path.exists(checkdir):
                print "Looking into %s" % (checkdir)
                for filename in os.listdir(checkdir):
                    if not filename.endswith(".changes"):
                        # Only interested in changes files.
                        continue
                    try:
                        count += 1
                        print "Directory %s, file %7d, failures %3d. (%s)" % (directory, count, failure, filename)
                        changes = Changes()
                        changes.changes_file = filename
                        changesfile = os.path.join(checkdir, filename)
                        changes.changes = parse_changes(changesfile, signing_rules=-1)
                        changes.changes["fingerprint"] = check_signature(changesfile)
                        changes.add_known_changes(directory)
                    except InvalidDscError as line:
                        warn("syntax error in .dsc file '%s', line %s." % (f, line))
                        failure += 1
                    except ChangesUnicodeError:
                        warn("found invalid changes file, not properly utf-8 encoded")
                        failure += 1

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply knownchanges update 18, rollback issued. Error message : %s" % (str(msg)))
