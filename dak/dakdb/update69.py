#!/usr/bin/env python
# coding=utf8

"""
Add support for Description-md5

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Ansgar Burchardt <ansgar@debian.org>
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

################################################################################
def do_update(self):
    """
    Add support for Description-md5
    """
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        c.execute("""CREATE OR REPLACE FUNCTION public.add_missing_description_md5()
  RETURNS VOID
  VOLATILE
  LANGUAGE plpgsql
AS $function$
DECLARE
  description_key_id metadata_keys.key_id%TYPE;
  description_md5_key_id metadata_keys.key_id%TYPE;
  BEGIN
    SELECT key_id INTO STRICT description_key_id FROM metadata_keys WHERE key='Description';
    SELECT key_id INTO description_md5_key_id FROM metadata_keys WHERE key='Description-md5';
    IF NOT FOUND THEN
      INSERT INTO metadata_keys (key) VALUES ('Description-md5') RETURNING key_id INTO description_md5_key_id;
    END IF;

    INSERT INTO binaries_metadata
      (bin_id, key_id, value)
    SELECT
      bm.bin_id AS bin_id,
      description_md5_key_id AS key_id,
      MD5(bm.value || E'\n') AS value
    FROM binaries_metadata AS bm
    WHERE
      bm.key_id = description_key_id
      AND
      NOT EXISTS (SELECT 1 FROM binaries_metadata AS bm2 WHERE bm.bin_id = bm2.bin_id AND bm2.key_id = description_md5_key_id);
END;
$function$""")

        c.execute("ALTER TABLE suite ADD COLUMN include_long_description BOOLEAN NOT NULL DEFAULT 't'")

        c.execute("UPDATE config SET value = '69' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 69, rollback issued. Error message : %s' % (str(msg)))
