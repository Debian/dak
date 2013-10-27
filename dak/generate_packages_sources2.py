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

import apt_pkg, sys

def usage():
    print """Usage: dak generate-packages-sources2 [OPTIONS]
Generate the Packages/Sources files

  -a, --archive=ARCHIVE        process suites in ARCHIVE
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
         WHEN key = 'Source' THEN E'Package\: '
         WHEN key = 'Files' THEN E'Files\:\n ' || f.md5sum || ' ' || f.size || ' ' || SUBSTRING(f.filename FROM E'/([^/]*)\\Z')
         WHEN key = 'Checksums-Sha1' THEN E'Checksums-Sha1\:\n ' || f.sha1sum || ' ' || f.size || ' ' || SUBSTRING(f.filename FROM E'/([^/]*)\\Z')
         WHEN key = 'Checksums-Sha256' THEN E'Checksums-Sha256\:\n ' || f.sha256sum || ' ' || f.size || ' ' || SUBSTRING(f.filename FROM E'/([^/]*)\\Z')
         ELSE key || E'\: '
       END || value, E'\n' ORDER BY mk.ordering, mk.key)
   FROM
     source_metadata sm
     JOIN metadata_keys mk ON mk.key_id = sm.key_id
   WHERE s.id=sm.src_id
  )
  ||
  CASE
    WHEN src_associations_full.extra_source THEN E'\nExtra-Source-Only\: yes'
    ELSE ''
  END
  ||
  E'\nDirectory\: pool/' || :component_name || '/' || SUBSTRING(f.filename FROM E'\\A(.*)/[^/]*\\Z')
  ||
  E'\nPriority\: ' || COALESCE(pri.priority, 'extra')
  ||
  E'\nSection\: ' || COALESCE(sec.section, 'misc')

FROM

source s
JOIN src_associations_full ON src_associations_full.suite = :suite AND s.id = src_associations_full.source
JOIN files f ON s.file=f.id
JOIN files_archive_map fam
  ON fam.file_id = f.id
     AND fam.archive_id = (SELECT archive_id FROM suite WHERE id = :suite)
     AND fam.component_id = :component
LEFT JOIN override o ON o.package = s.source
                     AND o.suite = :overridesuite
                     AND o.component = :component
                     AND o.type = :dsc_type
LEFT JOIN section sec ON o.section = sec.id
LEFT JOIN priority pri ON o.priority = pri.id

WHERE
  (src_associations_full.extra_source OR o.suite IS NOT NULL)

ORDER BY
s.source, s.version
"""

def generate_sources(suite_id, component_id):
    global _sources_query
    from daklib.filewriter import SourcesFileWriter
    from daklib.dbconn import Component, DBConn, OverrideType, Suite
    from daklib.dakmultiprocessing import PROC_STATUS_SUCCESS

    session = DBConn().session()
    dsc_type = session.query(OverrideType).filter_by(overridetype='dsc').one().overridetype_id

    suite = session.query(Suite).get(suite_id)
    component = session.query(Component).get(component_id)

    overridesuite_id = suite.get_overridesuite().suite_id

    writer_args = {
            'archive': suite.archive.path,
            'suite': suite.suite_name,
            'component': component.component_name
    }
    if suite.indices_compression is not None:
        writer_args['compression'] = suite.indices_compression
    writer = SourcesFileWriter(**writer_args)
    output = writer.open()

    # run query and write Sources
    r = session.execute(_sources_query, {"suite": suite_id, "component": component_id, "component_name": component.component_name, "dsc_type": dsc_type, "overridesuite": overridesuite_id})
    for (stanza,) in r:
        print >>output, stanza
        print >>output, ""

    writer.close()

    message = ["generate sources", suite.suite_name, component.component_name]
    session.rollback()
    return (PROC_STATUS_SUCCESS, message)

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
      JOIN files_archive_map fam ON f.id = fam.file_id AND fam.archive_id = :archive_id
      JOIN source s ON b.source = s.id
    WHERE
      (b.architecture = :arch_all OR b.architecture = :arch) AND b.type = :type_name
      AND ba.suite = :suite
      AND fam.component_id = :component
  )

SELECT
  (SELECT
     STRING_AGG(key || E'\: ' || value, E'\n' ORDER BY ordering, key)
   FROM
     (SELECT key, ordering,
        CASE WHEN :include_long_description = 'false' AND key = 'Description'
          THEN SUBSTRING(value FROM E'\\A[^\n]*')
          ELSE value
        END AS value
      FROM
        binaries_metadata bm
        JOIN metadata_keys mk ON mk.key_id = bm.key_id
      WHERE
        bm.bin_id = tmp.binary_id
        AND key != ALL (:metadata_skip)
     ) AS metadata
  )
  || COALESCE(E'\n' || (SELECT
     STRING_AGG(key || E'\: ' || value, E'\n' ORDER BY key)
   FROM external_overrides eo
   WHERE
     eo.package = tmp.package
     AND eo.suite = :overridesuite AND eo.component = :component
  ), '')
  || E'\nSection\: ' || sec.section
  || E'\nPriority\: ' || pri.priority
  || E'\nFilename\: pool/' || :component_name || '/' || tmp.filename
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

ORDER BY tmp.source, tmp.package, tmp.version
"""

def generate_packages(suite_id, component_id, architecture_id, type_name):
    global _packages_query
    from daklib.filewriter import PackagesFileWriter
    from daklib.dbconn import Architecture, Component, DBConn, OverrideType, Suite
    from daklib.dakmultiprocessing import PROC_STATUS_SUCCESS

    session = DBConn().session()
    arch_all_id = session.query(Architecture).filter_by(arch_string='all').one().arch_id
    type_id = session.query(OverrideType).filter_by(overridetype=type_name).one().overridetype_id

    suite = session.query(Suite).get(suite_id)
    component = session.query(Component).get(component_id)
    architecture = session.query(Architecture).get(architecture_id)

    overridesuite_id = suite.get_overridesuite().suite_id
    include_long_description = suite.include_long_description

    # We currently filter out the "Tag" line. They are set by external
    # overrides and NOT by the maintainer. And actually having it set by
    # maintainer means we output it twice at the moment -> which breaks
    # dselect.
    metadata_skip = ["Section", "Priority", "Tag"]
    if include_long_description:
        metadata_skip.append("Description-md5")

    writer_args = {
            'archive': suite.archive.path,
            'suite': suite.suite_name,
            'component': component.component_name,
            'architecture': architecture.arch_string,
            'debtype': type_name
    }
    if suite.indices_compression is not None:
        writer_args['compression'] = suite.indices_compression
    writer = PackagesFileWriter(**writer_args)
    output = writer.open()

    r = session.execute(_packages_query, {"archive_id": suite.archive.archive_id,
        "suite": suite_id, "component": component_id, 'component_name': component.component_name,
        "arch": architecture_id, "type_id": type_id, "type_name": type_name, "arch_all": arch_all_id,
        "overridesuite": overridesuite_id, "metadata_skip": metadata_skip,
        "include_long_description": 'true' if include_long_description else 'false'})
    for (stanza,) in r:
        print >>output, stanza
        print >>output, ""

    writer.close()

    message = ["generate-packages", suite.suite_name, component.component_name, architecture.arch_string]
    session.rollback()
    return (PROC_STATUS_SUCCESS, message)

#############################################################################

_translations_query = """
WITH
  override_suite AS
    (SELECT
      s.id AS id,
      COALESCE(os.id, s.id) AS overridesuite_id
      FROM suite AS s LEFT JOIN suite AS os ON s.overridesuite = os.suite_name)

SELECT
     E'Package\: ' || b.package
  || E'\nDescription-md5\: ' || bm_description_md5.value
  || E'\nDescription-en\: ' || bm_description.value
  || E'\n'
FROM binaries b
  -- join tables for suite and component
  JOIN bin_associations ba ON b.id = ba.bin
  JOIN override_suite os ON os.id = ba.suite
  JOIN override o ON b.package = o.package AND o.suite = os.overridesuite_id AND o.type = (SELECT id FROM override_type WHERE type = 'deb')

  -- join tables for Description and Description-md5
  JOIN binaries_metadata bm_description ON b.id = bm_description.bin_id AND bm_description.key_id = (SELECT key_id FROM metadata_keys WHERE key = 'Description')
  JOIN binaries_metadata bm_description_md5 ON b.id = bm_description_md5.bin_id AND bm_description_md5.key_id = (SELECT key_id FROM metadata_keys WHERE key = 'Description-md5')

  -- we want to sort by source name
  JOIN source s ON b.source = s.id

WHERE ba.suite = :suite AND o.component = :component
GROUP BY b.package, bm_description_md5.value, bm_description.value
ORDER BY MIN(s.source), b.package, bm_description_md5.value
"""

def generate_translations(suite_id, component_id):
    global _translations_query
    from daklib.filewriter import TranslationFileWriter
    from daklib.dbconn import DBConn, Suite, Component
    from daklib.dakmultiprocessing import PROC_STATUS_SUCCESS

    session = DBConn().session()
    suite = session.query(Suite).get(suite_id)
    component = session.query(Component).get(component_id)

    writer_args = {
            'archive': suite.archive.path,
            'suite': suite.suite_name,
            'component': component.component_name,
            'language': 'en',
    }
    if suite.i18n_compression is not None:
        writer_args['compression'] = suite.i18n_compression
    writer = TranslationFileWriter(**writer_args)
    output = writer.open()

    r = session.execute(_translations_query, {"suite": suite_id, "component": component_id})
    for (stanza,) in r:
        print >>output, stanza

    writer.close()

    message = ["generate-translations", suite.suite_name, component.component_name]
    session.rollback()
    return (PROC_STATUS_SUCCESS, message)

#############################################################################

def main():
    from daklib.config import Config
    from daklib import daklog

    cnf = Config()

    Arguments = [('h',"help","Generate-Packages-Sources::Options::Help"),
                 ('a','archive','Generate-Packages-Sources::Options::Archive','HasArg'),
                 ('s',"suite","Generate-Packages-Sources::Options::Suite"),
                 ('f',"force","Generate-Packages-Sources::Options::Force"),
                 ('o','option','','ArbItem')]

    suite_names = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    try:
        Options = cnf.subtree("Generate-Packages-Sources::Options")
    except KeyError:
        Options = {}

    if Options.has_key("Help"):
        usage()

    from daklib.dakmultiprocessing import DakProcessPool, PROC_STATUS_SUCCESS, PROC_STATUS_SIGNALRAISED
    pool = DakProcessPool()

    logger = daklog.Logger('generate-packages-sources2')

    from daklib.dbconn import Component, DBConn, get_suite, Suite, Archive
    session = DBConn().session()
    session.execute("SELECT add_missing_description_md5()")
    session.commit()

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
        query = session.query(Suite).filter(Suite.untouchable == False)
        if 'Archive' in Options:
            query = query.join(Suite.archive).filter(Archive.archive_name==Options['Archive'])
        suites = query.all()

    force = Options.has_key("Force") and Options["Force"]


    def parse_results(message):
        # Split out into (code, msg)
        code, msg = message
        if code == PROC_STATUS_SUCCESS:
            logger.log([msg])
        elif code == PROC_STATUS_SIGNALRAISED:
            logger.log(['E: Subprocess recieved signal ', msg])
        else:
            logger.log(['E: ', msg])

    for s in suites:
        component_ids = [ c.component_id for c in s.components ]
        if s.untouchable and not force:
            import daklib.utils
            daklib.utils.fubar("Refusing to touch %s (untouchable and not forced)" % s.suite_name)
        for c in component_ids:
            pool.apply_async(generate_sources, [s.suite_id, c], callback=parse_results)
            if not s.include_long_description:
                pool.apply_async(generate_translations, [s.suite_id, c], callback=parse_results)
            for a in s.architectures:
                if a == 'source':
                    continue
                pool.apply_async(generate_packages, [s.suite_id, c, a.arch_id, 'deb'], callback=parse_results)
                pool.apply_async(generate_packages, [s.suite_id, c, a.arch_id, 'udeb'], callback=parse_results)

    pool.close()
    pool.join()

    # this script doesn't change the database
    session.close()

    logger.close()

    sys.exit(pool.overall_status())

if __name__ == '__main__':
    main()
