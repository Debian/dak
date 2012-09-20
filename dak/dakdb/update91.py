#!/usr/bin/env python
# coding=utf8

"""
per-queue NEW comments and permissions

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
"""
ALTER TABLE new_comments
ADD COLUMN policy_queue_id INTEGER REFERENCES policy_queue(id)
""",

"""
UPDATE new_comments
SET policy_queue_id = (SELECT id FROM policy_queue WHERE queue_name = 'new')
""",

"""
ALTER TABLE new_comments ALTER COLUMN policy_queue_id SET NOT NULL
""",

"""
CREATE OR REPLACE FUNCTION trigger_check_policy_queue_permission() RETURNS TRIGGER
SET search_path = public, pg_temp
LANGUAGE plpgsql
AS $$
DECLARE
  v_row RECORD;
  v_suite_id suite.id%TYPE;
  v_policy_queue_name policy_queue.queue_name%TYPE;
BEGIN

  CASE TG_OP
    WHEN 'INSERT', 'UPDATE' THEN
      v_row := NEW;
    WHEN 'DELETE' THEN
      v_row := OLD;
    ELSE
      RAISE EXCEPTION 'Unexpected TG_OP (%)', TG_OP;
  END CASE;

  IF TG_OP = 'UPDATE' AND OLD.policy_queue_id != NEW.policy_queue_id THEN
    RAISE EXCEPTION 'Cannot change policy_queue_id';
  END IF;

  SELECT suite_id, queue_name INTO STRICT v_suite_id, v_policy_queue_name
    FROM policy_queue WHERE id = v_row.policy_queue_id;
  IF NOT has_suite_permission(TG_OP, v_suite_id) THEN
    RAISE EXCEPTION 'Not allowed to % in %', TG_OP, v_policy_queue_name;
  END IF;

  RETURN v_row;

END;
$$
""",

"""
CREATE CONSTRAINT TRIGGER trigger_new_comments_permission
  AFTER INSERT OR UPDATE OR DELETE
  ON new_comments
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_check_policy_queue_permission()
""",
]

################################################################################
def do_update(self):
    print __doc__
    try:
        cnf = Config()

        c = self.db.cursor()

        for stmt in statements:
            c.execute(stmt)

        c.execute("UPDATE config SET value = '91' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 91, rollback issued. Error message: {0}'.format(msg))
