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

"""module to process policy queue uploads"""

from .config import Config
from .dbconn import Component, Override, OverrideType, Priority, Section, Suite, get_mapped_component, get_mapped_component_name
from .fstransactions import FilesystemTransaction
from .regexes import re_file_changes, re_file_safe
from .packagelist import PackageList
import daklib.utils as utils

import errno
import os
import shutil


class UploadCopy(object):
    """export a policy queue upload

    This class can be used in a with-statement::

       with UploadCopy(...) as copy:
          ...

    Doing so will provide a temporary copy of the upload in the directory
    given by the C{directory} attribute.  The copy will be removed on leaving
    the with-block.
    """

    def __init__(self, upload, group=None):
        """initializer

        @type  upload: L{daklib.dbconn.PolicyQueueUpload}
        @param upload: upload to handle
        """

        self.directory = None
        self.upload = upload
        self.group = group

    def export(self, directory, mode=None, symlink=True, ignore_existing=False):
        """export a copy of the upload

        @type  directory: str
        @param directory: directory to export to

        @type  mode: int
        @param mode: permissions to use for the copied files

        @type  symlink: bool
        @param symlink: use symlinks instead of copying the files

        @type  ignore_existing: bool
        @param ignore_existing: ignore already existing files
        """
        with FilesystemTransaction() as fs:
            source = self.upload.source
            queue = self.upload.policy_queue

            if source is not None:
                for dsc_file in source.srcfiles:
                    f = dsc_file.poolfile
                    dst = os.path.join(directory, os.path.basename(f.filename))
                    if not os.path.exists(dst) or not ignore_existing:
                        fs.copy(f.fullpath, dst, mode=mode, symlink=symlink)

            for binary in self.upload.binaries:
                f = binary.poolfile
                dst = os.path.join(directory, os.path.basename(f.filename))
                if not os.path.exists(dst) or not ignore_existing:
                    fs.copy(f.fullpath, dst, mode=mode, symlink=symlink)

            # copy byhand files
            for byhand in self.upload.byhand:
                src = os.path.join(queue.path, byhand.filename)
                dst = os.path.join(directory, byhand.filename)
                if os.path.exists(src) and (not os.path.exists(dst) or not ignore_existing):
                    fs.copy(src, dst, mode=mode, symlink=symlink)

            # copy .changes
            src = os.path.join(queue.path, self.upload.changes.changesname)
            dst = os.path.join(directory, self.upload.changes.changesname)
            if not os.path.exists(dst) or not ignore_existing:
                fs.copy(src, dst, mode=mode, symlink=symlink)

    def __enter__(self):
        assert self.directory is None

        mode = 0o0700
        symlink = True
        if self.group is not None:
            mode = 0o2750
            symlink = False

        cnf = Config()
        self.directory = utils.temp_dirname(parent=cnf.get('Dir::TempPath'),
                                            mode=mode,
                                            group=self.group)
        self.export(self.directory, symlink=symlink)
        return self

    def __exit__(self, *args):
        if self.directory is not None:
            shutil.rmtree(self.directory)
            self.directory = None
        return None


class PolicyQueueUploadHandler(object):
    """process uploads to policy queues

    This class allows to accept or reject uploads and to get a list of missing
    overrides (for NEW processing).
    """

    def __init__(self, upload, session):
        """initializer

        @type  upload: L{daklib.dbconn.PolicyQueueUpload}
        @param upload: upload to process

        @param session: database session
        """
        self.upload = upload
        self.session = session

    @property
    def _overridesuite(self):
        overridesuite = self.upload.target_suite
        if overridesuite.overridesuite is not None:
            overridesuite = self.session.query(Suite).filter_by(suite_name=overridesuite.overridesuite).one()
        return overridesuite

    def _source_override(self, component_name):
        package = self.upload.source.source
        suite = self._overridesuite
        component = get_mapped_component(component_name, self.session)
        query = self.session.query(Override).filter_by(package=package, suite=suite) \
            .join(OverrideType).filter(OverrideType.overridetype == 'dsc') \
            .filter(Override.component == component)
        return query.first()

    def _binary_override(self, name, binarytype, component_name):
        suite = self._overridesuite
        component = get_mapped_component(component_name, self.session)
        query = self.session.query(Override).filter_by(package=name, suite=suite) \
            .join(OverrideType).filter(OverrideType.overridetype == binarytype) \
            .filter(Override.component == component)
        return query.first()

    @property
    def _changes_prefix(self):
        changesname = self.upload.changes.changesname
        assert changesname.endswith('.changes')
        assert re_file_changes.match(changesname)
        return changesname[0:-8]

    def accept(self):
        """mark upload as accepted"""
        assert len(self.missing_overrides()) == 0

        fn1 = 'ACCEPT.{0}'.format(self._changes_prefix)
        fn = os.path.join(self.upload.policy_queue.path, 'COMMENTS', fn1)
        try:
            fh = os.open(fn, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fh, 'wt') as f:
                f.write('OK\n')
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                raise

    def reject(self, reason):
        """mark upload as rejected

        @type  reason: str
        @param reason: reason for the rejection
        """
        cnf = Config()

        fn1 = 'REJECT.{0}'.format(self._changes_prefix)
        assert re_file_safe.match(fn1)

        fn = os.path.join(self.upload.policy_queue.path, 'COMMENTS', fn1)
        try:
            fh = os.open(fn, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fh, 'wt') as f:
                f.write('NOTOK\n')
                f.write('From: {0} <{1}>\n\n'.format(utils.whoami(), cnf['Dinstall::MyAdminAddress']))
                f.write(reason)
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                raise

    def get_action(self):
        """get current action

        @rtype:  str
        @return: string giving the current action, one of 'ACCEPT', 'ACCEPTED', 'REJECT'
        """
        changes_prefix = self._changes_prefix

        for action in ('ACCEPT', 'ACCEPTED', 'REJECT'):
            fn1 = '{0}.{1}'.format(action, changes_prefix)
            fn = os.path.join(self.upload.policy_queue.path, 'COMMENTS', fn1)
            if os.path.exists(fn):
                return action

        return None

    def missing_overrides(self, hints=None):
        """get missing override entries for the upload

        @type  hints: list of dict
        @param hints: suggested hints for new overrides in the same format as
                      the return value

        @return: list of dicts with the following keys:

                 - package: package name
                 - priority: default priority (from upload)
                 - section: default section (from upload)
                 - component: default component (from upload)
                 - type: type of required override ('dsc', 'deb' or 'udeb')

                 All values are strings.
        """
        # TODO: use Package-List field
        missing = []
        components = set()

        source = self.upload.source

        if hints is None:
            hints = []
        hints_map = dict([((o['type'], o['package']), o) for o in hints])

        def check_override(name, type, priority, section, included):
            component = 'main'
            if section.find('/') != -1:
                component = section.split('/', 1)[0]
            override = self._binary_override(name, type, component)
            if override is None and not any(o['package'] == name and o['type'] == type for o in missing):
                hint = hints_map.get((type, name))
                if hint is not None:
                    missing.append(hint)
                    component = hint['component']
                else:
                    missing.append(dict(
                            package=name,
                            priority=priority,
                            section=section,
                            component=component,
                            type=type,
                            included=included
                            ))
            components.add(component)

        for binary in self.upload.binaries:
            binary_proxy = binary.proxy
            priority = binary_proxy['Priority']
            section = binary_proxy['Section']
            check_override(binary.package, binary.binarytype, priority, section, included=True)

        if source is not None:
            source_proxy = source.proxy
            package_list = PackageList(source_proxy)
            if not package_list.fallback:
                packages = package_list.packages_for_suite(self.upload.target_suite)
                for p in packages:
                    check_override(p.name, p.type, p.priority, p.section, included=False)

            # see daklib.archive.source_component_from_package_list
            # which we cannot use here as we might not have a Package-List
            # field for old packages
            mapped_components = [get_mapped_component_name(c) for c in components]
            query = self.session.query(Component).order_by(Component.ordering) \
                    .filter(Component.component_name.in_(mapped_components))
            source_component = query.first().component_name

            override = self._source_override(source_component)
            if override is None:
                hint = hints_map.get(('dsc', source.source))
                if hint is not None:
                    missing.append(hint)
                else:
                    section = 'misc'
                    if source_component != 'main':
                        section = "{0}/{1}".format(source_component, section)
                    missing.append(dict(
                            package=source.source,
                            priority='extra',
                            section=section,
                            component=source_component,
                            type='dsc',
                            included=True,
                            ))

        return missing

    def add_overrides(self, new_overrides, suite):
        if suite.overridesuite is not None:
            suite = self.session.query(Suite).filter_by(suite_name=suite.overridesuite).one()

        for override in new_overrides:
            package = override['package']
            priority = self.session.query(Priority).filter_by(priority=override['priority']).first()
            section = self.session.query(Section).filter_by(section=override['section']).first()
            component = get_mapped_component(override['component'], self.session)
            overridetype = self.session.query(OverrideType).filter_by(overridetype=override['type']).one()

            if priority is None:
                raise Exception('Invalid priority {0} for package {1}'.format(priority, package))
            if section is None:
                raise Exception('Invalid section {0} for package {1}'.format(section, package))
            if component is None:
                raise Exception('Invalid component {0} for package {1}'.format(component, package))

            o = Override(package=package, suite=suite, component=component, priority=priority, section=section, overridetype=overridetype)
            self.session.add(o)

        self.session.commit()
