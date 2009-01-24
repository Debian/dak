#!/usr/bin/env python

# DB access class
# Copyright (C) 2008  Mark Hymers <mhy@debian.org>

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

# < mhy> I need a funny comment
# < sgran> two peanuts were walking down a dark street
# < sgran> one was a-salted
#  * mhy looks up the definition of "funny"

################################################################################

import psycopg2
from psycopg2.extras import DictCursor

from Singleton import Singleton
from Config import Config

################################################################################

class Cache(object):
    def __init__(self, hashfunc=None):
        if hashfunc:
            self.hashfunc = hashfunc
        else:
            self.hashfunc = lambda x: x['value']

        self.data = {}

    def SetValue(self, keys, value):
        self.data[self.hashfunc(keys)] = value

    def GetValue(self, keys):
        return self.data.get(self.hashfunc(keys))

################################################################################

class DBConn(Singleton):
    """
    A DBConn object is a singleton containing
    information about the connection to the SQL Database
    """
    def __init__(self, *args, **kwargs):
        super(DBConn, self).__init__(*args, **kwargs)

    def _startup(self, *args, **kwargs):
        self.__createconn()
        self.__init_caches()

    ## Connection functions
    def __createconn(self):
        connstr = Config().GetDBConnString()
        self.db_con = psycopg2.connect(connstr)

    def reconnect(self):
        try:
            self.db_con.close()
        except psycopg2.InterfaceError:
            pass

        self.db_con = None
        self.__createconn()

    ## Cache functions
    def __init_caches(self):
        self.caches = {'suite':         Cache(), 
                       'section':       Cache(),
                       'priority':      Cache(),
                       'override_type': Cache(),
                       'architecture':  Cache(),
                       'archive':       Cache(),
                       'component':     Cache(),
                       'location':      Cache(lambda x: '%s_%s_%s' % (x['location'], x['component'], x['location'])),
                       'maintainer':    {}, # TODO
                       'keyring':       {}, # TODO
                       'source':        Cache(lambda x: '%s_%s_' % (x['source'], x['version'])),
                       'files':         {}, # TODO
                       'maintainer':    {}, # TODO
                       'fingerprint':   {}, # TODO
                       'queue':         {}, # TODO
                       'uid':           {}, # TODO
                       'suite_version': Cache(lambda x: '%s_%s' % (x['source'], x['suite'])),
                      }

    def clear_caches(self):
        self.__init_caches()

    ## Functions to pass through to the database connector
    def cursor(self):
        return self.db_con.cursor()

    def commit(self):
        return self.db_con.commit()

    ## Get functions
    def __get_single_id(self, query, values, cachename=None):
        # This is a bit of a hack but it's an internal function only
        if cachename is not None:
            res = self.caches[cachename].GetValue(values)
            if res:
                return res

        c = self.db_con.cursor()
        c.execute(query, values)

        if c.rowcount != 1:
            return None

        res = c.fetchone()[0]

        if cachename is not None:
            self.caches[cachename].SetValue(values, res)
            
        return res
   
    def __get_id(self, retfield, table, qfield, value):
        query = "SELECT %s FROM %s WHERE %s = %%(value)s" % (retfield, table, qfield)
        return self.__get_single_id(query, {'value': value}, cachename=table)

    def get_suite_id(self, suite):
        return self.__get_id('id', 'suite', 'suite_name', suite)

    def get_section_id(self, section):
        return self.__get_id('id', 'section', 'section', section)

    def get_priority_id(self, priority):
        return self.__get_id('id', 'priority', 'priority', priority)

    def get_override_type_id(self, override_type):
        return self.__get_id('id', 'override_type', 'override_type', override_type)

    def get_architecture_id(self, architecture):
        return self.__get_id('id', 'architecture', 'arch_string', architecture)

    def get_archive_id(self, archive):
        return self.__get_id('id', 'archive', 'lower(name)', archive)

    def get_component_id(self, component):
        return self.__get_id('id', 'component', 'lower(name)', component)

    def get_location_id(self, location, component, archive):
        archive_id = self.get_archive_id(archive)

        if not archive_id:
            return None

        res = None

        if component:
            component_id = self.get_component_id(component)
            if component_id:
                res = self.__get_single_id("SELECT id FROM location WHERE path=%(location)s AND component=%(component)d AND archive=%(archive)d",
                        {'location': location, 'archive': archive_id, 'component': component_id}, cachename='location')
        else:
            res = self.__get_single_id("SELECT id FROM location WHERE path=%(location)s AND archive=%(archive)d",
                    {'location': location, 'archive': archive_id, 'component': ''}, cachename='location')

        return res

    def get_source_id(self, source, version):
        return self.__get_single_id("SELECT id FROM source s WHERE s.source=%(source)s AND s.version=%(version)s",
                                 {'source': source, 'version': version}, cachename='source')

    def get_suite_version(self, source, suite):
        return self.__get_single_id("""
        SELECT s.version FROM source s, suite su, src_associations sa
        WHERE sa.source=s.id
          AND sa.suite=su.id
          AND su.suite_name=%(suite)s
          AND s.source=%(source)""", {'suite': suite, 'source': source}, cachename='suite_version')

