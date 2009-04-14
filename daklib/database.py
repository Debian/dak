#!/usr/bin/env python

""" DB access functions
@group readonly: get_suite_id, get_section_id, get_priority_id, get_override_type_id,
                 get_architecture_id, get_archive_id, get_component_id, get_location_id,
                 get_source_id, get_suite_version, get_files_id, get_maintainer, get_suites,
                 get_suite_architectures, get_new_comments, has_new_comment
@group read/write: get_or_set*, set_files_id
@group writeonly: add_new_comment, delete_new_comments

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
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

import sys
import time
import types
import utils
from binary import Binary

################################################################################

Cnf = None                    #: Configuration, apt_pkg.Configuration
projectB = None               #: database connection, pgobject
suite_id_cache = {}           #: cache for suites
section_id_cache = {}         #: cache for sections
priority_id_cache = {}        #: cache for priorities
override_type_id_cache = {}   #: cache for overrides
architecture_id_cache = {}    #: cache for architectures
archive_id_cache = {}         #: cache for archives
component_id_cache = {}       #: cache for components
location_id_cache = {}        #: cache for locations
maintainer_id_cache = {}      #: cache for maintainers
keyring_id_cache = {}         #: cache for keyrings
source_id_cache = {}          #: cache for sources

files_id_cache = {}           #: cache for files
maintainer_cache = {}         #: cache for maintainer names
fingerprint_id_cache = {}     #: cache for fingerprints
queue_id_cache = {}           #: cache for queues
uid_id_cache = {}             #: cache for uids
suite_version_cache = {}      #: cache for suite_versions (packages)
suite_bin_version_cache = {}
cache_preloaded = False

################################################################################

def init (config, sql):
    """
    database module init.

    @type config: apt_pkg.Configuration
    @param config: apt config, see U{http://apt.alioth.debian.org/python-apt-doc/apt_pkg/cache.html#Configuration}

    @type sql: pgobject
    @param sql: database connection

    """
    global Cnf, projectB

    Cnf = config
    projectB = sql


def do_query(query):
    """
    Executes a database query. Writes statistics / timing to stderr.

    @type query: string
    @param query: database query string, passed unmodified

    @return: db result

    @warning: The query is passed B{unmodified}, so be careful what you use this for.
    """
    sys.stderr.write("query: \"%s\" ... " % (query))
    before = time.time()
    r = projectB.query(query)
    time_diff = time.time()-before
    sys.stderr.write("took %.3f seconds.\n" % (time_diff))
    if type(r) is int:
        sys.stderr.write("int result: %s\n" % (r))
    elif type(r) is types.NoneType:
        sys.stderr.write("result: None\n")
    else:
        sys.stderr.write("pgresult: %s\n" % (r.getresult()))
    return r

################################################################################

def get_suite_id (suite):
    """
    Returns database id for given C{suite}.
    Results are kept in a cache during runtime to minimize database queries.

    @type suite: string
    @param suite: The name of the suite

    @rtype: int
    @return: the database id for the given suite

    """
    global suite_id_cache

    if suite_id_cache.has_key(suite):
        return suite_id_cache[suite]

    q = projectB.query("SELECT id FROM suite WHERE suite_name = '%s'" % (suite))
    ql = q.getresult()
    if not ql:
        return -1

    suite_id = ql[0][0]
    suite_id_cache[suite] = suite_id

    return suite_id

def get_section_id (section):
    """
    Returns database id for given C{section}.
    Results are kept in a cache during runtime to minimize database queries.

    @type section: string
    @param section: The name of the section

    @rtype: int
    @return: the database id for the given section

    """
    global section_id_cache

    if section_id_cache.has_key(section):
        return section_id_cache[section]

    q = projectB.query("SELECT id FROM section WHERE section = '%s'" % (section))
    ql = q.getresult()
    if not ql:
        return -1

    section_id = ql[0][0]
    section_id_cache[section] = section_id

    return section_id

def get_priority_id (priority):
    """
    Returns database id for given C{priority}.
    Results are kept in a cache during runtime to minimize database queries.

    @type priority: string
    @param priority: The name of the priority

    @rtype: int
    @return: the database id for the given priority

    """
    global priority_id_cache

    if priority_id_cache.has_key(priority):
        return priority_id_cache[priority]

    q = projectB.query("SELECT id FROM priority WHERE priority = '%s'" % (priority))
    ql = q.getresult()
    if not ql:
        return -1

    priority_id = ql[0][0]
    priority_id_cache[priority] = priority_id

    return priority_id

def get_override_type_id (type):
    """
    Returns database id for given override C{type}.
    Results are kept in a cache during runtime to minimize database queries.

    @type type: string
    @param type: The name of the override type

    @rtype: int
    @return: the database id for the given override type

    """
    global override_type_id_cache

    if override_type_id_cache.has_key(type):
        return override_type_id_cache[type]

    q = projectB.query("SELECT id FROM override_type WHERE type = '%s'" % (type))
    ql = q.getresult()
    if not ql:
        return -1

    override_type_id = ql[0][0]
    override_type_id_cache[type] = override_type_id

    return override_type_id

def get_architecture_id (architecture):
    """
    Returns database id for given C{architecture}.
    Results are kept in a cache during runtime to minimize database queries.

    @type architecture: string
    @param architecture: The name of the override type

    @rtype: int
    @return: the database id for the given architecture

    """
    global architecture_id_cache

    if architecture_id_cache.has_key(architecture):
        return architecture_id_cache[architecture]

    q = projectB.query("SELECT id FROM architecture WHERE arch_string = '%s'" % (architecture))
    ql = q.getresult()
    if not ql:
        return -1

    architecture_id = ql[0][0]
    architecture_id_cache[architecture] = architecture_id

    return architecture_id

def get_archive_id (archive):
    """
    Returns database id for given C{archive}.
    Results are kept in a cache during runtime to minimize database queries.

    @type archive: string
    @param archive: The name of the override type

    @rtype: int
    @return: the database id for the given archive

    """
    global archive_id_cache

    archive = archive.lower()

    if archive_id_cache.has_key(archive):
        return archive_id_cache[archive]

    q = projectB.query("SELECT id FROM archive WHERE lower(name) = '%s'" % (archive))
    ql = q.getresult()
    if not ql:
        return -1

    archive_id = ql[0][0]
    archive_id_cache[archive] = archive_id

    return archive_id

def get_component_id (component):
    """
    Returns database id for given C{component}.
    Results are kept in a cache during runtime to minimize database queries.

    @type component: string
    @param component: The name of the component

    @rtype: int
    @return: the database id for the given component

    """
    global component_id_cache

    component = component.lower()

    if component_id_cache.has_key(component):
        return component_id_cache[component]

    q = projectB.query("SELECT id FROM component WHERE lower(name) = '%s'" % (component))
    ql = q.getresult()
    if not ql:
        return -1

    component_id = ql[0][0]
    component_id_cache[component] = component_id

    return component_id

def get_location_id (location, component, archive):
    """
    Returns database id for the location behind the given combination of
      - B{location} - the path of the location, eg. I{/srv/ftp.debian.org/ftp/pool/}
      - B{component} - the id of the component as returned by L{get_component_id}
      - B{archive} - the id of the archive as returned by L{get_archive_id}
    Results are kept in a cache during runtime to minimize database queries.

    @type location: string
    @param location: the path of the location

    @type component: int
    @param component: the id of the component

    @type archive: int
    @param archive: the id of the archive

    @rtype: int
    @return: the database id for the location

    """
    global location_id_cache

    cache_key = location + '_' + component + '_' + location
    if location_id_cache.has_key(cache_key):
        return location_id_cache[cache_key]

    archive_id = get_archive_id (archive)
    if component != "":
        component_id = get_component_id (component)
        if component_id != -1:
            q = projectB.query("SELECT id FROM location WHERE path = '%s' AND component = %d AND archive = %d" % (location, component_id, archive_id))
    else:
        q = projectB.query("SELECT id FROM location WHERE path = '%s' AND archive = %d" % (location, archive_id))
    ql = q.getresult()
    if not ql:
        return -1

    location_id = ql[0][0]
    location_id_cache[cache_key] = location_id

    return location_id

def get_source_id (source, version):
    """
    Returns database id for the combination of C{source} and C{version}
      - B{source} - source package name, eg. I{mailfilter}, I{bbdb}, I{glibc}
      - B{version}
    Results are kept in a cache during runtime to minimize database queries.

    @type source: string
    @param source: source package name

    @type version: string
    @param version: the source version

    @rtype: int
    @return: the database id for the source

    """
    global source_id_cache

    cache_key = source + '_' + version + '_'
    if source_id_cache.has_key(cache_key):
        return source_id_cache[cache_key]

    q = projectB.query("SELECT id FROM source s WHERE s.source = '%s' AND s.version = '%s'" % (source, version))

    if not q.getresult():
        return None

    source_id = q.getresult()[0][0]
    source_id_cache[cache_key] = source_id

    return source_id

def get_suite_version(source, suite):
    """
    Returns database id for a combination of C{source} and C{suite}.

      - B{source} - source package name, eg. I{mailfilter}, I{bbdb}, I{glibc}
      - B{suite} - a suite name, eg. I{unstable}

    Results are kept in a cache during runtime to minimize database queries.

    @type source: string
    @param source: source package name

    @type suite: string
    @param suite: the suite name

    @rtype: string
    @return: the version for I{source} in I{suite}

    """

    global suite_version_cache
    cache_key = "%s_%s" % (source, suite)

    if suite_version_cache.has_key(cache_key):
        return suite_version_cache[cache_key]

    q = projectB.query("""
    SELECT s.version FROM source s, suite su, src_associations sa
    WHERE sa.source=s.id
      AND sa.suite=su.id
      AND su.suite_name='%s'
      AND s.source='%s'"""
                              % (suite, source))

    if not q.getresult():
        return None

    version = q.getresult()[0][0]
    suite_version_cache[cache_key] = version

    return version

def get_latest_binary_version_id(binary, section, suite, arch):
    global suite_bin_version_cache
    cache_key = "%s_%s_%s_%s" % (binary, section, suite, arch)
    cache_key_all = "%s_%s_%s_%s" % (binary, section, suite, get_architecture_id("all"))

    # Check for the cache hit for its arch, then arch all
    if suite_bin_version_cache.has_key(cache_key):
        return suite_bin_version_cache[cache_key]
    if suite_bin_version_cache.has_key(cache_key_all):
        return suite_bin_version_cache[cache_key_all]
    if cache_preloaded == True:
        return # package does not exist

    q = projectB.query("SELECT DISTINCT b.id FROM binaries b JOIN bin_associations ba ON (b.id = ba.bin) JOIN override o ON (o.package=b.package) WHERE b.package = '%s' AND b.architecture = '%d' AND ba.suite = '%d' AND o.section = '%d'" % (binary, int(arch), int(suite), int(section)))

    if not q.getresult():
        return False

    highest_bid = q.getresult()[0][0]

    suite_bin_version_cache[cache_key] = highest_bid
    return highest_bid

def preload_binary_id_cache():
    global suite_bin_version_cache, cache_preloaded

    # Get suite info
    q = projectB.query("SELECT id FROM suite")
    suites = q.getresult()

    # Get arch mappings
    q = projectB.query("SELECT id FROM architecture")
    arches = q.getresult()

    for suite in suites:
        for arch in arches:
            q = projectB.query("SELECT DISTINCT b.id, b.package, o.section FROM binaries b JOIN bin_associations ba ON (b.id = ba.bin) JOIN override o ON (o.package=b.package) WHERE b.architecture = '%d' AND ba.suite = '%d'" % (int(arch[0]), int(suite[0])))

            for bi in q.getresult():
                cache_key = "%s_%s_%s_%s" % (bi[1], bi[2], suite[0], arch[0])
                suite_bin_version_cache[cache_key] = int(bi[0])

    cache_preloaded = True

def get_suite_architectures(suite):
    """
    Returns list of architectures for C{suite}.

    @type suite: string, int
    @param suite: the suite name or the suite_id

    @rtype: list
    @return: the list of architectures for I{suite}
    """

    suite_id = None
    if type(suite) == str:
        suite_id = get_suite_id(suite)
    elif type(suite) == int:
        suite_id = suite
    else:
        return None

    sql = """ SELECT a.arch_string FROM suite_architectures sa
              JOIN architecture a ON (a.id = sa.architecture)
              WHERE suite='%s' """ % (suite_id)

    q = projectB.query(sql)
    return map(lambda x: x[0], q.getresult())

def get_suite_untouchable(suite):
    """
    Returns true if the C{suite} is untouchable, otherwise false.

    @type suite: string, int
    @param suite: the suite name or the suite_id

    @rtype: boolean
    @return: status of suite
    """

    suite_id = None
    if type(suite) == str:
        suite_id = get_suite_id(suite.lower())
    elif type(suite) == int:
        suite_id = suite
    else:
        return None

    sql = """ SELECT untouchable FROM suite WHERE id='%s' """ % (suite_id)

    q = projectB.query(sql)
    if q.getresult()[0][0] == "f":
        return False
    else:
        return True

################################################################################

def get_or_set_maintainer_id (maintainer):
    """
    If C{maintainer} does not have an entry in the maintainer table yet, create one
    and return the new id.
    If C{maintainer} already has an entry, simply return the existing id.

    Results are kept in a cache during runtime to minimize database queries.

    @type maintainer: string
    @param maintainer: the maintainer name

    @rtype: int
    @return: the database id for the maintainer

    """
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

################################################################################

def get_or_set_keyring_id (keyring):
    """
    If C{keyring} does not have an entry in the C{keyrings} table yet, create one
    and return the new id.
    If C{keyring} already has an entry, simply return the existing id.

    Results are kept in a cache during runtime to minimize database queries.

    @type keyring: string
    @param keyring: the keyring name

    @rtype: int
    @return: the database id for the keyring

    """
    global keyring_id_cache

    if keyring_id_cache.has_key(keyring):
        return keyring_id_cache[keyring]

    q = projectB.query("SELECT id FROM keyrings WHERE name = '%s'" % (keyring))
    if not q.getresult():
        projectB.query("INSERT INTO keyrings (name) VALUES ('%s')" % (keyring))
        q = projectB.query("SELECT id FROM keyrings WHERE name = '%s'" % (keyring))
    keyring_id = q.getresult()[0][0]
    keyring_id_cache[keyring] = keyring_id

    return keyring_id

################################################################################

def get_or_set_uid_id (uid):
    """
    If C{uid} does not have an entry in the uid table yet, create one
    and return the new id.
    If C{uid} already has an entry, simply return the existing id.

    Results are kept in a cache during runtime to minimize database queries.

    @type uid: string
    @param uid: the uid.

    @rtype: int
    @return: the database id for the uid

    """

    global uid_id_cache

    if uid_id_cache.has_key(uid):
        return uid_id_cache[uid]

    q = projectB.query("SELECT id FROM uid WHERE uid = '%s'" % (uid))
    if not q.getresult():
        projectB.query("INSERT INTO uid (uid) VALUES ('%s')" % (uid))
        q = projectB.query("SELECT id FROM uid WHERE uid = '%s'" % (uid))
    uid_id = q.getresult()[0][0]
    uid_id_cache[uid] = uid_id

    return uid_id

################################################################################

def get_or_set_fingerprint_id (fingerprint):
    """
    If C{fingerprint} does not have an entry in the fingerprint table yet, create one
    and return the new id.
    If C{fingerprint} already has an entry, simply return the existing id.

    Results are kept in a cache during runtime to minimize database queries.

    @type fingerprint: string
    @param fingerprint: the fingerprint

    @rtype: int
    @return: the database id for the fingerprint

    """
    global fingerprint_id_cache

    if fingerprint_id_cache.has_key(fingerprint):
        return fingerprint_id_cache[fingerprint]

    q = projectB.query("SELECT id FROM fingerprint WHERE fingerprint = '%s'" % (fingerprint))
    if not q.getresult():
        projectB.query("INSERT INTO fingerprint (fingerprint) VALUES ('%s')" % (fingerprint))
        q = projectB.query("SELECT id FROM fingerprint WHERE fingerprint = '%s'" % (fingerprint))
    fingerprint_id = q.getresult()[0][0]
    fingerprint_id_cache[fingerprint] = fingerprint_id

    return fingerprint_id

################################################################################

def get_files_id (filename, size, md5sum, location_id):
    """
    Returns -1, -2 or the file_id for filename, if its C{size} and C{md5sum} match an
    existing copy.

    The database is queried using the C{filename} and C{location_id}. If a file does exist
    at that location, the existing size and md5sum are checked against the provided
    parameters. A size or checksum mismatch returns -2. If more than one entry is
    found within the database, a -1 is returned, no result returns None, otherwise
    the file id.

    Results are kept in a cache during runtime to minimize database queries.

    @type filename: string
    @param filename: the filename of the file to check against the DB

    @type size: int
    @param size: the size of the file to check against the DB

    @type md5sum: string
    @param md5sum: the md5sum of the file to check against the DB

    @type location_id: int
    @param location_id: the id of the location as returned by L{get_location_id}

    @rtype: int / None
    @return: Various return values are possible:
               - -2: size/checksum error
               - -1: more than one file found in database
               - None: no file found in database
               - int: file id

    """
    global files_id_cache

    cache_key = "%s_%d" % (filename, location_id)

    if files_id_cache.has_key(cache_key):
        return files_id_cache[cache_key]

    size = int(size)
    q = projectB.query("SELECT id, size, md5sum FROM files WHERE filename = '%s' AND location = %d" % (filename, location_id))
    ql = q.getresult()
    if ql:
        if len(ql) != 1:
            return -1
        ql = ql[0]
        orig_size = int(ql[1])
        orig_md5sum = ql[2]
        if orig_size != size or orig_md5sum != md5sum:
            return -2
        files_id_cache[cache_key] = ql[0]
        return files_id_cache[cache_key]
    else:
        return None

################################################################################

def get_or_set_queue_id (queue):
    """
    If C{queue} does not have an entry in the queue table yet, create one
    and return the new id.
    If C{queue} already has an entry, simply return the existing id.

    Results are kept in a cache during runtime to minimize database queries.

    @type queue: string
    @param queue: the queue name (no full path)

    @rtype: int
    @return: the database id for the queue

    """
    global queue_id_cache

    if queue_id_cache.has_key(queue):
        return queue_id_cache[queue]

    q = projectB.query("SELECT id FROM queue WHERE queue_name = '%s'" % (queue))
    if not q.getresult():
        projectB.query("INSERT INTO queue (queue_name) VALUES ('%s')" % (queue))
        q = projectB.query("SELECT id FROM queue WHERE queue_name = '%s'" % (queue))
    queue_id = q.getresult()[0][0]
    queue_id_cache[queue] = queue_id

    return queue_id

################################################################################

def set_files_id (filename, size, md5sum, sha1sum, sha256sum, location_id):
    """
    Insert a new entry into the files table and return its id.

    @type filename: string
    @param filename: the filename

    @type size: int
    @param size: the size in bytes

    @type md5sum: string
    @param md5sum: md5sum of the file

    @type sha1sum: string
    @param sha1sum: sha1sum of the file

    @type sha256sum: string
    @param sha256sum: sha256sum of the file

    @type location_id: int
    @param location_id: the id of the location as returned by L{get_location_id}

    @rtype: int
    @return: the database id for the new file

    """
    global files_id_cache

    projectB.query("INSERT INTO files (filename, size, md5sum, sha1sum, sha256sum, location) VALUES ('%s', %d, '%s', '%s', '%s', %d)" % (filename, long(size), md5sum, sha1sum, sha256sum, location_id))

    return get_files_id (filename, size, md5sum, location_id)

    ### currval has issues with postgresql 7.1.3 when the table is big
    ### it was taking ~3 seconds to return on auric which is very Not
    ### Cool(tm).
    ##
    ##q = projectB.query("SELECT id FROM files WHERE id = currval('files_id_seq')")
    ##ql = q.getresult()[0]
    ##cache_key = "%s_%d" % (filename, location_id)
    ##files_id_cache[cache_key] = ql[0]
    ##return files_id_cache[cache_key]

################################################################################

def get_maintainer (maintainer_id):
    """
    Return the name of the maintainer behind C{maintainer_id}.

    Results are kept in a cache during runtime to minimize database queries.

    @type maintainer_id: int
    @param maintainer_id: the id of the maintainer, eg. from L{get_or_set_maintainer_id}

    @rtype: string
    @return: the name of the maintainer

    """
    global maintainer_cache

    if not maintainer_cache.has_key(maintainer_id):
        q = projectB.query("SELECT name FROM maintainer WHERE id = %s" % (maintainer_id))
        maintainer_cache[maintainer_id] = q.getresult()[0][0]

    return maintainer_cache[maintainer_id]

################################################################################

def get_suites(pkgname, src=False):
    """
    Return the suites in which C{pkgname} can be found. If C{src} is True query for source
    package, else binary package.

    @type pkgname: string
    @param pkgname: name of the package

    @type src: bool
    @param src: if True look for source packages, false (default) looks for binary.

    @rtype: list
    @return: list of suites, or empty list if no match

    """
    if src:
        sql = """
        SELECT suite_name
        FROM source,
             src_associations,
             suite
        WHERE source.id = src_associations.source
        AND   source.source = '%s'
        AND   src_associations.suite = suite.id
        """ % (pkgname)
    else:
        sql = """
        SELECT suite_name
        FROM binaries,
             bin_associations,
             suite
        WHERE binaries.id = bin_associations.bin
        AND   package = '%s'
        AND   bin_associations.suite = suite.id
        """ % (pkgname)

    q = projectB.query(sql)
    return map(lambda x: x[0], q.getresult())


################################################################################

def get_new_comments(package):
    """
    Returns all the possible comments attached to C{package} in NEW. All versions.

    @type package: string
    @param package: name of the package

    @rtype: list
    @return: list of strings containing comments for all versions from all authors for package
    """

    comments = []
    query = projectB.query(""" SELECT version, comment, author
                               FROM new_comments
                               WHERE package = '%s' """ % (package))

    for row in query.getresult():
        comments.append("\nAuthor: %s\nVersion: %s\n\n%s\n" % (row[2], row[0], row[1]))
        comments.append("-"*72)

    return comments

def has_new_comment(package, version):
    """
    Returns true if the given combination of C{package}, C{version} has a comment.

    @type package: string
    @param package: name of the package

    @type version: string
    @param version: package version

    @rtype: boolean
    @return: true/false
    """

    exists = projectB.query("""SELECT 1 FROM new_comments
                               WHERE package='%s'
                               AND version='%s'
                               LIMIT 1"""
                            % (package, version) ).getresult()

    if not exists:
        return False
    else:
        return True

def add_new_comment(package, version, comment, author):
    """
    Add a new comment for C{package}, C{version} written by C{author}

    @type package: string
    @param package: name of the package

    @type version: string
    @param version: package version

    @type comment: string
    @param comment: the comment

    @type author: string
    @param author: the authorname
    """

    projectB.query(""" INSERT INTO new_comments (package, version, comment, author)
                       VALUES ('%s', '%s', '%s', '%s')
    """ % (package, version, comment, author) )

    return

def delete_new_comments(package, version):
    """
    Delete a comment for C{package}, C{version}, if one exists
    """

    projectB.query(""" DELETE FROM new_comments
                       WHERE package = '%s' AND version = '%s'
    """ % (package, version))
    return

################################################################################
def copy_temporary_contents(package, version, arch, deb, reject):
    """
    copy the previously stored contents from the temp table to the permanant one

    during process-unchecked, the deb should have been scanned and the
    contents stored in pending_content_associations
    """

    # first see if contents exist:

    arch_id = get_architecture_id (arch)

    exists = projectB.query("""SELECT 1 FROM pending_content_associations
                               WHERE package='%s'
                               AND version='%s'
                               AND architecture=%d LIMIT 1"""
                            % (package, version, arch_id) ).getresult()

    if not exists:
        # This should NOT happen.  We should have added contents
        # during process-unchecked.  if it did, log an error, and send
        # an email.
        subst = {
            "__PACKAGE__": package,
            "__VERSION__": version,
            "__ARCH__": arch,
            "__TO_ADDRESS__": Cnf["Dinstall::MyAdminAddress"],
            "__DAK_ADDRESS__": Cnf["Dinstall::MyEmailAddress"] }

        message = utils.TemplateSubst(subst, Cnf["Dir::Templates"]+"/missing-contents")
        utils.send_mail( message )

        exists = Binary(deb, reject).scan_package()

    if exists:
        sql = """INSERT INTO content_associations(binary_pkg,filepath,filename)
                 SELECT currval('binaries_id_seq'), filepath, filename FROM pending_content_associations
                 WHERE package='%s'
                     AND version='%s'
                     AND architecture=%d""" % (package, version, arch_id)
        projectB.query(sql)
        projectB.query("""DELETE from pending_content_associations
                          WHERE package='%s'
                            AND version='%s'
                            AND architecture=%d""" % (package, version, arch_id))

    return exists
