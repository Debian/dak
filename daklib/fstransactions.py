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

"""Transactions for filesystem actions
"""

import errno
import os
import shutil

class _FilesystemAction(object):
    @property
    def temporary_name(self):
        raise NotImplementedError()

    def check_for_temporary(self):
        try:
            if os.path.exists(self.temporary_name):
                raise IOError("Temporary file '{0}' already exists.".format(self.temporary_name))
        except NotImplementedError:
            pass

class _FilesystemCopyAction(_FilesystemAction):
    def __init__(self, source, destination, link=True, symlink=False, mode=None):
        self.destination = destination
        self.need_cleanup = False

        self.check_for_temporary()
        destdir = os.path.dirname(self.destination)
        if not os.path.exists(destdir):
            os.makedirs(destdir, 0o2775)
        if symlink:
            os.symlink(source, self.destination)
        elif link:
            try:
                os.link(source, self.destination)
            except OSError:
                shutil.copy2(source, self.destination)
        else:
            shutil.copy2(source, self.destination)

        self.need_cleanup = True
        if mode is not None:
            os.chmod(self.destination, mode)

    @property
    def temporary_name(self):
        return self.destination

    def commit(self):
        pass

    def rollback(self):
        if self.need_cleanup:
            os.unlink(self.destination)
            self.need_cleanup = False

class _FilesystemUnlinkAction(_FilesystemAction):
    def __init__(self, path):
        self.path = path
        self.need_cleanup = False

        self.check_for_temporary()
        os.rename(self.path, self.temporary_name)
        self.need_cleanup = True

    @property
    def temporary_name(self):
        return "{0}.dak-rm".format(self.path)

    def commit(self):
        if self.need_cleanup:
            os.unlink(self.temporary_name)
            self.need_cleanup = False

    def rollback(self):
        if self.need_cleanup:
            os.rename(self.temporary_name, self.path)
            self.need_cleanup = False

class _FilesystemCreateAction(_FilesystemAction):
    def __init__(self, path):
        self.path = path
        self.need_cleanup = True

    @property
    def temporary_name(self):
        return self.path

    def commit(self):
        pass

    def rollback(self):
        if self.need_cleanup:
            os.unlink(self.path)
            self.need_cleanup = False

class FilesystemTransaction(object):
    """transactions for filesystem actions"""
    def __init__(self):
        self.actions = []

    def copy(self, source, destination, link=True, symlink=False, mode=None):
        """copy `source` to `destination`

        Args:
           source (str): source file
           destination (str): destination file

        Kwargs:
           link (bool): Try hardlinking, falling back to copying.
           symlink (bool): Create a symlink instead
           mode (int): Permissions to change `destination` to.
        """
        self.actions.append(_FilesystemCopyAction(source, destination, link=link, symlink=symlink, mode=mode))

    def move(self, source, destination, mode=None):
        """move `source` to `destination`

        Args:
           source (str): source file
           destination (str): destination file

        Kwargs:
           mode (int): Permissions to change `destination` to.
        """
        self.copy(source, destination, link=True, mode=mode)
        self.unlink(source)

    def unlink(self, path):
        """unlink `path`

        Args:
           path (str): file to unlink
        """
        self.actions.append(_FilesystemUnlinkAction(path))

    def create(self, path, mode=None):
        """create `filename` and return file handle

        Args:
           filename (str): file to create

        Kwargs:
           mode (int): Permissions for the new file

        Returns:
           file handle of the new file
        """
        destdir = os.path.dirname(path)
        if not os.path.exists(destdir):
            os.makedirs(destdir, 0o2775)
        if os.path.exists(path):
            raise IOError("File '{0}' already exists.".format(path))
        fh = open(path, 'w')
        self.actions.append(_FilesystemCreateAction(path))
        if mode is not None:
            os.chmod(path, mode)
        return fh

    def commit(self):
        """Commit all recorded actions."""
        try:
            for action in self.actions:
                action.commit()
        except:
            self.rollback()
            raise
        finally:
            self.actions = []

    def rollback(self):
        """Undo all recorded actions."""
        try:
            for action in self.actions:
                action.rollback()
        finally:
            self.actions = []

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if type is None:
            self.commit()
        else:
            self.rollback()
        return None
