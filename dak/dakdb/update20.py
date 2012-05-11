#!/usr/bin/env python
# coding=utf8

"""
Add policy queue handling support

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
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
import traceback

from daklib.dak_exceptions import DBUpdateError
from daklib.config import Config

################################################################################

def do_update(self):
    print "Updating use of queue table"

    try:
        c = self.db.cursor()

        cnf = Config()

        print "Adding path to queue table"
        c.execute("ALTER TABLE queue ADD COLUMN path TEXT")
        c.execute("SELECT * FROM queue")
        rows = c.fetchall()
        seenqueues = {}
        for row in rows:
            dir = cnf["Dir::Queue::%s" % row[1]].rstrip('/')
            seenqueues[row[1].lower()] = 1
            print "Setting %s queue to use path %s" % (row[1], dir)
            c.execute("UPDATE queue SET path = %s WHERE id = %s", (dir, row[0]))

        print "Adding missing queues to the queue table"
        for q in cnf.subtree("Dir::Queue").keys():
            qname = q.lower()
            if qname in seenqueues.keys():
                continue
            if qname in ["done", "holding", "reject", "newstage", "btsversiontrack"]:
                print "Skipping queue %s" % qname
                continue
            pth = cnf["Dir::Queue::%s" % qname].rstrip('/')
            if not os.path.exists(pth):
                print "Skipping %s as %s does not exist" % (qname, pth)
                continue

            print "Adding %s queue with path %s" % (qname, pth)
            c.execute("INSERT INTO queue (queue_name, path) VALUES (%s, %s)", (qname, pth))
            seenqueues[qname] = 1

        print "Adding queue and approved_for columns to known_changes"
        c.execute("ALTER TABLE known_changes ADD COLUMN in_queue INT4 REFERENCES queue(id) DEFAULT NULL")
        c.execute("ALTER TABLE known_changes ADD COLUMN approved_for INT4 REFERENCES queue(id) DEFAULT NULL")

        print "Adding policy queue column to suite table"
        c.execute("ALTER TABLE suite DROP COLUMN policy_engine")
        c.execute("ALTER TABLE suite ADD COLUMN policy_queue_id INT4 REFERENCES queue(id) DEFAULT NULL")
        # Handle some of our common cases automatically
        if seenqueues.has_key('proposedupdates'):
            c.execute("""UPDATE suite SET policy_queue_id = (SELECT id FROM queue WHERE queue_name = 'proposedupdates')
                                      WHERE suite_name = 'proposed-updates'""")

        if seenqueues.has_key('oldproposedupdates'):
            c.execute("""UPDATE suite SET policy_queue_id = (SELECT id FROM queue WHERE queue_name = 'oldproposedupdates')
                                      WHERE suite_name = 'oldstable-proposed-updates'""")

        print "Committing"
        c.execute("UPDATE config SET value = '20' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply debversion update 20, rollback issued. Error message : %s" % (str(msg)))
