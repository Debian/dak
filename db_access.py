# DB access fucntions
# Copyright (C) 2000, 2001  James Troup <james@nocrew.org>
# $Id: db_access.py,v 1.10 2001-11-24 18:42:05 troup Exp $

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

import pg, string

############################################################################################

Cnf = None;
projectB = None;
suite_id_cache = {};
section_id_cache = {};
priority_id_cache = {};
override_type_id_cache = {};
architecture_id_cache = {};
archive_id_cache = {};
component_id_cache = {};
location_id_cache = {};
maintainer_id_cache = {};
source_id_cache = {};
files_id_cache = {};
maintainer_cache = {}

############################################################################################

def init (config, sql):
    global Cnf, projectB

    Cnf = config;
    projectB = sql;

############################################################################################

def get_suite_id (suite):
    global suite_id_cache

    if suite_id_cache.has_key(suite):
        return suite_id_cache[suite]

    q = projectB.query("SELECT id FROM suite WHERE suite_name = '%s'" % (suite))
    ql = q.getresult();
    if not ql:
        return -1;

    suite_id = ql[0][0];
    suite_id_cache[suite] = suite_id

    return suite_id

def get_section_id (section):
    global section_id_cache

    if section_id_cache.has_key(section):
        return section_id_cache[section]

    q = projectB.query("SELECT id FROM section WHERE section = '%s'" % (section))
    ql = q.getresult();
    if not ql:
        return -1;

    section_id = ql[0][0];
    section_id_cache[section] = section_id

    return section_id

def get_priority_id (priority):
    global priority_id_cache

    if priority_id_cache.has_key(priority):
        return priority_id_cache[priority]

    q = projectB.query("SELECT id FROM priority WHERE priority = '%s'" % (priority))
    ql = q.getresult();
    if not ql:
        return -1;

    priority_id = ql[0][0];
    priority_id_cache[priority] = priority_id

    return priority_id

def get_override_type_id (type):
    global override_type_id_cache;

    if override_type_id_cache.has_key(type):
        return override_type_id_cache[type];

    q = projectB.query("SELECT id FROM override_type WHERE type = '%s'" % (type));
    ql = q.getresult();
    if not ql:
        return -1;

    override_type_id = ql[0][0];
    override_type_id_cache[type] = override_type_id;

    return override_type_id;

def get_architecture_id (architecture):
    global architecture_id_cache;

    if architecture_id_cache.has_key(architecture):
        return architecture_id_cache[architecture];

    q = projectB.query("SELECT id FROM architecture WHERE arch_string = '%s'" % (architecture))
    ql = q.getresult();
    if not ql:
        return -1;

    architecture_id = ql[0][0];
    architecture_id_cache[architecture] = architecture_id;

    return architecture_id;

def get_archive_id (archive):
    global archive_id_cache

    archive = string.lower(archive);

    if archive_id_cache.has_key(archive):
        return archive_id_cache[archive]

    q = projectB.query("SELECT id FROM archive WHERE lower(name) = '%s'" % (archive));
    ql = q.getresult();
    if not ql:
        return -1;

    archive_id = ql[0][0]
    archive_id_cache[archive] = archive_id

    return archive_id

def get_component_id (component):
    global component_id_cache

    component = string.lower(component);

    if component_id_cache.has_key(component):
        return component_id_cache[component]

    q = projectB.query("SELECT id FROM component WHERE lower(name) = '%s'" % (component))
    ql = q.getresult();
    if not ql:
        return -1;

    component_id = ql[0][0];
    component_id_cache[component] = component_id

    return component_id

def get_location_id (location, component, archive):
    global location_id_cache

    cache_key = location + '~' + component + '~' + location
    if location_id_cache.has_key(cache_key):
        return location_id_cache[cache_key]

    archive_id = get_archive_id (archive)
    if component != "":
        component_id = get_component_id (component)
        if component_id != -1:
            q = projectB.query("SELECT id FROM location WHERE path = '%s' AND component = %d AND archive = %d" % (location, component_id, archive_id))
    else:
        q = projectB.query("SELECT id FROM location WHERE path = '%s' AND archive = %d" % (location, archive_id))
    ql = q.getresult();
    if not ql:
        return -1;

    location_id = ql[0][0]
    location_id_cache[cache_key] = location_id

    return location_id

def get_source_id (source, version):
    global source_id_cache

    cache_key = source + '~' + version + '~'
    if source_id_cache.has_key(cache_key):
        return source_id_cache[cache_key]

    q = projectB.query("SELECT id FROM source s WHERE s.source = '%s' AND s.version = '%s'" % (source, version))

    if not q.getresult():
        return None

    source_id = q.getresult()[0][0]
    source_id_cache[cache_key] = source_id

    return source_id

##########################################################################################

def get_or_set_maintainer_id (maintainer):
    global maintainer_id_cache

    if maintainer_id_cache.has_key(maintainer):
        return maintainer_id_cache[maintainer]

    q = projectB.query("SELECT id FROM maintainer WHERE name = '%s'" % (maintainer))
    if not q.getresult():
        projectB.query("INSERT INTO maintainer (name) VALUES ('%s')" % (maintainer))
        q = projectB.query("SELECT id FROM maintainer WHERE name = '%s'" % (maintainer))
    maintainer_id = q.getresult()[0][0]
    maintainer_id_cache[maintainer] = maintainer_id

    return maintainer_id

##########################################################################################

def get_files_id (filename, size, md5sum, location_id):
    global files_id_cache

    cache_key = "%s~%d" % (filename, location_id);

    if files_id_cache.has_key(cache_key):
        return files_id_cache[cache_key]

    size = int(size);
    q = projectB.query("SELECT id, size, md5sum FROM files WHERE filename = '%s' AND location = %d" % (filename, location_id));
    ql = q.getresult();
    if ql:
        if len(ql) != 1:
            return -1;
        ql = ql[0];
        orig_size = int(ql[1]);
        orig_md5sum = ql[2];
        if orig_size != size or orig_md5sum != md5sum:
            return -2;
        files_id_cache[cache_key] = ql[0];
        return files_id_cache[cache_key]
    else:
        return None


##########################################################################################

def set_files_id (filename, size, md5sum, location_id):
    global files_id_cache

    cache_key = "%s~%d" % (filename, location_id);

    #print "INSERT INTO files (filename, size, md5sum, location) VALUES ('%s', %d, '%s', %d)" % (filename, long(size), md5sum, location_id);
    projectB.query("INSERT INTO files (filename, size, md5sum, location) VALUES ('%s', %d, '%s', %d)" % (filename, long(size), md5sum, location_id));
    q = projectB.query("SELECT id FROM files WHERE id = currval('files_id_seq')");
    ql = q.getresult()[0];
    files_id_cache[cache_key] = ql[0]

    return files_id_cache[cache_key]

##########################################################################################

def get_maintainer (maintainer_id):
    global maintainer_cache;

    if not maintainer_cache.has_key(maintainer_id):
        q = projectB.query("SELECT name FROM maintainer WHERE id = %s" % (maintainer_id));
        maintainer_cache[maintainer_id] = q.getresult()[0][0];

    return maintainer_cache[maintainer_id];

##########################################################################################
