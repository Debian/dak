#!/usr/bin/env python
# coding=utf8

"""
Adding content fields

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2010  Mike O'Connor <stew@debian.org>
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

################################################################################

def do_update(self):
    print "fix trigger for bin_contents so that it ignores non deb,udeb"

    try:
        c = self.db.cursor()
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
            AND ot.type in ('deb','udeb')
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

        c.execute("UPDATE config SET value = '30' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to appy debversion updates, rollback issued. Error message : %s" % (str(msg)))
