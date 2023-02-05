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
from typing import IO, Optional


class _FilesystemAction:
    @property
    def temporary_name(self) -> str:
        raise NotImplementedError()

    def check_for_temporary(self) -> None:
        try:
            if os.path.exists(self.temporary_name):
                raise OSError(errno.EEXIST, os.strerror(errno.EEXIST), self.temporary_name)
        except NotImplementedError:
            pass


class _FilesystemCopyAction(_FilesystemAction):
    def __init__(self, source, destination, link=True, symlink=False, mode=None):
        self.destination = destination
        self.need_cleanup = False

        dirmode = 0o2755
        if mode is not None:
            dirmode = 0o2700 | mode
            # Allow +x for group and others if they have +r.
            if dirmode & 0o0040:
                dirmode = dirmode | 0o0010
            if dirmode & 0o0004:
                dirmode = dirmode | 0o0001

        self.check_for_temporary()
        destdir = os.path.dirname(self.destination)
        if not os.path.exists(destdir):
            os.makedirs(destdir, dirmode)
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
    def __init__(self, path: str):
        self.path: str = path
        self.need_cleanup: bool = False

        self.check_for_temporary()
        os.rename(self.path, self.temporary_name)
        self.need_cleanup: bool = True

    @property
    def temporary_name(self) -> str:
        return "{0}.dak-rm".format(self.path)

    def commit(self) -> None:
        if self.need_cleanup:
            os.unlink(self.temporary_name)
            self.need_cleanup = False

    def rollback(self) -> None:
        if self.need_cleanup:
            os.rename(self.temporary_name, self.path)
            self.need_cleanup = False


class _FilesystemCreateAction(_FilesystemAction):
    def __init__(self, path: str):
        self.path: str = path
        self.need_cleanup: bool = True

    @property
    def temporary_name(self) -> str:
        return self.path

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        if self.need_cleanup:
            os.unlink(self.path)
            self.need_cleanup = False


class FilesystemTransaction:
    """transactions for filesystem actions"""

    def __init__(self):
        self.actions = []

    def copy(self, source: str, destination: str, link: bool = False, symlink: bool = False, mode: Optional[int] = None) -> None:
        """copy `source` to `destination`

        :param source: source file
        :param destination: destination file
        :param link: try hardlinking, falling back to copying
        :param symlink: create a symlink instead of copying
        :param mode: permissions to change `destination` to
        """
        if isinstance(mode, str):
            mode = int(mode, 8)

        self.actions.append(_FilesystemCopyAction(source, destination, link=link, symlink=symlink, mode=mode))

    def move(self, source: str, destination: str, mode: Optional[int] = None) -> None:
        """move `source` to `destination`

        :param source: source file
        :param destination: destination file
        :param mode: permissions to change `destination` to
        """
        self.copy(source, destination, link=True, mode=mode)
        self.unlink(source)

    def unlink(self, path: str) -> None:
        """unlink `path`

        :param path: file to unlink
        """
        self.actions.append(_FilesystemUnlinkAction(path))

    def create(self, path: str, mode: Optional[int] = None, text: bool = True) -> IO:
        """create `filename` and return file handle

        :param path: file to create
        :param mode: permissions for the new file
        :param text: open file in text mode
        :return: file handle of the new file
        """
        if isinstance(mode, str):
            mode = int(mode, 8)

        destdir = os.path.dirname(path)
        if not os.path.exists(destdir):
            os.makedirs(destdir, 0o2775)
        if os.path.exists(path):
            raise OSError(errno.EEXIST, os.strerror(errno.EEXIST), path)
        fh = open(path, 'w' if text else 'wb')
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
