#!/usr/bin/env python
# coding=utf8

"""
Adding content fields

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008  Michael Casadevall <mcasadevall@debian.org>
@copyright: 2008  Roger Leigh <rleigh@debian.org>
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

# <tomv_w> really, if we want to screw ourselves, let's find a better way.
# <Ganneff> rm -rf /srv/ftp.debian.org

################################################################################

import psycopg2
import time
from daklib.dak_exceptions import DBUpdateError

################################################################################

def do_update(self):
    print "Adding content fields to database"

    try:
        c = self.db.cursor()
        c.execute("""CREATE TABLE content_file_paths (
                     id serial primary key not null,
                     path text unique not null
                   )""")

        c.execute("""CREATE TABLE content_file_names (
                    id serial primary key not null,
                    file text unique not null
                   )""")

        c.execute("""CREATE TABLE content_associations (
                    id serial not null,
                    binary_pkg int4 not null references binaries(id) on delete cascade,
                    filepath int4 not null references content_file_paths(id) on delete cascade,
                    filename int4 not null references content_file_names(id) on delete cascade
                  );""")

        c.execute("""CREATE TABLE pending_content_associations (
                     id serial not null,
                     package text not null,
                     version debversion not null,
                     filepath int4 not null references content_file_paths(id) on delete cascade,
                     filename int4 not null references content_file_names(id) on delete cascade
                   );""")

        c.execute("""CREATE FUNCTION comma_concat(text, text) RETURNS text
                   AS $_$select case
                   WHEN $2 is null or $2 = '' THEN $1
                   WHEN $1 is null or $1 = '' THEN $2
                   ELSE $1 || ',' || $2
                   END$_$
                   LANGUAGE sql""")

        c.execute("""CREATE AGGREGATE comma_separated_list (
                   BASETYPE = text,
                   SFUNC = comma_concat,
                   STYPE = text,
                   INITCOND = ''
                   );""")

        c.execute( "CREATE INDEX content_assocaitions_binary ON content_associations(binary_pkg)" )

        c.execute("UPDATE config SET value = '6' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to appy debversion updates, rollback issued. Error message : %s" % (str(msg)))
