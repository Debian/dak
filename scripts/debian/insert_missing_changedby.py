#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Adds yet unknown changedby fields when this column is added to an existing
# database. If everything goes well, it needs to be run only once. Data is
# extracted from Filippo Giunchedi's upload-history project, get the file at
# merkel:/home/filippo/upload-history/*.db.

# Copyright (C) 2008  Christoph Berg <myon@debian.org>
# Copyright (C) 2008  Bernd Zeimetz <bzed@debian.org>


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
import pysqlite2.dbapi2
import psycopg2

projectB = None
projectBdb = None
DBNAME = "uploads-queue.db"
sqliteConn = None
maintainer_id_cache={}

###############################################################################

def get_or_set_maintainer_id (maintainer):
    global maintainer_id_cache

    if maintainer_id_cache.has_key(maintainer):
        return maintainer_id_cache[maintainer]

    if isinstance(maintainer, basestring):
        if not isinstance(maintainer, unicode):
            try:
                maintainer = unicode(maintainer, 'utf-8')
            except:
                maintainer = unicode(maintainer, 'iso8859-15')
    maintainer = maintainer.encode('utf-8')

    print "%s" % maintainer
    cursor = projectBdb.cursor()
    cursor.execute("SELECT id FROM maintainer WHERE name=%s", (maintainer, ))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO maintainer (name) VALUES (%s)" , (maintainer, ))
        cursor.execute("SELECT id FROM maintainer WHERE name=%s", (maintainer, ))
        row = cursor.fetchone()
    maintainer_id = row[0]
    maintainer_id_cache[maintainer] = maintainer_id
    cursor.close()

    return maintainer_id


def __get_changedby__(package, version):
    cur = sqliteConn.cursor()
    cur.execute("SELECT changedby FROM uploads WHERE package=? AND version=? LIMIT 1", (package, version))
    res = cur.fetchone()
    cur.close()
    return res

def insert ():
    print "Adding missing changedby fields."

    listcursor = projectBdb.cursor()
    listcursor.execute("SELECT id, source, version FROM source WHERE changedby IS NULL")
    row = listcursor.fetchone()

    while row:
        print repr(row)
        try:
            res = __get_changedby__(row[1], row[2])
        except:
            sqliteConn.text_factory = str
            try:
                res = __get_changedby__(row[1], row[2])
            except:
                print 'FAILED SQLITE'
                res=None
            sqliteConn.text_factory = unicode
        if res:
            changedby_id = get_or_set_maintainer_id(res[0])

            cur = projectBdb.cursor()
            cur.execute("UPDATE source SET changedby=%s WHERE id=%s" % (changedby_id, row[0]))
            cur.close()
            print changedby_id, "(%d)" % row[0]

        else:
            print "nothing found"

        row = listcursor.fetchone()
    listcursor.close()

###############################################################################


def main():
    global projectB, sqliteConn, projectBdb

    Cnf = daklib.utils.get_conf()
    Upload = daklib.queue.Upload(Cnf)
    projectB = Upload.projectB
    projectBdb = psycopg2.connect("dbname=%s" % Cnf["DB::Name"])

    sqliteConn = sqlite.connect(DBNAME)

    insert()

    projectBdb.commit()
    projectBdb.close()

###############################################################################

if __name__ == '__main__':
    main()
