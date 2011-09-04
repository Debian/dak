#!/usr/bin/env python
# coding=utf8

"""
Add missing checksums to source_metadata

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
    Add missing checksums to source_metadata
    """
    print __doc__
    try:
        c = self.db.cursor()
        c.execute(R"""CREATE OR REPLACE FUNCTION metadata_keys_get(key_ text)
  RETURNS integer
  LANGUAGE plpgsql
  STRICT
AS $function$
DECLARE
  v_key_id metadata_keys.key_id%TYPE;
BEGIN
  SELECT key_id INTO v_key_id FROM metadata_keys WHERE key = key_;
  IF NOT FOUND THEN
    INSERT INTO metadata_keys (key) VALUES (key_) RETURNING key_id INTO v_key_id;
  END IF;
  RETURN v_key_id;
END;
$function$
""")

        c.execute("""COMMENT ON FUNCTION metadata_keys_get(text)
IS 'return key_id for the given key. If key is not present, create a new entry.'
""")

        c.execute(R"""CREATE OR REPLACE FUNCTION source_metadata_add_missing_checksum(type text)
  RETURNS INTEGER
  LANGUAGE plpgsql
  STRICT
AS $function$
DECLARE
  v_checksum_key metadata_keys.key_id%TYPE;
  rows INTEGER;
BEGIN
  IF type NOT IN ('Files', 'Checksums-Sha1', 'Checksums-Sha256') THEN
    RAISE EXCEPTION 'Unknown checksum field %', type;
  END IF;
  v_checksum_key := metadata_keys_get(type);

  INSERT INTO source_metadata
    (src_id, key_id, value)
  SELECT
    s.id,
    v_checksum_key,
    E'\n' ||
      (SELECT STRING_AGG(' ' || tmp.checksum || ' ' || tmp.size || ' ' || tmp.basename, E'\n' ORDER BY tmp.basename)
       FROM
         (SELECT
              CASE type
                WHEN 'Files' THEN f.md5sum
                WHEN 'Checksums-Sha1' THEN f.sha1sum
                WHEN 'Checksums-Sha256' THEN f.sha256sum
              END AS checksum,
              f.size,
              SUBSTRING(f.filename FROM E'/([^/]*)\\Z') AS basename
            FROM files f JOIN dsc_files ON f.id = dsc_files.file
            WHERE dsc_files.source = s.id AND f.id != s.file
         ) AS tmp
      )

    FROM
      source s
    WHERE NOT EXISTS (SELECT 1 FROM source_metadata md WHERE md.src_id=s.id AND md.key_id = v_checksum_key);

  GET DIAGNOSTICS rows = ROW_COUNT;
  RETURN rows;
END;
$function$
""")

        c.execute("""COMMENT ON FUNCTION source_metadata_add_missing_checksum(TEXT)
IS 'add missing checksum fields to source_metadata. type can be Files (md5sum), Checksums-Sha1, Checksums-Sha256'
""")

        c.execute("UPDATE config SET value = '71' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 71, rollback issued. Error message : %s' % (str(msg)))
