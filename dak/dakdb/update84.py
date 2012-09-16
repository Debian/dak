#!/usr/bin/env python
# coding=utf8

"""
add per-suite database permissions

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
CREATE TABLE suite_permission (
  suite_id INT NOT NULL REFERENCES suite(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  PRIMARY KEY (suite_id, role)
)
""",

"""
CREATE OR REPLACE FUNCTION has_suite_permission(action TEXT, suite_id INT)
  RETURNS BOOLEAN
  STABLE
  STRICT
  SET search_path = public, pg_temp
  LANGUAGE plpgsql
AS $$
DECLARE
  v_result BOOLEAN;
BEGIN

  IF pg_has_role('ftpteam', 'USAGE') THEN
    RETURN 't';
  END IF;

  SELECT BOOL_OR(pg_has_role(sp.role, 'USAGE')) INTO v_result
    FROM suite_permission sp
   WHERE sp.suite_id = has_suite_permission.suite_id
   GROUP BY sp.suite_id;

  IF v_result IS NULL THEN
    v_result := 'f';
  END IF;

  RETURN v_result;

END;
$$
""",

"""
CREATE OR REPLACE FUNCTION trigger_check_suite_permission() RETURNS TRIGGER
SET search_path = public, pg_temp
LANGUAGE plpgsql
AS $$
DECLARE
  v_row RECORD;
  v_suite_name suite.suite_name%TYPE;
BEGIN

  CASE TG_OP
    WHEN 'INSERT', 'UPDATE' THEN
      v_row := NEW;
    WHEN 'DELETE' THEN
      v_row := OLD;
    ELSE
      RAISE EXCEPTION 'Unexpected TG_OP (%)', TG_OP;
  END CASE;

  IF TG_OP = 'UPDATE' AND OLD.suite != NEW.suite THEN
    RAISE EXCEPTION 'Cannot change suite';
  END IF;

  IF NOT has_suite_permission(TG_OP, v_row.suite) THEN
    SELECT suite_name INTO STRICT v_suite_name FROM suite WHERE id = v_row.suite;
    RAISE EXCEPTION 'Not allowed to % in %', TG_OP, v_suite_name;
  END IF;

  RETURN v_row;

END;
$$
""",

"""
CREATE CONSTRAINT TRIGGER trigger_override_permission
  AFTER INSERT OR UPDATE OR DELETE
  ON override
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_check_suite_permission()
""",

"""
CREATE CONSTRAINT TRIGGER trigger_src_associations_permission
  AFTER INSERT OR UPDATE OR DELETE
  ON src_associations
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_check_suite_permission()
""",

"""
CREATE CONSTRAINT TRIGGER trigger_bin_associations_permission
  AFTER INSERT OR UPDATE OR DELETE
  ON bin_associations
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_check_suite_permission()
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

        c.execute("UPDATE config SET value = '84' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 84, rollback issued. Error message: {0}'.format(msg))
