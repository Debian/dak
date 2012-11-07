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
import daklib.upload
import daklib.regexes

def usage():
    print """Usage:

dak import <suite> <component> <files...>

Options:
  -h, --help:             show this help message
  -a, --add-overrides:    add missing overrides automatically
  -c, --changed-by:       Changed-By for imported source packages
                          (default: maintainer)
  -s, --ignore-signature: ignore signature for imported source packages

WARNING: This command does no sanity checks. Only use it on trusted packages.
"""

def import_source(transaction, suite, component, directory, filename,
                  changed_by=None, keyrings=None, require_signature=True,
                  add_overrides=False):
    if keyrings is None:
        keyrings = []
    session = transaction.session

    source = daklib.upload.Source.from_file(directory, filename, keyrings, require_signature)
    fingerprint = None
    if source.valid_signature:
        fingerprint = session.query(Fingerprint).filter_by(fingerprint=source.primary_fingerprint).one()
    if changed_by is None:
        changed_by = source.dsc['Maintainer']
    db_changed_by = get_or_set_maintainer(changed_by, session)

    transaction.install_source(directory, source, suite, component, db_changed_by, fingerprint=fingerprint)

    if add_overrides and not session.query(Override).filter_by(suite=suite.get_overridesuite(), component=component, package=source.dsc['Source']).join(OverrideType).filter(OverrideType.overridetype == 'dsc').first():
        overridetype = session.query(OverrideType).filter_by(overridetype='dsc').one()
        overridesuite = suite.get_overridesuite()
        section_name = 'misc'
        if component.component_name != 'main':
            section_name = "{0}/{1}".format(component.component_name, section_name)
        section = session.query(Section).filter_by(section=section).one()
        priority = session.query(Priority).filter_by(priority='extra').one()

        override = Override(package=control.dsc['Source'], suite=overridesuite, component=component,
                            section=section, priority=priority, overridetype=overridetype)
        session.add(override)

def import_binary(transaction, suite, component, directory, filename, add_overrides=False):
    session = transaction.session

    binary = daklib.upload.Binary.from_file(directory, filename)
    transaction.install_binary(directory, binary, suite, component)

    if add_overrides and not session.query(Override).filter_by(suite=suite.get_overridesuite(), component=component, package=binary.control['Package']).join(OverrideType).filter(OverrideType.overridetype == binary.type).first():
        overridetype = session.query(OverrideType).filter_by(overridetype=binary.type).one()
        overridesuite = suite.get_overridesuite()
        section = session.query(Section).filter_by(section=binary.control['Section']).one()
        priority = session.query(Priority).filter_by(priority=binary.control['Priority']).one()

        override = Override(package=binary.control['Package'], suite=overridesuite, component=component,
                            section=section, priority=priority, overridetype=overridetype)
        session.add(override)

def import_file(transaction, suite, component, directory, filename,
                changed_by=None, keyrings=None, require_signature=False,
                add_overrides = False):
    if keyrings is None:
        keyrings = []

    if daklib.regexes.re_file_binary.match(filename):
        import_binary(transaction, suite, component, directory, filename, add_overrides)
    elif daklib.regexes.re_file_dsc.match(filename):
        import_source(transaction, suite, component, directory, filename,
                      changed_by=changed_by, keyrings=keyrings,
                      require_signature=require_signature, add_overrides=add_overrides)
    else:
        raise Exception('File is neither source nor binary package: {0}'.format(filename))

def main(argv=None):
    if argv is None:
        argv = sys.argv

    arguments = [
        ('h', 'help', 'Import::Options::Help'),
        ('a', 'add-overrides', 'Import::Options::AddOverrides'),
        ('c', 'changed-by', 'Import::Options::ChangedBy', 'HasArg'),
        ('s', 'ignore-signature', 'Import::Options::IgnoreSignature'),
        ]

    cnf = daklib.config.Config()
    cnf['Import::Options::Dummy'] = ''
    argv = apt_pkg.parse_commandline(cnf.Cnf, arguments, argv)
    options = cnf.subtree('Import::Options')

    if 'Help' in options or len(argv) < 3:
        usage()
        sys.exit(0)

    suite_name = argv[0]
    component_name = argv[1]
    files = argv[2:]

    add_overrides = options.find_b('AddOverrides')
    require_signature = not options.find_b('IgnoreSignature')
    changed_by = options.find('ChangedBy') or None

    with daklib.archive.ArchiveTransaction() as transaction:
        session = transaction.session
        suite = session.query(Suite).filter_by(suite_name=suite_name).one()
        component = session.query(Component).filter_by(component_name=component_name).one()
        keyrings = session.query(Keyring).filter_by(active=True).order_by(Keyring.priority)
        keyring_files = [ k.keyring_name for k in keyrings ]

        for f in files:
            directory, filename = os.path.split(os.path.abspath(f))
            import_file(transaction, suite, component, directory, filename,
                        changed_by=changed_by,
                        keyrings=keyring_files, require_signature=require_signature,
                        add_overrides=add_overrides)

        transaction.commit()

if __name__ == '__main__':
    main()
