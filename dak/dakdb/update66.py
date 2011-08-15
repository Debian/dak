#!/usr/bin/env python
# coding=utf8

"""
Add audit schema and initial package table and triggers

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011 Mark Hymers <mhy@debian.org>
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
tablename = TD["table_name"]
event = TD["event"]

# We only handle bin/src_associations in this trigger
if tablename not in ['bin_associations', 'src_associations']:
    return None

if event == 'INSERT':
    dat = TD['new']
    pkg_event = 'I'
elif event == 'DELETE':
    dat = TD['old']
    pkg_event = 'D'
else:
    # We don't handle other changes on these tables
    return None

# Find suite information
suite_info = plpy.execute(plpy.prepare("SELECT suite_name FROM suite WHERE id = $1", ["int"]), [dat["suite"]])
# Couldn't find suite
if len(suite_info) != 1:
    plpy.warning('Could not find suite for id %s' % dat['suite'])
    return None
suite_name = suite_info[0]['suite_name']

# Some defaults in case we can't find the overrides
component = None
section = None
priority = None

if tablename == 'bin_associations':
    pkg_info = plpy.execute(plpy.prepare("SELECT package, version, arch_string FROM binaries LEFT JOIN architecture ON (architecture.id = binaries.architecture) WHERE binaries.id = $1", ["int"]), [dat["bin"]])

    # Couldn't find binary: shouldn't happen, but be careful
    if len(pkg_info) != 1:
        plpy.warning('Could not find binary for id %s' % dat["bin"])
        return None

    package = pkg_info[0]['package']
    version = pkg_info[0]['version']
    arch = pkg_info[0]['arch_string']

    bin_override_q = '''SELECT component.name AS component,
                             priority.priority AS priority,
                             section.section AS section,
                             override_type.type
                        FROM override
                   LEFT JOIN override_type ON (override.type = override_type.id)
                   LEFT JOIN priority ON (priority.id = override.priority)
                   LEFT JOIN section ON (section.id = override.section)
                   LEFT JOIN component ON (override.component = component.id)
                   LEFT JOIN suite ON (suite.id = override.suite)
                       WHERE override_type.type != 'dsc'
                         AND package = $1
                         AND suite.id = $2'''

    bin_overrides = plpy.execute(plpy.prepare(bin_override_q, ["text", "int"]), [package, dat["suite"]])
    # Only fill in the values if we find the unique override
    if len(bin_overrides) == 1:
        component = bin_overrides[0]['component']
        priority = bin_overrides[0]['priority']
        section = bin_overrides[0]['section']

elif tablename == 'src_associations':
    pkg_info = plpy.execute(plpy.prepare("SELECT source, version FROM source WHERE source.id = $1", ["int"]), [dat["source"]])

    # Couldn't find source: shouldn't happen, but be careful
    if len(pkg_info) != 1:
        plpy.warning('Could not find source for id %s' % dat["source"])
        return None

    package = pkg_info[0]['source']
    version = pkg_info[0]['version']
    arch = 'source'

    src_override_q = '''SELECT component.name AS component,
                             priority.priority AS priority,
                             section.section AS section,
                             override_type.type
                        FROM override
                   LEFT JOIN override_type ON (override.type = override_type.id)
                   LEFT JOIN priority ON (priority.id = override.priority)
                   LEFT JOIN section ON (section.id = override.section)
                   LEFT JOIN component ON (override.component = component.id)
                   LEFT JOIN suite ON (suite.id = override.suite)
                       WHERE override_type.type = 'dsc'
                         AND package = $1
                         AND suite.id = $2'''

    src_overrides = plpy.execute(plpy.prepare(src_override_q, ["text", "int"]), [package, dat["suite"]])
    # Only fill in the values if we find the unique override
    if len(src_overrides) == 1:
        component = src_overrides[0]['component']
        priority = src_overrides[0]['priority']
        section = src_overrides[0]['section']

# Insert the audit row
plpy.execute(plpy.prepare("INSERT INTO audit.package_changes (package, version, architecture, suite, event, priority, component, section) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
             ["text", "text", "text", "text", "text", "text", "text", "text"]),
             [package, version, arch, suite_name, pkg_event, priority, component, section])

$$ LANGUAGE plpythonu VOLATILE SECURITY DEFINER""")

        c.execute("""CREATE OR REPLACE FUNCTION trigger_override_update() RETURNS TRIGGER AS $$
tablename = TD["table_name"]
event = TD["event"]

if tablename != 'override':
    return None

if event != 'UPDATE':
    # We only care about UPDATE event here
    return None

# Deal with some pathologically stupid cases we ignore
if (TD['new']['package'] != TD['old']['package']) or \
   (TD['new']['type'] != TD['old']['type']) or \
   (TD['new']['suite'] != TD['old']['suite']):
    return None

package = TD['old']['package']

# Get the priority, component and section out
if TD['new']['priority'] == TD['old']['priority']:
    priority = None
else:
    priority_row = plpy.execute(plpy.prepare("SELECT priority FROM priority WHERE id = $1", ["int"]), [TD['new']['priority']])
    if len(priority_row) != 1:
        plpy.warning('Could not find priority for id %s' % TD['new']['priority'])
        return None
    priority = priority_row[0]['priority']

if TD['new']['component'] == TD['old']['component']:
    component = None
else:
    component_row = plpy.execute(plpy.prepare("SELECT name AS component FROM component WHERE id = $1", ["int"]), [TD['new']['component']])
    if len(component_row) != 1:
        plpy.warning('Could not find component for id %s' % TD['new']['component'])
        return None
    component = component_row[0]['component']

if TD['new']['section'] == TD['old']['section']:
    section = None
else:
    section_row = plpy.execute(plpy.prepare("SELECT section FROM section WHERE id = $1", ["int"]), [TD['new']['section']])
    if len(section_row) != 1:
        plpy.warning('Could not find section for id %s' % TD['new']['section'])
        return None
    section = section_row[0]['section']

# Find out if we're doing src or binary overrides
src_override_types = plpy.execute(plpy.prepare("SELECT id FROM override_type WHERE type = 'dsc'"), [])
if len(src_override_types) != 1:
    return None
src_override_id = src_override_types[0]['id']

if TD['old']['type'] == src_override_id:
    # Doing a src_association link
    ## Find all of the relevant suites to work on
    for suite_row in plpy.execute(plpy.prepare('''SELECT source.version, suite_name
                                            FROM source
                                       LEFT JOIN src_associations ON (source.id = src_associations.source)
                                       LEFT JOIN suite ON (suite.id = src_associations.suite)
                                       WHERE source.source = $1
                                       AND suite = $2''', ["text", "int"]), [package, TD['new']['suite']]):
        # INSERT one row per affected source package
        plpy.execute(plpy.prepare("INSERT INTO audit.package_changes (package, version, architecture, suite, event, priority, component, section) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
             ["text", "text", "text", "text", "text", "text", "text", "text"]),
             [package, suite_row['version'], 'source', suite_row['suite_name'],
              'U', priority, component, section])
else:
    # Doing a bin_association link; Find all of the relevant suites to work on
    for suite_row in plpy.execute(plpy.prepare('''SELECT binaries.version, arch_string, suite_name
                                            FROM binaries
                                       LEFT JOIN bin_associations ON (binaries.id = bin_associations.bin)
                                       LEFT JOIN architecture ON (architecture.id = binaries.architecture)
                                       LEFT JOIN suite ON (suite.id = bin_associations.suite)
                                       WHERE package = $1
                                       AND suite = $2''', ["text", "int"]), [package, TD['new']['suite']]):
        # INSERT one row per affected binary
        plpy.execute(plpy.prepare("INSERT INTO audit.package_changes (package, version, architecture, suite, event, priority, component, section) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
             ["text", "text", "text", "text", "text", "text", "text", "text"]),
             [package, suite_row['version'], suite_row['arch_string'], suite_row['suite_name'],
              'U', priority, component, section])

$$ LANGUAGE plpythonu VOLATILE SECURITY DEFINER;
""")

        c.execute("CREATE TRIGGER trigger_bin_associations_audit AFTER INSERT OR DELETE ON bin_associations FOR EACH ROW EXECUTE PROCEDURE trigger_binsrc_assoc_update()")
        c.execute("CREATE TRIGGER trigger_src_associations_audit AFTER INSERT OR DELETE ON src_associations FOR EACH ROW EXECUTE PROCEDURE trigger_binsrc_assoc_update()")
        c.execute("CREATE TRIGGER trigger_override_audit AFTER UPDATE ON override FOR EACH ROW EXECUTE PROCEDURE trigger_override_update()")

        c.execute("UPDATE config SET value = '66' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        raise DBUpdateError, 'Unable to apply sick update 66, rollback issued. Error message : %s' % (str(msg))
