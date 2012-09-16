#!/usr/bin/env python
# coding=utf8

"""
switch to new ACL implementation and add pre-suite NEW

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

statements = [
"""ALTER TABLE suite ADD COLUMN new_queue_id INT REFERENCES policy_queue(id)""",

"""CREATE TABLE acl (
    id SERIAL PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    is_global BOOLEAN NOT NULL DEFAULT 'f',

    match_fingerprint BOOLEAN NOT NULL DEFAULT 'f',
    match_keyring_id INTEGER REFERENCES keyrings(id),

    allow_new BOOLEAN NOT NULL DEFAULT 'f',
    allow_source BOOLEAN NOT NULL DEFAULT 'f',
    allow_binary BOOLEAN NOT NULL DEFAULT 'f',
    allow_binary_all BOOLEAN NOT NULL DEFAULT 'f',
    allow_binary_only BOOLEAN NOT NULL DEFAULT 'f',
    allow_hijack BOOLEAN NOT NULL DEFAULT 'f',
    allow_per_source BOOLEAN NOT NULL DEFAULT 'f',
    deny_per_source BOOLEAN NOT NULL DEFAULT 'f'
    )""",

"""CREATE TABLE acl_architecture_map (
    acl_id INTEGER NOT NULL REFERENCES acl(id) ON DELETE CASCADE,
    architecture_id INTEGER NOT NULL REFERENCES architecture(id) ON DELETE CASCADE,
    PRIMARY KEY (acl_id, architecture_id)
    )""",

"""CREATE TABLE acl_fingerprint_map (
    acl_id INTEGER NOT NULL REFERENCES acl(id) ON DELETE CASCADE,
    fingerprint_id INTEGER NOT NULL REFERENCES fingerprint(id) ON DELETE CASCADE,
    PRIMARY KEY (acl_id, fingerprint_id)
    )""",

"""CREATE TABLE acl_per_source (
    acl_id INTEGER NOT NULL REFERENCES acl(id) ON DELETE CASCADE,
    fingerprint_id INTEGER NOT NULL REFERENCES fingerprint(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    reason TEXT,
    PRIMARY KEY (acl_id, fingerprint_id, source)
    )""",

"""CREATE TABLE suite_acl_map (
    suite_id INTEGER NOT NULL REFERENCES suite(id) ON DELETE CASCADE,
    acl_id INTEGER NOT NULL REFERENCES acl(id),
    PRIMARY KEY (suite_id, acl_id)
    )""",
]

################################################################################

def get_buildd_acl_id(c, keyring_id):
    c.execute("""
        SELECT 'buildd-' || STRING_AGG(a.arch_string, '+' ORDER BY a.arch_string)
          FROM keyring_acl_map kam
          JOIN architecture a ON kam.architecture_id = a.id
         WHERE kam.keyring_id = %(keyring_id)s
        """, {'keyring_id': keyring_id})
    acl_name, = c.fetchone()

    c.execute('SELECT id FROM acl WHERE name = %(acl_name)s', {'acl_name': acl_name})
    row = c.fetchone()
    if row is not None:
        return row[0]

    c.execute("""
        INSERT INTO acl
               (        name, allow_new, allow_source, allow_binary, allow_binary_all, allow_binary_only, allow_hijack)
        VALUES (%(acl_name)s,       't',          'f',          't',              'f',               't',          't')
        RETURNING id""", {'acl_name': acl_name})
    acl_id, = c.fetchone()

    c.execute("""INSERT INTO acl_architecture_map (acl_id, architecture_id)
                 SELECT %(acl_id)s, architecture_id
                   FROM keyring_acl_map
                  WHERE keyring_id = %(keyring_id)s""",
              {'acl_id': acl_id, 'keyring_id': keyring_id})

    return acl_id

def get_acl_id(c, acl_dd, acl_dm, keyring_id, source_acl_id, binary_acl_id):
    c.execute('SELECT access_level FROM source_acl WHERE id = %(source_acl_id)s', {'source_acl_id': source_acl_id})
    row = c.fetchone()
    if row is not None:
        source_acl = row[0]
    else:
        source_acl = None

    c.execute('SELECT access_level FROM binary_acl WHERE id = %(binary_acl_id)s', {'binary_acl_id': binary_acl_id})
    row = c.fetchone()
    if row is not None:
        binary_acl = row[0]
    else:
        binary_acl = None

    if source_acl == 'full' and binary_acl == 'full':
        return acl_dd
    elif source_acl == 'dm' and binary_acl == 'full':
        return acl_dm
    elif source_acl is None and binary_acl == 'map':
        return get_buildd_acl_id(c, keyring_id)

    raise Exception('Cannot convert ACL combination automatically: binary_acl={0}, source_acl={1}'.format(binary_acl, source_acl))

def do_update(self):
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("""
            INSERT INTO acl
                   (name, allow_new, allow_source, allow_binary, allow_binary_all, allow_binary_only, allow_hijack)
            VALUES ('dd',       't',          't',          't',              't',               't',          't')
            RETURNING id""")
        acl_dd, = c.fetchone()

        c.execute("""
            INSERT INTO acl
                   (name, allow_new, allow_source, allow_binary, allow_binary_all, allow_binary_only, allow_per_source, allow_hijack)
            VALUES ('dm',       'f',          't',          't',              't',               'f',              't',          'f')
            RETURNING id""")
        acl_dm, = c.fetchone()

        # convert per-fingerprint ACLs

        c.execute('ALTER TABLE fingerprint ADD COLUMN acl_id INTEGER REFERENCES acl(id)')
        c.execute("""SELECT id, keyring, source_acl_id, binary_acl_id
                       FROM fingerprint
                      WHERE source_acl_id IS NOT NULL OR binary_acl_id IS NOT NULL""")
        for fingerprint_id, keyring_id, source_acl_id, binary_acl_id in c.fetchall():
            acl_id = get_acl_id(c, acl_dd, acl_dm, keyring_id, source_acl_id, binary_acl_id)
            c.execute('UPDATE fingerprint SET acl_id = %(acl_id)s WHERE id = %(fingerprint_id)s',
                      {'acl_id': acl_id, 'fingerprint_id': fingerprint_id})
        c.execute("""ALTER TABLE fingerprint
                       DROP COLUMN source_acl_id,
                       DROP COLUMN binary_acl_id,
                       DROP COLUMN binary_reject""")

        # convert per-keyring ACLs
        c.execute('ALTER TABLE keyrings ADD COLUMN acl_id INTEGER REFERENCES acl(id)')
        c.execute('SELECT id, default_source_acl_id, default_binary_acl_id FROM keyrings')
        for keyring_id, source_acl_id, binary_acl_id in c.fetchall():
            acl_id = get_acl_id(c, acl_dd, acl_dm, keyring_id, source_acl_id, binary_acl_id)
            c.execute('UPDATE keyrings SET acl_id = %(acl_id)s WHERE id = %(keyring_id)s',
                      {'acl_id': acl_id, 'keyring_id': keyring_id})
        c.execute("""ALTER TABLE keyrings
                       DROP COLUMN default_source_acl_id,
                       DROP COLUMN default_binary_acl_id,
                       DROP COLUMN default_binary_reject""")

        c.execute("DROP TABLE keyring_acl_map")
        c.execute("DROP TABLE binary_acl_map")
        c.execute("DROP TABLE binary_acl")
        c.execute("DROP TABLE source_acl")

        # convert upload blocks
        c.execute("""
            INSERT INTO acl
                   (    name, is_global, allow_new, allow_source, allow_binary, allow_binary_all, allow_hijack, allow_binary_only, deny_per_source)
            VALUES ('blocks',       't',       't',          't',          't',              't',          't',               't',             't')
            RETURNING id""")
        acl_block, = c.fetchone()
        c.execute("SELECT source, fingerprint_id, reason FROM upload_blocks")
        for source, fingerprint_id, reason in c.fetchall():
            if fingerprint_id is None:
                raise Exception(
                    "ERROR: upload blocks based on uid are no longer supported\n"
                    "=========================================================\n"
                    "\n"
                    "dak now only supports upload blocks based on fingerprints. Please remove\n"
                    "any uid-specific block by running\n"
                    "   DELETE FROM upload_blocks WHERE fingerprint_id IS NULL\n"
                    "and try again.")

            c.execute('INSERT INTO acl_match_source_map (acl_id, fingerprint_id, source, reason) VALUES (%(acl_id)s, %(fingerprint_id)s, %(source)s, %(reason)s)',
                      {'acl_id': acl_block, 'fingerprint_id': fingerprint_id, 'source': source, 'reason': reason})
        c.execute("DROP TABLE upload_blocks")

        c.execute("UPDATE config SET value = '83' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 83, rollback issued. Error message: {0}'.format(msg))
