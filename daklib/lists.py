#!/usr/bin/python

"""
Helper functions for list generating commands (Packages, Sources).

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009-2011  Torsten Werner <twerner@debian.org>
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

from dbconn import get_architecture

def fetch(query, args, session):
    for (id, path, filename) in session.execute(query, args).fetchall():
        yield (id, path + filename)

def getSources(suite, component, session, timestamp = None):
    '''
    Calculates the sources in suite and component optionally limited by
    sources newer than timestamp.  Returns a generator that yields a
    tuple of source id and full pathname to the dsc file. See function
    writeSourceList() in dak/generate_filelist.py for an example that
    uses this function.
    '''
    extra_cond = ""
    if timestamp:
        extra_cond = "AND extract(epoch from sa.created) > %d" % timestamp
    query = """
        SELECT s.id, archive.path || 'pool/', c.name || '/' || f.filename
            FROM source s
            JOIN src_associations sa
                ON s.id = sa.source AND sa.suite = :suite %s
            JOIN suite
                ON sa.suite = suite.id
            JOIN archive
                ON suite.archive_id = archive.id
            JOIN files f
                ON s.file = f.id
            JOIN files_archive_map fam
                ON fam.file_id = f.id AND fam.component_id = :component
            JOIN component c
                ON fam.component_id = c.id
            ORDER BY filename
    """ % extra_cond
    args = { 'suite': suite.suite_id,
             'component': component.component_id }
    return fetch(query, args, session)

def getArchAll(suite, component, architecture, type, session, timestamp = None):
    '''
    Calculates all binaries in suite and component of architecture 'all' (and
    only 'all') and type 'deb' or 'udeb' optionally limited to binaries newer
    than timestamp.  Returns a generator that yields a tuple of binary id and
    full pathname to the u(deb) file. See function writeAllList() in
    dak/generate_filelist.py for an example that uses this function.
    '''
    query = suite.clone(session).binaries. \
        filter_by(architecture = architecture, binarytype = type)
    if timestamp is not None:
        extra_cond = 'extract(epoch from bin_associations.created) > %d' % timestamp
        query = query.filter(extra_cond)
    for binary in query:
        yield (binary.binary_id, binary.poolfile.fullpath)

def getBinaries(suite, component, architecture, type, session, timestamp = None):
    '''
    Calculates the binaries in suite and component of architecture and
    type 'deb' or 'udeb' optionally limited to binaries newer than
    timestamp.  Returns a generator that yields a tuple of binary id and
    full pathname to the u(deb) file. See function writeBinaryList() in
    dak/generate_filelist.py for an example that uses this function.
    '''
    extra_cond = ""
    if timestamp:
        extra_cond = "AND extract(epoch from ba.created) > %d" % timestamp
    query = """
CREATE TEMP TABLE b_candidates (
    id integer,
    source integer,
    file integer,
    architecture integer);

INSERT INTO b_candidates (id, source, file, architecture)
    SELECT b.id, b.source, b.file, b.architecture
        FROM binaries b
        JOIN bin_associations ba ON b.id = ba.bin
        WHERE b.type = :type AND ba.suite = :suite AND
            b.architecture IN (:arch_all, :architecture) %s;

CREATE TEMP TABLE gf_candidates (
    id integer,
    filename text,
    path text,
    architecture integer,
    src integer,
    source text);

INSERT INTO gf_candidates (id, filename, path, architecture, src, source)
    SELECT bc.id, c.name || '/' || f.filename, archive.path || 'pool/' , bc.architecture, bc.source as src, s.source
        FROM b_candidates bc
        JOIN source s ON bc.source = s.id
        JOIN files f ON bc.file = f.id
        JOIN files_archive_map fam ON f.id = fam.file_id
        JOIN component c ON fam.component_id = c.id
        JOIN archive ON fam.archive_id = archive.id
        JOIN suite ON suite.archive_id = archive.id

        WHERE c.id = :component AND suite.id = :suite;

WITH arch_any AS

    (SELECT id, path, filename FROM gf_candidates
        WHERE architecture <> :arch_all),

     arch_all_with_any AS
    (SELECT id, path, filename FROM gf_candidates
        WHERE architecture = :arch_all AND
              src IN (SELECT src FROM gf_candidates WHERE architecture <> :arch_all)),

     arch_all_without_any AS
    (SELECT id, path, filename FROM gf_candidates
        WHERE architecture = :arch_all AND
              source NOT IN (SELECT DISTINCT source FROM gf_candidates WHERE architecture <> :arch_all)),

     filelist AS
    (SELECT * FROM arch_any
    UNION
    SELECT * FROM arch_all_with_any
    UNION
    SELECT * FROM arch_all_without_any)

    SELECT * FROM filelist ORDER BY filename
    """ % extra_cond
    args = { 'suite': suite.suite_id,
             'component': component.component_id,
             'architecture': architecture.arch_id,
             'arch_all': get_architecture('all', session).arch_id,
             'type': type }
    return fetch(query, args, session)

