#!/usr/bin/env python
# coding=utf8

"""
Adding table for allowed source formats

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Raphael Hertzog <hertzog@debian.org>
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
    print "Adding tables listing allowed source formats"

    try:
        c = self.db.cursor()
        c.execute("""
            CREATE TABLE src_format (
                    id SERIAL PRIMARY KEY,
                    format_name TEXT NOT NULL,
                    UNIQUE (format_name)
            )
        """)
        c.execute("INSERT INTO src_format (format_name) VALUES('1.0')")
        c.execute("INSERT INTO src_format (format_name) VALUES('3.0 (quilt)')")
        c.execute("INSERT INTO src_format (format_name) VALUES('3.0 (native)')")

        c.execute("""
            CREATE TABLE suite_src_formats (
                    suite INT4 NOT NULL REFERENCES suite(id),
                    src_format INT4 NOT NULL REFERENCES src_format(id),
                    PRIMARY KEY (suite, src_format)
            )
        """)

        print "Authorize format 1.0 on all suites by default"
        c.execute("SELECT id FROM suite")
        suites = c.fetchall()
        c.execute("SELECT id FROM src_format WHERE format_name = '1.0'")
        formats = c.fetchall()
        for s in suites:
            for f in formats:
                c.execute("INSERT INTO suite_src_formats (suite, src_format) VALUES(%s, %s)", (s[0], f[0]))

        print "Authorize all other formats on tpu, unstable & experimental by default"
        c.execute("SELECT id FROM suite WHERE suite_name IN ('testing-proposed-updates', 'unstable', 'experimental')")
        suites = c.fetchall()
        c.execute("SELECT id FROM src_format WHERE format_name != '1.0'")
        formats = c.fetchall()
        for s in suites:
            for f in formats:
                c.execute("INSERT INTO suite_src_formats (suite, src_format) VALUES(%s, %s)", (s[0], f[0]))

        c.execute("UPDATE config SET value = '15' WHERE name = 'db_revision'")
        self.db.commit()

    except psycopg2.ProgrammingError as msg:
        self.db.rollback()
        raise DBUpdateError("Unable to apply source format update 15, rollback issued. Error message : %s" % (str(msg)))
