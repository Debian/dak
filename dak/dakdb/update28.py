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
import time
from daklib.dak_exceptions import DBUpdateError
from daklib.config import Config
import string

################################################################################

def _suites():
    """
    return a list of suites to operate on
    """
    suites = Config().subtree("Suite").list()
    return suites

def arches(cursor, suite):
    """
    return a list of archs to operate on
    """
    arch_list = []
    cursor.execute("""SELECT s.architecture, a.arch_string
    FROM suite_architectures s
    JOIN architecture a ON (s.architecture=a.id)
    WHERE suite = '%s'""" % suite)

    while True:
        r = cursor.fetchone()
        if not r:
            break

        if r[1] != "source" and r[1] != "all":
            arch_list.append((r[0], r[1]))

    return arch_list

def do_update(self):
    """
    Adding contents table as first step to maybe, finally getting rid
    of apt-ftparchive
    """

    print __doc__

    try:
        c = self.db.cursor()

        c.execute("""CREATE TABLE pending_bin_contents (
        id serial NOT NULL,
        package text NOT NULL,
        version debversion NOT NULL,
        arch int NOT NULL,
        filename text NOT NULL,
        type int NOT NULL,
        PRIMARY KEY(id))""" );

        c.execute("""CREATE TABLE deb_contents (
        filename text,
        section text,
        package text,
        binary_id integer,
        arch integer,
        suite integer)""" )

        c.execute("""CREATE TABLE udeb_contents (
        filename text,
        section text,
        package text,
        binary_id integer,
        suite integer,
        arch integer)""" )

        c.execute("""ALTER TABLE ONLY deb_contents
        ADD CONSTRAINT deb_contents_arch_fkey
        FOREIGN KEY (arch) REFERENCES architecture(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY udeb_contents
        ADD CONSTRAINT udeb_contents_arch_fkey
        FOREIGN KEY (arch) REFERENCES architecture(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY deb_contents
        ADD CONSTRAINT deb_contents_pkey
        PRIMARY KEY (filename,package,arch,suite);""")

        c.execute("""ALTER TABLE ONLY udeb_contents
        ADD CONSTRAINT udeb_contents_pkey
        PRIMARY KEY (filename,package,arch,suite);""")

        c.execute("""ALTER TABLE ONLY deb_contents
        ADD CONSTRAINT deb_contents_suite_fkey
        FOREIGN KEY (suite) REFERENCES suite(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY udeb_contents
        ADD CONSTRAINT udeb_contents_suite_fkey
        FOREIGN KEY (suite) REFERENCES suite(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY deb_contents
        ADD CONSTRAINT deb_contents_binary_fkey
        FOREIGN KEY (binary_id) REFERENCES binaries(id)
        ON DELETE CASCADE;""")

        c.execute("""ALTER TABLE ONLY udeb_contents
        ADD CONSTRAINT udeb_contents_binary_fkey
        FOREIGN KEY (binary_id) REFERENCES binaries(id)
        ON DELETE CASCADE;""")

        c.execute("""CREATE INDEX ind_deb_contents_binary ON deb_contents(binary_id);""" )

        suites = _suites()

        for suite in [i.lower() for i in suites]:

            c.execute("SELECT id FROM suite WHERE suite_name ='%s'" % suite )
            suiterow = c.fetchone()
            suite_id = suiterow[0]
            arch_list = arches(c, suite_id)
            arch_list = arches(c, suite_id)
            suitestr=string.replace(suite,'-','_');

            for (arch_id,arch_str) in arch_list:
                arch_str = string.replace(arch_str,"-", "_")
                c.execute( "CREATE INDEX ind_deb_contents_%s_%s ON deb_contents (arch,suite) WHERE (arch=2 OR arch=%s) AND suite='%s'"%(arch_str,suitestr,arch_id,suite_id) )

            for section, sname in [("debian-installer","main"),
                                  ("non-free/debian-installer", "nonfree")]:
                c.execute( "CREATE INDEX ind_udeb_contents_%s_%s ON udeb_contents (section,suite) WHERE section='%s' AND suite='%s'"%(sname,suitestr,section,suite_id) )


        c.execute( """CREATE OR REPLACE FUNCTION update_contents_for_bin_a() RETURNS trigger AS  $$
    event = TD["event"]
    if event == "DELETE" or event == "UPDATE":

        plpy.execute(plpy.prepare("DELETE FROM deb_contents WHERE binary_id=$1 and suite=$2",
                                  ["int","int"]),
                                  [TD["old"]["bin"], TD["old"]["suite"]])

    if event == "INSERT" or event == "UPDATE":

       content_data = plpy.execute(plpy.prepare(
            \"\"\"SELECT s.section, b.package, b.architecture, ot.type
            FROM override o
            JOIN override_type ot on o.type=ot.id
            JOIN binaries b on b.package=o.package
            JOIN files f on b.file=f.id
            JOIN location l on l.id=f.location
            JOIN section s on s.id=o.section
            WHERE b.id=$1
            AND o.suite=$2
            \"\"\",
            ["int", "int"]),
            [TD["new"]["bin"], TD["new"]["suite"]])[0]

       tablename="%s_contents" % content_data['type']

       plpy.execute(plpy.prepare(\"\"\"DELETE FROM %s
                   WHERE package=$1 and arch=$2 and suite=$3\"\"\" % tablename,
                   ['text','int','int']),
                   [content_data['package'],
                   content_data['architecture'],
                   TD["new"]["suite"]])

       filenames = plpy.execute(plpy.prepare(
           "SELECT bc.file FROM bin_contents bc where bc.binary_id=$1",
           ["int"]),
           [TD["new"]["bin"]])

       for filename in filenames:
           plpy.execute(plpy.prepare(
               \"\"\"INSERT INTO %s
                   (filename,section,package,binary_id,arch,suite)
                   VALUES($1,$2,$3,$4,$5,$6)\"\"\" % tablename,
               ["text","text","text","int","int","int"]),
               [filename["file"],
                content_data["section"],
                content_data["package"],
                TD["new"]["bin"],
                content_data["architecture"],
                TD["new"]["suite"]] )
$$ LANGUAGE plpythonu VOLATILE SECURITY DEFINER;
""")


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

        c.execute("""CREATE OR REPLACE FUNCTION update_contents_for_override()
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

        c.execute( """CREATE TRIGGER illegal_suite_arch_bin_associations_trigger
                      BEFORE INSERT OR UPDATE ON bin_associations
                      FOR EACH ROW EXECUTE PROCEDURE update_contents_for_override();""")

        c.execute( """CREATE TRIGGER bin_associations_contents_trigger
                      AFTER INSERT OR UPDATE OR DELETE ON bin_associations
                      FOR EACH ROW EXECUTE PROCEDURE update_contents_for_bin_a();""")
        c.execute("""CREATE TRIGGER override_contents_trigger
                      AFTER UPDATE ON override
                      FOR EACH ROW EXECUTE PROCEDURE update_contents_for_override();""")


        c.execute( "CREATE INDEX ind_deb_contents_name ON deb_contents(package);");
        c.execute( "CREATE INDEX ind_udeb_contents_name ON udeb_contents(package);");

        c.execute("UPDATE config SET value = '28' WHERE name = 'db_revision'")

        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply process-new update 28, rollback issued. Error message : %s" % (str(msg)))

