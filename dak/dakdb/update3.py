#!/usr/bin/env python

""" Database Update Script - Remove unused versioncmp """
# Copyright (C) 2008  Michael Casadevall <mcasadevall@debian.org>
# Copyright (C) 2009  Joerg Jaspert <joerg@debian.org>

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

import psycopg2, time

################################################################################

def do_update(self):
    print "Removing no longer used function versioncmp"

    try:
        c = self.db.cursor()
        c.execute("DROP FUNCTION versioncmp(text, text);")
        c.execute("UPDATE config SET value = '3' WHERE name = 'db_revision'")

        self.db.commit()

    except psycopg2.ProgrammingError, msg:
        self.db.rollback()
        print "FATAL: Unable to apply db update 3!"
        print "Error Message: " + str(msg)
        print "Database changes have been rolled back."
