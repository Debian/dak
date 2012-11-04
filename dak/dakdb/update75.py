#!/usr/bin/env python
# coding=utf8

"""
Multi-archive support; convert policy and build queues to regular suites

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2012 Ansgar Burchardt <ansgar@debian.org>
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

import psycopg2
from daklib.dak_exceptions import DBUpdateError
from daklib.config import Config

import os

################################################################################

def _track_files_per_archive(cnf, c):
    c.execute("SELECT id FROM archive")
    (archive_id,) = c.fetchone()

    if c.fetchone() is not None:
        raise DBUpdateError("Cannot automatically upgrade from installation with multiple archives.")

    c.execute("""CREATE TABLE files_archive_map (
      file_id INT NOT NULL REFERENCES files(id),
      archive_id INT NOT NULL REFERENCES archive(id),
      component_id INT NOT NULL REFERENCES component(id),
      last_used TIMESTAMP DEFAULT NULL,
      created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (file_id, archive_id, component_id)
    )""")

    c.execute("""INSERT INTO files_archive_map (file_id, archive_id, component_id)
       SELECT f.id, %s, l.component
       FROM files f
       JOIN location l ON f.location = l.id""", (archive_id,))

    c.execute("""UPDATE files f SET filename = substring(f.filename FROM c.name || '/(.*)')
      FROM location l, component c
      WHERE f.location = l.id AND l.component = c.id
        AND f.filename LIKE c.name || '/%'""")

    # NOTE: The location table would need these changes, but we drop it later
    #       anyway.
    #c.execute("""UPDATE location l SET path = path || c.name || '/'
    #  FROM component c
    #  WHERE l.component = c.id
    #    AND l.path NOT LIKE '%/' || c.name || '/'""")

    c.execute("DROP VIEW IF EXISTS binfiles_suite_component_arch")
    c.execute("ALTER TABLE files DROP COLUMN location")
    c.execute("DROP TABLE location")

def _convert_policy_queues(cnf, c):
    base = cnf['Dir::Base']
    new_path = os.path.join(base, 'new')
    policy_path = os.path.join(base, 'policy')

    # Forget changes in (old) policy queues so they can be processed again.
    c.execute("DROP TABLE IF EXISTS build_queue_policy_files")
    c.execute("DROP TABLE IF EXISTS build_queue_files")
    c.execute("DROP TABLE IF EXISTS changes_pending_binaries")
    c.execute("DROP TABLE IF EXISTS changes_pending_source_files")
    c.execute("DROP TABLE IF EXISTS changes_pending_source")
    c.execute("DROP TABLE IF EXISTS changes_pending_files_map")
    c.execute("DROP TABLE IF EXISTS changes_pending_files")
    c.execute("DROP TABLE IF EXISTS changes_pool_files")
    c.execute("DELETE FROM changes WHERE in_queue IS NOT NULL")

    # newstage and unchecked are no longer queues
    c.execute("""
      DELETE FROM policy_queue
      WHERE queue_name IN ('newstage', 'unchecked')
    """)

    # Create archive for NEW
    c.execute("INSERT INTO archive (name, description, path, tainted, use_morgue, mode) VALUES ('new', 'new queue', %s, 't', 'f', '0640') RETURNING (id)", (new_path,))
    (new_archive_id,) = c.fetchone()

    # Create archive for policy queues
    c.execute("INSERT INTO archive (name, description, path, use_morgue) VALUES ('policy', 'policy queues', %s, 'f') RETURNING (id)", (policy_path,))
    (archive_id,) = c.fetchone()

    # Add suites for policy queues
    c.execute("""
      INSERT INTO suite
        (archive_id, suite_name, origin, label, description, signingkeys)
      SELECT
        %s, queue_name, origin, label, releasedescription, NULLIF(ARRAY[signingkey], ARRAY[NULL])
      FROM policy_queue
      WHERE queue_name NOT IN ('unchecked')
    """, (archive_id,))

    # move NEW to its own archive
    c.execute("UPDATE suite SET archive_id=%s WHERE suite_name IN ('byhand', 'new')", (new_archive_id,))

    c.execute("""ALTER TABLE policy_queue
      DROP COLUMN origin,
      DROP COLUMN label,
      DROP COLUMN releasedescription,
      DROP COLUMN signingkey,
      DROP COLUMN stay_of_execution,
      DROP COLUMN perms,
      ADD COLUMN suite_id INT REFERENCES suite(id)
    """)

    c.execute("UPDATE policy_queue pq SET suite_id=s.id FROM suite s WHERE s.suite_name = pq.queue_name")
    c.execute("ALTER TABLE policy_queue ALTER COLUMN suite_id SET NOT NULL")

    c.execute("""INSERT INTO suite_architectures (suite, architecture)
        SELECT pq.suite_id, sa.architecture
          FROM policy_queue pq
          JOIN suite ON pq.id = suite.policy_queue_id
          JOIN suite_architectures sa ON suite.id = sa.suite
         WHERE pq.queue_name NOT IN ('byhand', 'new')
         GROUP BY pq.suite_id, sa.architecture""")

    # We only add architectures from suite_architectures to only add
    # arches actually in use. It's not too important to have the
    # right set of arches for policy queues anyway unless you want
    # to generate Packages indices.
    c.execute("""INSERT INTO suite_architectures (suite, architecture)
        SELECT DISTINCT pq.suite_id, sa.architecture
          FROM policy_queue pq, suite_architectures sa
         WHERE pq.queue_name IN ('byhand', 'new')""")

    c.execute("""CREATE TABLE policy_queue_upload (
        id SERIAL NOT NULL PRIMARY KEY,
        policy_queue_id INT NOT NULL REFERENCES policy_queue(id),
        target_suite_id INT NOT NULL REFERENCES suite(id),
        changes_id INT NOT NULL REFERENCES changes(id),
        source_id INT REFERENCES source(id),
        UNIQUE (policy_queue_id, target_suite_id, changes_id)
    )""")

    c.execute("""CREATE TABLE policy_queue_upload_binaries_map (
        policy_queue_upload_id INT REFERENCES policy_queue_upload(id) ON DELETE CASCADE,
        binary_id INT REFERENCES binaries(id),
        PRIMARY KEY (policy_queue_upload_id, binary_id)
    )""")

    c.execute("""
      CREATE TABLE policy_queue_byhand_file (
        id SERIAL NOT NULL PRIMARY KEY,
        upload_id INT NOT NULL REFERENCES policy_queue_upload(id),
        filename TEXT NOT NULL,
        processed BOOLEAN NOT NULL DEFAULT 'f'
      )""")

    c.execute("""ALTER TABLE changes
      DROP COLUMN in_queue,
      DROP COLUMN approved_for
    """)

def _convert_build_queues(cnf, c):
    base = cnf['Dir::Base']
    build_queue_path = os.path.join(base, 'build-queues')

    c.execute("INSERT INTO archive (name, description, path, tainted, use_morgue) VALUES ('build-queues', 'build queues', %s, 't', 'f') RETURNING id", [build_queue_path])
    archive_id, = c.fetchone()

    c.execute("ALTER TABLE build_queue ADD COLUMN suite_id INT REFERENCES suite(id)")

    c.execute("""
      INSERT INTO suite
        (archive_id, suite_name, origin, label, description, signingkeys, notautomatic)
      SELECT
        %s, queue_name, origin, label, releasedescription, NULLIF(ARRAY[signingkey], ARRAY[NULL]), notautomatic
      FROM build_queue
    """, [archive_id])
    c.execute("UPDATE build_queue bq SET suite_id=(SELECT id FROM suite s WHERE s.suite_name = bq.queue_name)")
    c.execute("ALTER TABLE build_queue ALTER COLUMN suite_id SET NOT NULL")

    c.execute("""INSERT INTO suite_architectures (suite, architecture)
        SELECT bq.suite_id, sa.architecture
          FROM build_queue bq
          JOIN suite_build_queue_copy sbqc ON bq.id = sbqc.build_queue_id
          JOIN suite ON sbqc.suite = suite.id
          JOIN suite_architectures sa ON suite.id = sa.suite
         GROUP BY bq.suite_id, sa.architecture""")

    c.execute("""ALTER TABLE build_queue
                   DROP COLUMN path,
                   DROP COLUMN copy_files,
                   DROP COLUMN origin,
                   DROP COLUMN label,
                   DROP COLUMN releasedescription,
                   DROP COLUMN signingkey,
                   DROP COLUMN notautomatic""")

def do_update(self):
    print __doc__
    try:
        cnf = Config()
        if 'Dir::Base' not in cnf:
            print """
MANUAL UPGRADE INSTRUCTIONS
===========================

This database update will convert policy and build queues to regular suites.
For these archives will be created under Dir::Base:

  NEW:           <base>/new
  policy queues: <base>/policy
  build queues:  <base>/build-queues

Please add Dir::Base to dak.conf and try the update again.  Once the database
upgrade is finished, you will have to reprocess all uploads currently in
policy queues: just move them back to unchecked manually.
"""
            raise DBUpdateError("Please update dak.conf and try again.")

        c = self.db.cursor()

        _track_files_per_archive(cnf, c)
        _convert_policy_queues(cnf, c)
        _convert_build_queues(cnf, c)

        c.execute("UPDATE config SET value = '75' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 75, rollback issued. Error message : %s' % (str(msg)))
