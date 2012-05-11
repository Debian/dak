#!/usr/bin/env python
# coding=utf8

"""
Modify queue autobuild support

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
    print "Updating queue_build table"

    try:
        c = self.db.cursor()

        cnf = Config()

        print "Adding copy_files field to queue table"
        c.execute("ALTER TABLE queue ADD copy_pool_files BOOL NOT NULL DEFAULT FALSE")

        print "Adding queue_files table"

        c.execute("""CREATE TABLE queue_files (
    id            SERIAL PRIMARY KEY,
    queueid       INT4 NOT NULL REFERENCES queue(id) ON DELETE RESTRICT,
    insertdate    TIMESTAMP NOT NULL DEFAULT now(),
    lastused      TIMESTAMP DEFAULT NULL,
    filename      TEXT NOT NULL,
    fileid        INT4 REFERENCES files(id) ON DELETE CASCADE)""")

        c.execute("""SELECT queue_build.filename, queue_build.last_used, queue_build.queue
                       FROM queue_build""")

        for r in c.fetchall():
            print r[0]
            filename = r[0]
            last_used = r[1]
            queue = r[2]
            try:
                endlink = os.readlink(filename)
                c.execute("SELECT files.id FROM files WHERE filename LIKE '%%%s'" % endlink[endlink.rindex('/')+1:])
                f = c.fetchone()
                c.execute("""INSERT INTO queue_files (queueid, lastused, filename, fileid) VALUES
                                                     (%s, now(), %s, %s)""", (queue, filename[filename.rindex('/')+1:], f[0]))
            except OSError as e:
                print "Can't find file %s (%s)" % (filename, e)

        print "Dropping old queue_build table"
        c.execute("DROP TABLE queue_build")

        print "Adding changes_pending_files table"
        c.execute("""CREATE TABLE changes_pending_files (
                        id           SERIAL PRIMARY KEY,
                        changeid     INT4 NOT NULL REFERENCES known_changes(id) ON DELETE CASCADE,
                        filename     TEXT NOT NULL,
                        source       BOOL NOT NULL DEFAULT FALSE,
                        filesize     BIGINT NOT NULL,
                        md5sum       TEXT NOT NULL,
                        sha1sum      TEXT NOT NULL,
                        sha256sum    TEXT NOT NULL)""")


        print "Adding changes_pool_files table"
        c.execute("""CREATE TABLE changes_pool_files (
                        changeid     INT4 NOT NULL REFERENCES known_changes(id) ON DELETE CASCADE,
                        fileid       INT4 NOT NULL REFERENCES files(id) ON DELETE RESTRICT,

                        PRIMARY KEY (changeid, fileid))""")

        print "Adding suite_queue_copy table"
        c.execute("""CREATE TABLE suite_queue_copy (
                        suite        INT4 NOT NULL REFERENCES suite(id),
                        queue        INT4 NOT NULL REFERENCES queue(id),

                        PRIMARY KEY (suite, queue))""")

        # Link all suites from accepted
        c.execute("""SELECT suite.id FROM suite""")
        for s in c.fetchall():
            c.execute("""INSERT INTO suite_queue_copy (suite, queue) VALUES (%s, (SELECT id FROM queue WHERE queue_name = 'accepted'))""", s)

        # Parse the config and add any buildd stuff
        cnf = Config()
        c.execute("""INSERT INTO queue (queue_name, path) VALUES ('buildd', '%s')""" % cnf["Dir::QueueBuild"].rstrip('/'))

        for s in cnf.value_list("Dinstall::QueueBuildSuites"):
            c.execute("""INSERT INTO suite_queue_copy (suite, queue)
                              VALUES ( (SELECT id FROM suite WHERE suite_name = '%s'),
                                       (SELECT id FROM queue WHERE queue_name = 'buildd'))""" % s.lower())

        print "Committing"
        c.execute("UPDATE config SET value = '21' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply queue_build 21, rollback issued. Error message : %s" % (str(msg)))
