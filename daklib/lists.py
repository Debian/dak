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
        SELECT s.id, l.path, f.filename
            FROM source s
            JOIN src_associations sa
                ON s.id = sa.source AND sa.suite = :suite %s
            JOIN files f
                ON s.file = f.id
            JOIN location l
                ON f.location = l.id AND l.component = :component
            ORDER BY filename
    """ % extra_cond
    args = { 'suite': suite.suite_id,
             'component': component.component_id }
    return fetch(query, args, session)

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
            b.architecture IN (2, :architecture) %s;

CREATE TEMP TABLE gf_candidates (
    id integer,
    filename text,
    path text,
    architecture integer,
    src integer,
    source text);

INSERT INTO gf_candidates (id, filename, path, architecture, src, source)
    SELECT bc.id, f.filename, l.path, bc.architecture, bc.source as src, s.source
        FROM b_candidates bc
        JOIN source s ON bc.source = s.id
        JOIN files f ON bc.file = f.id
        JOIN location l ON f.location = l.id
        WHERE l.component = :component;

WITH arch_any AS

    (SELECT id, path, filename FROM gf_candidates
        WHERE architecture > 2),

     arch_all_with_any AS
    (SELECT id, path, filename FROM gf_candidates
        WHERE architecture = 2 AND
              src IN (SELECT src FROM gf_candidates WHERE architecture > 2)),

     arch_all_without_any AS
    (SELECT id, path, filename FROM gf_candidates
        WHERE architecture = 2 AND
              source NOT IN (SELECT DISTINCT source FROM gf_candidates WHERE architecture > 2)),

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
             'type': type }
    return fetch(query, args, session)

