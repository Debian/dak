"""
Add support for by-hash with a new table and per-suite boolean

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2016, Julien Cristau <jcristau@debian.org>
@license: GNU General Public License version 2 or later
"""

import psycopg2
from daklib.dak_exceptions import DBUpdateError


def do_update(self):
    """Add column to store whether to generate by-hash things per suite,
    add table to store when by-hash files stopped being referenced
    """
    print(__doc__)
    try:
        c = self.db.cursor()

        c.execute("ALTER TABLE suite ADD COLUMN byhash BOOLEAN DEFAULT false")

        c.execute("""
            CREATE TABLE hashfile (
                suite_id INTEGER NOT NULL REFERENCES suite(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                unreferenced TIMESTAMP,
                PRIMARY KEY (suite_id, path)
            )
             """)

        c.execute("UPDATE config SET value = '116' WHERE name = 'db_revision'")

        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 116, rollback issued. Error message : %s' % (str(msg)))
