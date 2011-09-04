#!/usr/bin/env python
# coding=utf8

"""
keep contents of binary packages in tables so we can generate contents.gz files from dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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
from daklib.dak_exceptions import DBUpdateError

################################################################################
def do_update(self):
    """
    add trigger to verify that bin_associations aren't added for an
    illegal suite,arch combination.  Fix override trigger, re-add all
    3 triggers
    """
    print __doc__
    try:
        c = self.db.cursor()

        c.execute("""CREATE OR REPLACE FUNCTION check_illegal_suite_arch()
                      RETURNS trigger AS  $$
    event = TD["event"]
    if event == "UPDATE" or event == "INSERT":
        row = TD["new"]
        r = plpy.execute(plpy.prepare( \"\"\"SELECT 1 from suite_architectures sa
                  JOIN binaries b ON b.architecture = sa.architecture
                  WHERE b.id = $1 and sa.suite = $2\"\"\",
                ["int", "int"]),
                [row["bin"], row["suite"]])
        if not len(r):
            plpy.error("Illegal architecture for this suite")

$$ LANGUAGE plpythonu VOLATILE;""")

        c.execute( """CREATE OR REPLACE FUNCTION update_contents_for_override() RETURNS trigger AS  $$
    event = TD["event"]
    if event == "UPDATE":

        otype = plpy.execute(plpy.prepare("SELECT type from override_type where id=$1",["int"]),[TD["new"]["type"]] )[0];
        if otype["type"].endswith("deb"):
            section = plpy.execute(plpy.prepare("SELECT section from section where id=$1",["int"]),[TD["new"]["section"]] )[0];

            table_name = "%s_contents" % otype["type"]
            plpy.execute(plpy.prepare("UPDATE %s set section=$1 where package=$2 and suite=$3" % table_name,
                                      ["text","text","int"]),
                                      [section["section"],
                                      TD["new"]["package"],
                                      TD["new"]["suite"]])

$$ LANGUAGE plpythonu VOLATILE SECURITY DEFINER;
""")
        c.execute( "DROP TRIGGER IF EXISTS illegal_suite_arch_bin_associations_trigger on bin_associations;" )

        c.execute( "DROP TRIGGER IF EXISTS bin_associations_contents_trigger ON bin_associations;" )
        c.execute( "DROP TRIGGER IF EXISTS override_contents_trigger ON override;" )

        c.execute( """CREATE TRIGGER bin_associations_contents_trigger
                      AFTER INSERT OR UPDATE OR DELETE ON bin_associations
                      FOR EACH ROW EXECUTE PROCEDURE update_contents_for_bin_a();""")

        c.execute("""CREATE TRIGGER override_contents_trigger
                      AFTER UPDATE ON override
                      FOR EACH ROW EXECUTE PROCEDURE update_contents_for_override();""")

        c.execute( """CREATE TRIGGER illegal_suite_arch_bin_associations_trigger
                      BEFORE INSERT OR UPDATE ON bin_associations
                      FOR EACH ROW EXECUTE PROCEDURE check_illegal_suite_arch();""")

        c.execute("UPDATE config SET value = '31' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply process-new update 31, rollback issued. Error message : %s" % (str(msg)))

