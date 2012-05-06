#!/usr/bin/env python

""" Copies the installer from one suite to another """
# Copyright (C) 2011  Torsten Werner <twerner@debian.org>

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

from daklib.config import Config

import apt_pkg, glob, os.path, re, shutil, sys

def usage(exit_code = 0):
    print """Usage: dak copy-installer [OPTION]... VERSION
  -h, --help         show this help and exit
  -s, --source       source suite      (defaults to unstable)
  -d, --destination  destination suite (defaults to testing)
  -n, --no-action    don't change anything

Exactly 1 version must be specified."""
    sys.exit(exit_code)

def main():
    cnf = Config()
    Arguments = [
            ('h', "help",        "Copy-Installer::Options::Help"),
            ('s', "source",      "Copy-Installer::Options::Source",      "HasArg"),
            ('d', "destination", "Copy-Installer::Options::Destination", "HasArg"),
            ('n', "no-action",   "Copy-Installer::Options::No-Action"),
            ]
    for option in [ "help", "source", "destination", "no-action" ]:
        if not cnf.has_key("Copy-Installer::Options::%s" % (option)):
            cnf["Copy-Installer::Options::%s" % (option)] = ""
    extra_arguments = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Copy-Installer::Options")

    if Options["Help"]:
        usage()
    if len(extra_arguments) != 1:
        usage(1)

    initializer = { "version": extra_arguments[0] }
    if Options["Source"] != "":
        initializer["source"] = Options["Source"]
    if Options["Destination"] != "":
        initializer["dest"] = Options["Destination"]

    copier = InstallerCopier(**initializer)
    print copier.get_message()
    if Options["No-Action"]:
        print 'Do nothing because --no-action has been set.'
    else:
        copier.do_copy()
        print 'Installer has been copied successfully.'

root_dir = Config()['Dir::Root']

class InstallerCopier:
    def __init__(self, source = 'unstable', dest = 'testing',
            **keywords):
        self.source = source
        self.dest = dest
        if 'version' not in keywords:
            raise KeyError('no version specified')
        self.version = keywords['version']

        self.source_dir = os.path.join(root_dir, 'dists', source, 'main')
        self.dest_dir = os.path.join(root_dir, 'dists', dest, 'main')
        self.check_dir(self.source_dir, 'source does not exist')
        self.check_dir(self.dest_dir, 'destination does not exist')

        self.architectures = []
        self.skip_architectures = []
        self.trees_to_copy = []
        self.symlinks_to_create = []
        arch_pattern = os.path.join(self.source_dir, 'installer-*', self.version)
        for arch_dir in glob.glob(arch_pattern):
            self.check_architecture(arch_dir)

    def check_dir(self, dir, message):
        if not os.path.isdir(dir):
            raise IOError(message)

    def check_architecture(self, arch_dir):
        architecture = re.sub('.*?/installer-(.*?)/.*', r'\1', arch_dir)
        dest_basedir = os.path.join(self.dest_dir, \
            'installer-%s' % architecture)
        dest_dir = os.path.join(dest_basedir, self.version)
        if os.path.isdir(dest_dir):
            self.skip_architectures.append(architecture)
        else:
            self.architectures.append(architecture)
            self.trees_to_copy.append((arch_dir, dest_dir))
            symlink_target = os.path.join(dest_basedir, 'current')
            self.symlinks_to_create.append((self.version, symlink_target))

    def get_message(self):
        return """
Will copy installer version %(version)s from suite %(source)s to
%(dest)s.
Architectures to copy: %(arch_list)s
Architectures to skip: %(skip_arch_list)s""" % {
            'version':        self.version,
            'source':         self.source,
            'dest':           self.dest,
            'arch_list':      ', '.join(self.architectures),
            'skip_arch_list': ', '.join(self.skip_architectures)}

    def do_copy(self):
        for source, dest in self.trees_to_copy:
            shutil.copytree(source, dest, symlinks=True)
        for source, dest in self.symlinks_to_create:
            if os.path.lexists(dest):
                os.unlink(dest)
            os.symlink(source, dest)


if __name__ == '__main__':
    main()
