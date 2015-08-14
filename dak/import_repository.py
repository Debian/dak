#! /usr/bin/env python
#
# Copyright (C) 2015, Ansgar Burchardt <ansgar@debian.org>
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

from __future__ import print_function

import daklib.archive
import daklib.config
import daklib.dbconn
import daklib.import_repository
import daklib.utils

import apt_pkg
import sys

from collections import defaultdict

def usage(status=0):
    print("""
dak import-repository
  --keyring=/usr/share/keyring/debian-archive-keyring.gpg
  [--key=${fingerprint}]
  [--architectures=a,b,c (default: architectures in origin suite)]
  [--components=main,contrib (default: components in origin suite)]
  [--target-suite=${suite} (default: origin suite name)]
  [--add-overrides]
  [--max-packages=${n} (import at maximum ${n} packages, default: no limit)]
  http://httpredir.debian.org/debian unstable

Things to think about:
 - Import Built-Using sources
   - all / only referenced
 - Remove old packages:
   - by-source: remove source X_v, if no X exists upstream
   - by-version: remove source X_v, if no X_v exists upstream
   (X denotes package name, v version, X_v package at a specific version)
 - Import all or only newest?
 - Expire binary packages?
""")
    sys.exit(status)

def entry_is_newer(entry, packages):
    version = entry['Version']
    for p in packages[entry['Package']]:
        if apt_pkg.version_compare(version, p.version) <= 0:
            return False
    return True

def entry_in_packages(entry, packages):
    return entry['Package'] in packages

def get_packages_in_suite(suite):
    sources = defaultdict(list)
    for s in suite.sources:
        sources[s.source].append(s)

    packages = defaultdict(list)
    for b in suite.binaries:
        packages[b.package].append(b)

    return sources, packages

def import_sources(base, sources, transaction, target_suite, component, target_sources, extra_sources, extra_sources_comp, max_packages=None):
    n = 0
    for entry in sources:
        if max_packages is not None and n > max_packages:
            break
        if entry.get('Extra-Source-Only', 'no') == 'yes':
            # Remember package, we might need to import it later.
            key = (entry['Package'], entry['Version'])
            extra_sources[key] = entry
            extra_sources_comp[key].add(c)
            continue
        if not entry_in_packages(entry, target_sources) or entry_is_newer(entry, target_sources):
            print("Importing {0}={1}".format(entry['Package'], entry['Version']))
            daklib.import_repository.import_source_to_suite(base, entry, transaction, target_suite, component)
            n += 1
            #transaction.commit()
    return n

def import_built_using(base, source, version, transaction, target_suite, component, extra_sources, extra_sources_comp):
    if not daklib.import_repository.source_in_archive(bu_source, bu_version, target_suite.archive):
        print("Importing extra source {0}={1}".format(bu_source, bu_version))
        key = (bu_source, bu_version)
        extra_entry = extra_sources.get(key)
        if extra_entry is None:
            raise Exception("Extra source {0}={1} referenced by {2}={3} ({4}) not found in source suite.".format(bu_source, bu_version, entry['Package'], entry['Version'], architecture))
        extra_components = extra_sources_comp[key]
        if c in components:
            extra_component = component
        else:
            # TODO: Take preferred components from those listed...
            raise Exception("Not implemented.")
        daklib.import_repository.import_source_to_suite(base, extra_entry, transaction, target_suite, extra_component)

def import_packages(base, packages, transaction, target_suite, component, architecture, target_binaries, extra_sources, extra_sources_comp, max_packages=None):
    n = 0
    for entry in packages:
        if max_packages is not None and n > max_packages:
            break
        if not entry_in_packages(entry, target_binaries) or entry_is_newer(entry, target_binaries):
            print("Importing {0}={1} ({2})".format(entry['Package'], entry['Version'], architecture))
            # Import Built-Using sources:
            for bu_source, bu_version in daklib.utils.parse_built_using(entry):
                import_built_using(base, bu_source, bu_version, transaction, target_suite, component, extra_sources, extra_sources_comp)
            # Import binary:
            daklib.import_repository.import_package_to_suite(base, entry, transaction, target_suite, component)
            n += 1
            #transaction.commit()
    return n

def main(argv=None):
    if argv is None:
        argv = sys.argv

    arguments = [
        ('h', 'help', 'Import-Repository::Help'),
        ('k', 'keyring', 'Import-Repository::Keyring', 'HasArg'),
        ('K', 'key', 'Import-Repository::Key', 'HasArg'),
        ('a', 'architectures', 'Import-Repository::Architectures', 'HasArg'),
        ('c', 'components', 'Import-Repository::Components', 'HasArg'),
        ('t', 'target-suite', 'Import-Repository::Target-Suite', 'HasArg'),
        ('A', 'add-overrides', 'Import-Repository::AddOverrides'),
        ('n', 'max-packages', 'Import-Repository::MaxPackages', 'HasArg'),
        ]

    cnf = daklib.config.Config();
    argv = apt_pkg.parse_commandline(cnf.Cnf, arguments, argv)
    options = cnf.subtree('Import-Repository')

    if 'Help' in options or len(argv) < 2:
        usage(0)

    keyring = options.find('Keyring') or None
    if keyring is None:
        print("Error: No keyring specified")
        print()

    if 'Key' in options:
        raise Exception('Not implemented.')

    if 'AddOverrides' in options:
        raise Exception('Not implemented.')

    if 'MaxPackages' in options:
        max_packages = long(options['MaxPackages'])
    else:
        max_packages = None

    base, suite = argv[0:2]

    target_suite_name = options.find('Target-Suite') or suite

    print("Importing packages from {0}/dists/{1} to {2}".format(base, suite, target_suite_name))
    with daklib.archive.ArchiveTransaction() as transaction:
        target_suite = daklib.dbconn.get_suite(target_suite_name, transaction.session)
        if target_suite is None:
            daklib.utils.fubar("Target suite '{0}' is unknown.".format(target_suite_name))

        release = daklib.import_repository.obtain_release(base, suite, keyring)
        target_sources, target_binaries = get_packages_in_suite(target_suite)

        if 'Architectures' in options:
            architectures = options['Architectures'].split(',')
        else:
            architectures = ['all'] + release.architectures()

        if 'Components' in options:
            components = options['Components'].split(',')
        else:
            components = release.components()

        # TODO: Clean this up...

        n = 0

        # For Extra-Source-Only sources packages, keep a dict
        # (name, version) -> entry and (name, version) -> set of components
        # to allow importing needed packages at a later stage
        extra_sources = dict()
        extra_sources_comp = defaultdict(set)

        for c in components:
            component = daklib.dbconn.get_component(c, transaction.session)
            print("Processing {0}/source...".format(c))
            sources = release.sources(c)
            imported = import_sources(base, sources, transaction, target_suite, component, target_sources, extra_sources, extra_sources_comp, max_packages)
            print("  imported {0} source packages".format(imported))
            n += imported
            if max_packages is not None:
                max_packages -= n

        for c in components:
            component = daklib.dbconn.get_component(c, transaction.session)
            for architecture in architectures:
                print("Processing {0}/{1}...".format(c, architecture))
                packages = release.packages(c, architecture)
                imported = import_packages(base, packages, transaction, target_suite, component, architecture, target_binaries, extra_sources, extra_sources_comp, max_packages)
                print("  imported {0} binary packages".format(imported))
                n += imported
                if max_packages is not None:
                    max_packages -= n

        transaction.rollback()

if __name__ == '__main__':
    main()
