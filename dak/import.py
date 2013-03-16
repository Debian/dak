#! /usr/bin/env python
#
# Copyright (C) 2012, Ansgar Burchardt <ansgar@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import apt_pkg
import os
import sys

from daklib.dbconn import *
import daklib.archive
import daklib.config
import daklib.daklog
import daklib.upload
import daklib.regexes

def usage():
    print """Usage:

dak import <suite> <component> <files...>
dak import -D|--dump <file> <suite> <component>
dak import -E|--export-dump <suite> <component>

WARNING: This command does no sanity checks. Only use it on trusted packages.

Options:
  -h, --help:             show this help message
  -a, --add-overrides:    add missing overrides automatically
  -c, --changed-by:       Changed-By for imported source packages
                          (default: maintainer)
  -D, --dump <file>:      Import all files listed in <file>. The format
                          is described below.
  -E, --export-dump:      Export list of files in the format required
                          by dak import --dump.
  -s, --ignore-signature: ignore signature for imported source packages

File format used by --dump:

  <filename>:<md5>:<sha1>:<sha256>:[<fingerprint>]:[<changed-by>]
"""

def import_source(log, transaction, suite, component, directory, hashed_file,
                  fingerprint=None, changed_by=None,
                  keyrings=None, require_signature=True, add_overrides=False):
    if keyrings is None:
        keyrings = []
    filename = hashed_file.filename
    session = transaction.session

    source = daklib.upload.Source(directory, [hashed_file], keyrings, require_signature)
    if source.valid_signature:
        fingerprint = session.query(Fingerprint).filter_by(fingerprint=source.primary_fingerprint).first()
    if changed_by is None:
        changed_by = source.dsc['Maintainer']
    db_changed_by = get_or_set_maintainer(changed_by, session)

    transaction.install_source(directory, source, suite, component, db_changed_by, fingerprint=fingerprint)
    log.log(['import-source', suite.suite_name, component.component_name, filename])

    if add_overrides and not session.query(Override).filter_by(suite=suite.get_overridesuite(), component=component, package=source.dsc['Source']).join(OverrideType).filter(OverrideType.overridetype == 'dsc').first():
        overridetype = session.query(OverrideType).filter_by(overridetype='dsc').one()
        overridesuite = suite.get_overridesuite()
        section_name = 'misc'
        if component.component_name != 'main':
            section_name = "{0}/{1}".format(component.component_name, section_name)
        section = session.query(Section).filter_by(section=section_name).one()
        priority = session.query(Priority).filter_by(priority='extra').one()

        override = Override(package=source.dsc['Source'], suite=overridesuite, component=component,
                            section=section, priority=priority, overridetype=overridetype)
        session.add(override)
        log.log(['add-source-override', suite.suite_name, component.component_name, source.dsc['Source'], section.section, priority.priority])

def import_binary(log, transaction, suite, component, directory, hashed_file, fingerprint=None, add_overrides=False):
    filename = hashed_file.filename
    session = transaction.session

    binary = daklib.upload.Binary(directory, hashed_file)
    transaction.install_binary(directory, binary, suite, component, fingerprint=fingerprint)
    log.log(['import-binary', suite.suite_name, component.component_name, filename])

    if add_overrides and not session.query(Override).filter_by(suite=suite.get_overridesuite(), component=component, package=binary.control['Package']).join(OverrideType).filter(OverrideType.overridetype == binary.type).first():
        overridetype = session.query(OverrideType).filter_by(overridetype=binary.type).one()
        overridesuite = suite.get_overridesuite()
        section = session.query(Section).filter_by(section=binary.control['Section']).one()
        priority = session.query(Priority).filter_by(priority=binary.control['Priority']).one()

        override = Override(package=binary.control['Package'], suite=overridesuite, component=component,
                            section=section, priority=priority, overridetype=overridetype)
        session.add(override)
        log.log(['add-binary-override', suite.suite_name, component.component_name, binary.control['Package'], section.section, priority.priority])

def import_file(log, transaction, suite, component, directory, hashed_file,
                fingerprint=None, changed_by=None, keyrings=None, require_signature=True,
                add_overrides = False):
    filename = hashed_file.filename
    if daklib.regexes.re_file_binary.match(filename):
        import_binary(log, transaction, suite, component, directory, hashed_file,
                      fingerprint=fingerprint, add_overrides=add_overrides)
    elif daklib.regexes.re_file_dsc.match(filename):
        import_source(log, transaction, suite, component, directory, hashed_file,
                      fingerprint=fingerprint, changed_by=changed_by, keyrings=keyrings,
                      require_signature=require_signature, add_overrides=add_overrides)
    else:
        raise Exception('File is neither source nor binary package: {0}'.format(filename))

def import_dump(log, transaction, suite, component, fh,
                keyrings=None, require_signature=True, add_overrides=False):
    session = transaction.session
    for line in fh:
        path, size, md5, sha1, sha256, fpr, changed_by = line.strip().split(':', 6)

        if not changed_by:
            changed_by = None
        fingerprint = None
        if fpr:
            fingerprint = session.query(Fingerprint).filter_by(fingerprint=fpr).first()
            if fingerprint is None:
                print 'W: {0}: unknown fingerprint {1}'.format(filename, fpr)

        directory, filename = os.path.split(os.path.abspath(path))
        hashed_file = daklib.upload.HashedFile(filename, long(size), md5, sha1, sha256)
        hashed_file.check(directory)

        import_file(log, transaction, suite, component, directory, hashed_file,
                    fingerprint=fingerprint, changed_by=changed_by,
                    keyrings=keyrings, require_signature=require_signature, add_overrides=add_overrides)

        transaction.commit()

_export_query = r"""
WITH
tmp AS
  (SELECT 1 AS order, s.file AS file_id, s.sig_fpr AS fingerprint_id, s.changedby AS changed_by, sa.suite AS suite_id
     FROM source s
     JOIN src_associations sa ON sa.source = s.id
   UNION
   SELECT 2 AS order, b.file AS file_id, b.sig_fpr AS fingerprint_id, NULL, ba.suite AS suite_id
     FROM binaries b
     JOIN bin_associations ba ON ba.bin = b.id
  )

SELECT
  f.filename, f.size::TEXT, f.md5sum, f.sha1sum, f.sha256sum, COALESCE(fpr.fingerprint, ''), COALESCE(m.name, '')
FROM files f
JOIN tmp ON f.id = tmp.file_id
JOIN suite ON suite.id = tmp.suite_id
JOIN files_archive_map fam ON fam.file_id = f.id AND fam.archive_id = suite.archive_id
LEFT JOIN fingerprint fpr ON fpr.id = tmp.fingerprint_id
LEFT JOIN maintainer m ON m.id = tmp.changed_by

WHERE
  suite.id = :suite_id
  AND fam.component_id = :component_id

ORDER BY tmp.order, f.filename;
"""

def export_dump(transaction, suite, component):
    session = transaction.session
    query = session.execute(_export_query,
                            {'suite_id': suite.suite_id,
                             'component_id': component.component_id})
    for row in query:
        print ":".join(row)

def main(argv=None):
    if argv is None:
        argv = sys.argv

    arguments = [
        ('h', 'help', 'Import::Options::Help'),
        ('a', 'add-overrides', 'Import::Options::AddOverrides'),
        ('c', 'changed-by', 'Import::Options::ChangedBy', 'HasArg'),
        ('D', 'dump', 'Import::Options::Dump', 'HasArg'),
        ('E', 'export-dump', 'Import::Options::Export'),
        ('s', 'ignore-signature', 'Import::Options::IgnoreSignature'),
        ]

    cnf = daklib.config.Config()
    cnf['Import::Options::Dummy'] = ''
    argv = apt_pkg.parse_commandline(cnf.Cnf, arguments, argv)
    options = cnf.subtree('Import::Options')

    if 'Help' in options or len(argv) < 2:
        usage()
        sys.exit(0)

    suite_name = argv[0]
    component_name = argv[1]

    add_overrides = options.find_b('AddOverrides')
    require_signature = not options.find_b('IgnoreSignature')
    changed_by = options.find('ChangedBy') or None

    log = daklib.daklog.Logger('import')

    with daklib.archive.ArchiveTransaction() as transaction:
        session = transaction.session
        suite = session.query(Suite).filter_by(suite_name=suite_name).one()
        component = session.query(Component).filter_by(component_name=component_name).one()
        keyrings = session.query(Keyring).filter_by(active=True).order_by(Keyring.priority)
        keyring_files = [ k.keyring_name for k in keyrings ]

        dump = options.find('Dump') or None
        if options.find_b('Export'):
            export_dump(transaction, suite, component)
            transaction.rollback()
        elif dump is not None:
            with open(dump, 'r') as fh:
                import_dump(log, transaction, suite, component, fh, keyring_files,
                            require_signature=require_signature, add_overrides=add_overrides)
            transaction.commit()
        else:
            files = argv[2:]
            for f in files:
                directory, filename = os.path.split(os.path.abspath(f))
                hashed_file = daklib.upload.HashedFile.from_file(directory, filename)
                import_file(log, transaction, suite, component, directory, hashed_file,
                            changed_by=changed_by,
                            keyrings=keyring_files, require_signature=require_signature,
                            add_overrides=add_overrides)
            transaction.commit()

    log.close()

if __name__ == '__main__':
    main()
