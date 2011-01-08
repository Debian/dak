#!/usr/bin/env python

from daklib.config import Config

import glob, os.path, re, shutil

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
            shutil.copytree(source, dest)
        for source, dest in self.symlinks_to_create:
            if os.path.lexists(dest):
                os.unlink(dest)
            os.symlink(source, dest)
