#!/usr/bin/env python
# coding=utf8

"""
Clean up queue SQL

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
    print "Splitting up queues and fixing general design mistakes"

    try:
        c = self.db.cursor()

        cnf = Config()

        print "Adding build_queue table"
        c.execute("""CREATE TABLE build_queue (
                            id          SERIAL PRIMARY KEY,
                            queue_name  TEXT NOT NULL UNIQUE,
                            path        TEXT NOT NULL,
                            copy_files  BOOL DEFAULT FALSE NOT NULL)""")

        print "Adding policy_queue table"
        c.execute("""CREATE TABLE policy_queue (
                            id           SERIAL PRIMARY KEY,
                            queue_name   TEXT NOT NULL UNIQUE,
                            path         TEXT NOT NULL,
                            perms        CHAR(4) NOT NULL DEFAULT '0660' CHECK (perms SIMILAR TO '^[0-7][0-7][0-7][0-7]$'),
                            change_perms CHAR(4) NOT NULL DEFAULT '0660' CHECK (change_perms SIMILAR TO '^[0-7][0-7][0-7][0-7]$')
                            )""")

        print "Copying queues"
        queues = {}
        c.execute("""SELECT queue.id, queue.queue_name, queue.path, queue.copy_pool_files FROM queue""")

        for q in c.fetchall():
            queues[q[0]] = q[1]
            if q[1] in ['accepted', 'buildd', 'embargoed', 'unembargoed']:
                # Move to build_queue_table
                c.execute("""INSERT INTO build_queue (queue_name, path, copy_files)
                                   VALUES ('%s', '%s', '%s')""" % (q[1], q[2], q[3]))

            else:
                # Move to policy_queue_table
                c.execute("""INSERT INTO policy_queue (queue_name, path)
                                   VALUES ('%s', '%s')""" % (q[1], q[2]))


        print "Fixing up build_queue_files"
        c.execute("""ALTER TABLE queue_files DROP CONSTRAINT queue_files_queueid_fkey""")
        c.execute("""ALTER TABLE queue_files RENAME TO build_queue_files""")
        c.execute("""ALTER TABLE build_queue_files RENAME COLUMN queueid TO build_queue_id""")

        c.execute("""UPDATE build_queue_files
                        SET build_queue_id = (SELECT build_queue.id FROM build_queue
                                               WHERE build_queue.queue_name =
                                                (SELECT queue.queue_name FROM queue
                                                  WHERE queue.id = build_queue_files.build_queue_id))""")

        c.execute("""ALTER TABLE build_queue_files
                       ADD CONSTRAINT build_queue_files_build_queue_id_fkey
                       FOREIGN KEY (build_queue_id)
                       REFERENCES build_queue(id)
                       ON DELETE CASCADE""")


        c.execute("""ALTER TABLE suite DROP CONSTRAINT suite_policy_queue_id_fkey""")

        c.execute("""UPDATE suite
    SET policy_queue_id = (SELECT policy_queue.id FROM policy_queue
                             WHERE policy_queue.queue_name =
                              (SELECT queue.queue_name FROM queue
                               WHERE queue.id = suite.policy_queue_id))""")

        c.execute("""ALTER TABLE suite
                       ADD CONSTRAINT suite_policy_queue_fkey
                       FOREIGN KEY (policy_queue_id)
                       REFERENCES policy_queue (id)
                       ON DELETE RESTRICT""")

        c.execute("""ALTER TABLE known_changes DROP CONSTRAINT known_changes_approved_for_fkey""")
        c.execute("""ALTER TABLE known_changes DROP CONSTRAINT known_changes_in_queue_fkey""")

        c.execute("""UPDATE known_changes
    SET in_queue = (SELECT policy_queue.id FROM policy_queue
                             WHERE policy_queue.queue_name =
                              (SELECT queue.queue_name FROM queue
                               WHERE queue.id = known_changes.in_queue))""")

        c.execute("""ALTER TABLE known_changes
                       ADD CONSTRAINT known_changes_in_queue_fkey
                       FOREIGN KEY (in_queue)
                       REFERENCES policy_queue (id)
                       ON DELETE RESTRICT""")



        c.execute("""UPDATE known_changes
    SET approved_for = (SELECT policy_queue.id FROM policy_queue
                               WHERE policy_queue.queue_name =
                                (SELECT queue.queue_name FROM queue
                                  WHERE queue.id = known_changes.approved_for))""")

        c.execute("""ALTER TABLE known_changes
                       ADD CONSTRAINT known_changes_approved_for_fkey
                       FOREIGN KEY (in_queue)
                       REFERENCES policy_queue (id)
                       ON DELETE RESTRICT""")

        c.execute("""ALTER TABLE suite_queue_copy RENAME TO suite_build_queue_copy""")

        c.execute("""ALTER TABLE suite_build_queue_copy DROP CONSTRAINT suite_queue_copy_queue_fkey""")

        c.execute("""ALTER TABLE suite_build_queue_copy RENAME COLUMN queue TO build_queue_id""")

        c.execute("""UPDATE suite_build_queue_copy
    SET build_queue_id = (SELECT build_queue.id FROM build_queue
                                 WHERE build_queue.queue_name =
                                (SELECT queue.queue_name FROM queue
                                  WHERE queue.id = suite_build_queue_copy.build_queue_id))""")

        c.execute("""ALTER TABLE suite_build_queue_copy
                       ADD CONSTRAINT suite_build_queue_copy_build_queue_id_fkey
                       FOREIGN KEY (build_queue_id)
                       REFERENCES build_queue (id)
                       ON DELETE RESTRICT""")

        c.execute("""DROP TABLE changes_pending_files""")

        c.execute("""CREATE TABLE changes_pending_files (
                            id             SERIAL PRIMARY KEY,
                            filename       TEXT NOT NULL UNIQUE,
                            size           BIGINT NOT NULL,
                            md5sum         TEXT NOT NULL,
                            sha1sum        TEXT NOT NULL,
                            sha256sum      TEXT NOT NULL )""")

        c.execute("""CREATE TABLE changes_pending_files_map (
                            file_id        INT4 NOT NULL REFERENCES changes_pending_files (id),
                            change_id      INT4 NOT NULL REFERENCES known_changes (id),

                            PRIMARY KEY (file_id, change_id))""")

        c.execute("""CREATE TABLE changes_pending_source (
                            id             SERIAL PRIMARY KEY,
                            change_id      INT4 NOT NULL REFERENCES known_changes (id),
                            source         TEXT NOT NULL,
                            version        DEBVERSION NOT NULL,
                            maintainer_id  INT4 NOT NULL REFERENCES maintainer (id),
                            changedby_id   INT4 NOT NULL REFERENCES maintainer (id),
                            sig_fpr        INT4 NOT NULL REFERENCES fingerprint (id),
                            dm_upload_allowed BOOL NOT NULL DEFAULT FALSE )""")

        c.execute("""CREATE TABLE changes_pending_source_files (
                            pending_source_id INT4 REFERENCES changes_pending_source (id) NOT NULL,
                            pending_file_id   INT4 REFERENCES changes_pending_files (id) NOT NULL,

                            PRIMARY KEY (pending_source_id, pending_file_id) )""")

        c.execute("""CREATE TABLE changes_pending_binaries (
                            id                 SERIAL PRIMARY KEY,
                            change_id          INT4 NOT NULL REFERENCES known_changes (id),
                            package            TEXT NOT NULL,
                            version            DEBVERSION NOT NULL,
                            architecture_id    INT4 REFERENCES architecture (id) NOT NULL,
                            source_id          INT4 REFERENCES source (id),
                            pending_source_id  INT4 REFERENCES changes_pending_source (id),
                            pending_file_id    INT4 REFERENCES changes_pending_files (id),

                            UNIQUE (package, version, architecture_id),
                            CHECK (source_id IS NOT NULL or pending_source_id IS NOT NULL ) )""")

        print "Getting rid of old queue table"
        c.execute("""DROP TABLE queue""")

        print "Sorting out permission columns"
        c.execute("""UPDATE policy_queue SET perms = '0664' WHERE queue_name IN ('proposedupdates', 'oldproposedupdates')""")

        print "Moving known_changes table"
        c.execute("""ALTER TABLE known_changes RENAME TO changes""")

        print "Sorting out permissions"

        for t in ['build_queue', 'policy_queue', 'build_queue_files',
                  'changes_pending_binaries', 'changes_pending_source_files',
                  'changes_pending_source', 'changes_pending_files',
                  'changes_pool_files', 'suite_build_queue_copy']:
            c.execute("GRANT SELECT ON %s TO public" % t)
            c.execute("GRANT ALL ON %s TO ftpmaster" % t)

        for s in ['queue_files_id_seq', 'build_queue_id_seq',
                  'changes_pending_source_id_seq',
                  'changes_pending_binaries_id_seq',
                  'changes_pending_files_id_seq',
                  'changes_pending_source_id_seq',
                  'known_changes_id_seq',
                  'policy_queue_id_seq']:
            c.execute("GRANT USAGE ON %s TO ftpmaster" % s)

        print "Committing"
        c.execute("UPDATE config SET value = '22' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.InternalError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply queue_build 21, rollback issued. Error message : %s" % (str(msg)))
