#!/usr/bin/python

"""
Generate Packages/Sources files

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011  Ansgar Burchardt <ansgar@debian.org>
@copyright: Based on daklib/lists.py and dak/generate_filelist.py:
            2009-2011  Torsten Werner <twerner@debian.org>
@copyright: Based on dak/generate_packages_sources.py:
            2000, 2001, 2002, 2006  James Troup <james@nocrew.org>
            2009  Mark Hymers <mhy@debian.org>
            2010  Joerg Jaspert <joerg@debian.org>
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

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils, daklog
from daklib.dakmultiprocessing import Pool
from daklib.filewriter import PackagesFileWriter, SourcesFileWriter

import apt_pkg, os, stat, sys

def usage():
    print """Usage: dak generate-packages-sources2 [OPTIONS]
Generate the Packages/Sources files

  -s, --suite=SUITE            process this suite
                               Default: All suites not marked 'untouchable'
  -f, --force                  Allow processing of untouchable suites
                               CAREFUL: Only to be used at point release time!
  -h, --help                   show this help and exit

SUITE can be a space seperated list, e.g.
   --suite=unstable testing
"""
    sys.exit()

#############################################################################

# Here be dragons.
_sources_query = R"""
SELECT

  (SELECT
     STRING_AGG(
       CASE
         WHEN key = 'Source' THEN 'Package\: '
         WHEN key = 'Files' THEN E'Files\:\n ' || f.md5sum || ' ' || f.size || ' ' || SUBSTRING(f.filename FROM E'/([^/]*)\\Z')
         WHEN key = 'Checksums-Sha1' THEN E'Checksums-Sha1\:\n ' || f.sha1sum || ' ' || f.size || ' ' || SUBSTRING(f.filename FROM E'/([^/]*)\\Z')
         WHEN key = 'Checksums-Sha256' THEN E'Checksums-Sha256\:\n ' || f.sha256sum || ' ' || f.size || ' ' || SUBSTRING(f.filename FROM E'/([^/]*)\\Z')
         ELSE key || '\: '
       END || value, E'\n' ORDER BY mk.ordering, mk.key)
   FROM
     source_metadata sm
     JOIN metadata_keys mk ON mk.key_id = sm.key_id
   WHERE s.id=sm.src_id
  )
  ||
  E'\nDirectory\: pool/' || SUBSTRING(f.filename FROM E'\\A(.*)/[^/]*\\Z')
  ||
  E'\nPriority\: ' || pri.priority
  ||
  E'\nSection\: ' || sec.section

FROM

source s
JOIN src_associations sa ON s.id = sa.source
JOIN files f ON s.file=f.id
JOIN override o ON o.package = s.source
JOIN section sec ON o.section = sec.id
JOIN priority pri ON o.priority = pri.id

WHERE
  sa.suite = :suite
  AND o.suite = :overridesuite AND o.component = :component AND o.type = :dsc_type

ORDER BY
s.source, s.version
"""

def generate_sources(suite_id, component_id):
    global _sources_query

    session = DBConn().session()
    dsc_type = session.query(OverrideType).filter_by(overridetype='dsc').one().overridetype_id

    suite = session.query(Suite).get(suite_id)
    component = session.query(Component).get(component_id)

    overridesuite_id = suite.get_overridesuite().suite_id

    writer = SourcesFileWriter(suite=suite.suite_name, component=component.component_name)
    output = writer.open()

    # run query and write Sources
    r = session.execute(_sources_query, {"suite": suite_id, "component": component_id, "dsc_type": dsc_type, "overridesuite": overridesuite_id})
    for (stanza,) in r:
        print >>output, stanza
        print >>output, ""

    writer.close()

    message = ["generate sources", suite.suite_name, component.component_name]
    session.rollback()
    return message

#############################################################################

# Here be large dragons.
_packages_query = R"""
WITH

  tmp AS (
    SELECT
      b.id AS binary_id,
      b.package AS package,
      b.version AS version,
      b.architecture AS architecture,
      b.source AS source_id,
      s.source AS source,
      f.filename AS filename,
      f.size AS size,
      f.md5sum AS md5sum,
      f.sha1sum AS sha1sum,
      f.sha256sum AS sha256sum
    FROM
      binaries b
      JOIN bin_associations ba ON b.id = ba.bin
      JOIN files f ON f.id = b.file
      JOIN location l ON l.id = f.location
      JOIN source s ON b.source = s.id
    WHERE
      (b.architecture = :arch_all OR b.architecture = :arch) AND b.type = :type_name
      AND ba.suite = :suite
      AND l.component = :component
  )

SELECT
  (SELECT
     STRING_AGG(key || '\: ' || value, E'\n' ORDER BY mk.ordering, mk.key)
   FROM
     binaries_metadata bm
     JOIN metadata_keys mk ON mk.key_id = bm.key_id
   WHERE
     bm.bin_id = tmp.binary_id
     AND key != 'Section' AND key != 'Priority'
  )
  || COALESCE(E'\n' || (SELECT
     STRING_AGG(key || '\: ' || value, E'\n' ORDER BY key)
   FROM external_overrides eo
   WHERE eo.package = tmp.package
  ), '')
  || E'\nSection\: ' || sec.section
  || E'\nPriority\: ' || pri.priority
  || E'\nFilename\: pool/' || tmp.filename
  || E'\nSize\: ' || tmp.size
  || E'\nMD5sum\: ' || tmp.md5sum
  || E'\nSHA1\: ' || tmp.sha1sum
  || E'\nSHA256\: ' || tmp.sha256sum

FROM
  tmp
  JOIN override o ON o.package = tmp.package
  JOIN section sec ON sec.id = o.section
  JOIN priority pri ON pri.id = o.priority

WHERE
  (
      architecture <> :arch_all
    OR
      (architecture = :arch_all AND source_id IN (SELECT source_id FROM tmp WHERE architecture <> :arch_all))
    OR
      (architecture = :arch_all AND source NOT IN (SELECT DISTINCT source FROM tmp WHERE architecture <> :arch_all))
  )
  AND
    o.type = :type_id AND o.suite = :overridesuite AND o.component = :component

ORDER BY tmp.package, tmp.version
"""

def generate_packages(suite_id, component_id, architecture_id, type_name):
    global _packages_query

    session = DBConn().session()
    arch_all_id = session.query(Architecture).filter_by(arch_string='all').one().arch_id
    type_id = session.query(OverrideType).filter_by(overridetype=type_name).one().overridetype_id

    suite = session.query(Suite).get(suite_id)
    component = session.query(Component).get(component_id)
    architecture = session.query(Architecture).get(architecture_id)

    overridesuite_id = suite.get_overridesuite().suite_id

    writer = PackagesFileWriter(suite=suite.suite_name, component=component.component_name,
            architecture=architecture.arch_string, debtype=type_name)
    output = writer.open()

    r = session.execute(_packages_query, {"suite": suite_id, "component": component_id,
        "arch": architecture_id, "type_id": type_id, "type_name": type_name, "arch_all": arch_all_id,
        "overridesuite": overridesuite_id})
    for (stanza,) in r:
        print >>output, stanza
        print >>output, ""

    writer.close()

    message = ["generate-packages", suite.suite_name, component.component_name, architecture.arch_string]
    session.rollback()
    return message

#############################################################################

def main():
    cnf = Config()

    Arguments = [('h',"help","Generate-Packages-Sources::Options::Help"),
                 ('s',"suite","Generate-Packages-Sources::Options::Suite"),
                 ('f',"force","Generate-Packages-Sources::Options::Force")]

    suite_names = apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    try:
        Options = cnf.SubTree("Generate-Packages-Sources::Options")
    except KeyError:
        Options = {}

    if Options.has_key("Help"):
        usage()

    logger = daklog.Logger(cnf, 'generate-packages-sources2')

    session = DBConn().session()

    if Options.has_key("Suite"):
        suites = []
        for s in suite_names:
            suite = get_suite(s.lower(), session)
            if suite:
                suites.append(suite)
            else:
                print "I: Cannot find suite %s" % s
                logger.log(['Cannot find suite %s' % s])
    else:
        suites = session.query(Suite).filter(Suite.untouchable == False).all()

    force = Options.has_key("Force") and Options["Force"]

    component_ids = [ c.component_id for c in session.query(Component).all() ]

    def log(details):
        logger.log(details)

    pool = Pool()
    for s in suites:
        if s.untouchable and not force:
            utils.fubar("Refusing to touch %s (untouchable and not forced)" % s.suite_name)
        for c in component_ids:
            pool.apply_async(generate_sources, [s.suite_id, c], callback=log)
            for a in s.architectures:
                pool.apply_async(generate_packages, [s.suite_id, c, a.arch_id, 'deb'], callback=log)
                pool.apply_async(generate_packages, [s.suite_id, c, a.arch_id, 'udeb'], callback=log)

    pool.close()
    pool.join()
    # this script doesn't change the database
    session.close()

if __name__ == '__main__':
    main()
