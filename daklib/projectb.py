#!/usr/bin/python

"""
Class providing access to a projectb database

This class provides convenience functions for common queries to a
projectb database using psycopg2.

Copyright (C) 2009  Mike O'Connor <stew@vireo.org>
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

################################################################################

class Projectb(object):
    """
    Object providing methods for accessing the projectb database
    """
    def __init__(self,Cnf):
        connect_str = "dbname=%s"% (Cnf["DB::Name"])
        if Cnf["DB::Host"] != '': connect_str += " host=%s" % (Cnf["DB::Host"])
        if Cnf["DB::Port"] != '-1': connect_str += " port=%d" % (int(Cnf["DB::Port"]))

        self.dbh = psycopg2.connect(connect_str)
        self.suite_id_cache = {}
        self.architecture_id_cache = {}
        self.section_id_cache = {}

    def get_suite_id(self, suite_name):
        """
        return the id for the given suite_name

        @param suite_name: name of a suite such as "unsatble" or "testing"

        @rtype: int
        @return: id of given suite or None if suite_name not matched

        >>> Cnf = {'DB::Name' : "projectb","DB::Host":"","DB::Port":'-1' }
        >>> pb = Projectb( Cnf )
        >>> pb.get_suite_id("unstable")
        5
        >>> pb.get_suite_id("n'existe pas")
        """
        if not self.suite_id_cache.has_key(suite_name):
            c = self.dbh.cursor()
            c.execute("SELECT id FROM suite WHERE suite_name=%(suite_name)s",
                      {'suite_name':suite_name})
            r = c.fetchone()
            if r:
                self.suite_id_cache[suite_name] = r[0]
            else:
                self.suite_id_cache[suite_name] = None

        return self.suite_id_cache[suite_name]

    def get_architecture_id(self, architecture_name):
        """
        return the id for the given architecture_name

        @param architecture_name: name of a architecture such as "i386" or "source"

        @rtype: int
        @return: id of given architecture or None if architecture_name not matched

        >>> Cnf = {'DB::Name' : "projectb","DB::Host":"","DB::Port":'-1' }
        >>> pb = Projectb( Cnf )
        >>> pb.get_architecture_id("i386")
        7
        >>> pb.get_architecture_id("n'existe pas")
        """
        if not self.architecture_id_cache.has_key(architecture_name):
            c = self.dbh.cursor()
            c.execute("SELECT id FROM architecture WHERE arch_string=%(architecture_name)s",
                      {'architecture_name':architecture_name})
            r = c.fetchone()
            if r:
                self.architecture_id_cache[architecture_name] = r[0]
            else:
                self.architecture_id_cache[architecture_name] = None

        return self.architecture_id_cache[architecture_name]

    def get_section_id(self, section_name):
        """
        return the id for the given section_name

        @param section_name: name of a section such as "x11" or "non-free/libs"

        @rtype: int
        @return: id of given section or None if section_name not matched

        >>> Cnf = {'DB::Name' : "projectb","DB::Host":"","DB::Port":'-1' }
        >>> pb = Projectb( Cnf )
        >>> pb.get_section_id("non-free/libs")
        285
        >>> pb.get_section_id("n'existe pas")
        """
        if not self.section_id_cache.has_key(section_name):
            c = self.dbh.cursor()
            c.execute("SELECT id FROM section WHERE section=%(section_name)s",
                      {'section_name':section_name})
            r = c.fetchone()
            if r:
                self.section_id_cache[section_name] = r[0]
            else:
                self.section_id_cache[section_name] = None

        return self.section_id_cache[section_name]

if __name__ == "__main__":
    import doctest
    doctest.testmod()
