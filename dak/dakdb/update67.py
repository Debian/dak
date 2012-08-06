#!/usr/bin/env python
# coding=utf8

"""
Add audit schema and initial package table and triggers

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Mark Hymers <mhy@debian.org>
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
    Add audit schema and initial package table and triggers
    """
    print __doc__
    try:
        c = self.db.cursor()

        c.execute("CREATE SCHEMA audit");
        c.execute("GRANT USAGE on SCHEMA audit TO public")
        c.execute("GRANT USAGE on SCHEMA audit TO ftpteam")
        c.execute("GRANT USAGE on SCHEMA audit TO ftpmaster")

        c.execute("""CREATE TABLE audit.package_changes (
   changedate TIMESTAMP NOT NULL DEFAULT now(),
   package TEXT NOT NULL,
   version DEBVERSION NOT NULL,
   architecture TEXT NOT NULL,
   suite TEXT NOT NULL,
   event TEXT NOT NULL,
   priority TEXT,
   component TEXT,
   section TEXT
)""")

        c.execute("GRANT INSERT ON audit.package_changes TO dak")
        c.execute("GRANT SELECT ON audit.package_changes TO PUBLIC")

        c.execute("""CREATE OR REPLACE FUNCTION trigger_binsrc_assoc_update() RETURNS TRIGGER AS $$
DECLARE
  v_data RECORD;

  v_package audit.package_changes.package%TYPE;
  v_version audit.package_changes.version%TYPE;
  v_architecture audit.package_changes.architecture%TYPE;
  v_suite audit.package_changes.suite%TYPE;
  v_event audit.package_changes.event%TYPE;
  v_priority audit.package_changes.priority%TYPE;
  v_component audit.package_changes.component%TYPE;
  v_section audit.package_changes.section%TYPE;
BEGIN
  CASE TG_OP
    WHEN 'INSERT' THEN v_event := 'I'; v_data := NEW;
    WHEN 'DELETE' THEN v_event := 'D'; v_data := OLD;
    ELSE RAISE EXCEPTION 'trigger called for invalid operation (%)', TG_OP;
  END CASE;

  SELECT suite_name INTO STRICT v_suite FROM suite WHERE id = v_data.suite;

  CASE TG_TABLE_NAME
    WHEN 'bin_associations' THEN
      SELECT package, version, arch_string
        INTO STRICT v_package, v_version, v_architecture
        FROM binaries LEFT JOIN architecture ON (architecture.id = binaries.architecture)
        WHERE binaries.id = v_data.bin;

      SELECT component.name, priority.priority, section.section
        INTO v_component, v_priority, v_section
        FROM override
             JOIN override_type ON (override.type = override_type.id)
             JOIN priority ON (priority.id = override.priority)
             JOIN section ON (section.id = override.section)
             JOIN component ON (override.component = component.id)
             JOIN suite ON (suite.id = override.suite)
        WHERE override_type.type != 'dsc'
              AND override.package = v_package AND suite.id = v_data.suite;

    WHEN 'src_associations' THEN
      SELECT source, version
        INTO STRICT v_package, v_version
        FROM source WHERE source.id = v_data.source;
      v_architecture := 'source';

      SELECT component.name, priority.priority, section.section
        INTO v_component, v_priority, v_section
        FROM override
             JOIN override_type ON (override.type = override_type.id)
             JOIN priority ON (priority.id = override.priority)
             JOIN section ON (section.id = override.section)
             JOIN component ON (override.component = component.id)
             JOIN suite ON (suite.id = override.suite)
        WHERE override_type.type = 'dsc'
              AND override.package = v_package AND suite.id = v_data.suite;

    ELSE RAISE EXCEPTION 'trigger called for invalid table (%)', TG_TABLE_NAME;
  END CASE;

  INSERT INTO audit.package_changes
    (package, version, architecture, suite, event, priority, component, section)
    VALUES (v_package, v_version, v_architecture, v_suite, v_event, v_priority, v_component, v_section);

  RETURN NEW;
END;
$$ LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public, pg_temp""");

        c.execute("""CREATE OR REPLACE FUNCTION trigger_override_update() RETURNS TRIGGER AS $$
DECLARE
  v_src_override_id override_type.id%TYPE;

  v_priority audit.package_changes.priority%TYPE := NULL;
  v_component audit.package_changes.component%TYPE := NULL;
  v_section audit.package_changes.section%TYPE := NULL;
BEGIN

  IF TG_TABLE_NAME != 'override' THEN
    RAISE EXCEPTION 'trigger called for invalid table (%)', TG_TABLE_NAME;
  END IF;
  IF TG_OP != 'UPDATE' THEN
    RAISE EXCEPTION 'trigger called for invalid event (%)', TG_OP;
  END IF;

  IF OLD.package != NEW.package OR OLD.type != NEW.type OR OLD.suite != NEW.suite THEN
    RETURN NEW;
  END IF;

  IF OLD.priority != NEW.priority THEN
    SELECT priority INTO STRICT v_priority FROM priority WHERE id = NEW.priority;
  END IF;

  IF OLD.component != NEW.component THEN
    SELECT name INTO STRICT v_component FROM component WHERE id = NEW.component;
  END IF;

  IF OLD.section != NEW.section THEN
    SELECT section INTO STRICT v_section FROM section WHERE id = NEW.section;
  END IF;

  -- Find out if we're doing src or binary overrides
  SELECT id INTO STRICT v_src_override_id FROM override_type WHERE type = 'dsc';
  IF OLD.type = v_src_override_id THEN
    -- Doing a src_association link
    INSERT INTO audit.package_changes
      (package, version, architecture, suite, event, priority, component, section)
      SELECT NEW.package, source.version, 'source', suite.suite_name, 'U', v_priority, v_component, v_section
        FROM source
          JOIN src_associations ON (source.id = src_associations.source)
          JOIN suite ON (suite.id = src_associations.suite)
        WHERE source.source = NEW.package AND src_associations.suite = NEW.suite;
  ELSE
    -- Doing a bin_association link
    INSERT INTO audit.package_changes
      (package, version, architecture, suite, event, priority, component, section)
      SELECT NEW.package, binaries.version, architecture.arch_string, suite.suite_name, 'U', v_priority, v_component, v_section
        FROM binaries
          JOIN bin_associations ON (binaries.id = bin_associations.bin)
          JOIN architecture ON (architecture.id = binaries.architecture)
          JOIN suite ON (suite.id = bin_associations.suite)
        WHERE binaries.package = NEW.package AND bin_associations.suite = NEW.suite;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public, pg_temp""");

        c.execute("CREATE TRIGGER trigger_bin_associations_audit AFTER INSERT OR DELETE ON bin_associations FOR EACH ROW EXECUTE PROCEDURE trigger_binsrc_assoc_update()")
        c.execute("CREATE TRIGGER trigger_src_associations_audit AFTER INSERT OR DELETE ON src_associations FOR EACH ROW EXECUTE PROCEDURE trigger_binsrc_assoc_update()")
        c.execute("CREATE TRIGGER trigger_override_audit AFTER UPDATE ON override FOR EACH ROW EXECUTE PROCEDURE trigger_override_update()")

        c.execute("UPDATE config SET value = '67' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        raise DBUpdateError('Unable to apply sick update 67, rollback issued. Error message : %s' % (str(msg)))
