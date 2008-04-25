#!/usr/bin/env python

# Adds yet unknown changedby fields when this column is added to an existing
# database. If everything goes well, it needs to be run only once. Data is
# extracted from Filippo Giunchedi's upload-history project, get the file at
# merkel:/home/filippo/upload-history/*.db.

# Copyright (C) 2008  Christoph Berg <myon@debian.org>

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

###############################################################################

#    /Everybody stand back/
#
#    I know regular expressions

###############################################################################

import errno, fcntl, os, sys, time, re
import apt_pkg
import daklib.database
import daklib.queue
import daklib.utils
from pysqlite2 import dbapi2 as sqlite

projectB = None
DBNAME = "uploads-ddc.db"
sqliteConn = None

###############################################################################

def insert ():
    print "Adding missing changedby fields."

    projectB.query("BEGIN WORK")

    q = projectB.query("SELECT id, source, version FROM source WHERE changedby IS NULL")

    for i in q.getresult():
        print i[1] + "/" + i[2] + ":",

        cur = sqliteConn.cursor()
        cur.execute("SELECT changedby FROM uploads WHERE package = '%s' AND version = '%s' LIMIT 1" % (i[1], i[2]))
        res = cur.fetchall()
        if len(res) != 1:
            print "nothing found"
            continue

        changedby = res[0][0].replace("'", "\\'")
        changedby_id = daklib.database.get_or_set_maintainer_id(changedby)

        projectB.query("UPDATE source SET changedby = %d WHERE id = %d" % (changedby_id, i[0]))
        print changedby, "(%d)" % changedby_id

    projectB.query("COMMIT WORK")

###############################################################################

def main():
    global projectB, sqliteConn

    Cnf = daklib.utils.get_conf()
    Upload = daklib.queue.Upload(Cnf)
    projectB = Upload.projectB

    sqliteConn = sqlite.connect(DBNAME)

    insert()

###############################################################################

if __name__ == '__main__':
    main()
