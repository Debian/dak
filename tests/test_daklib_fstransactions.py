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

from base_test import DakTestCase
from daklib.fstransactions import FilesystemTransaction

from unittest import main

import os
import shutil
import tempfile


class TemporaryDirectory:
    def __init__(self):
        self.directory = None
    def __str__(self):
        return self.directory
    def filename(self, suffix):
        return os.path.join(self.directory, suffix)
    def __enter__(self):
        self.directory = tempfile.mkdtemp()
        return self
    def __exit__(self, *args):
        if self.directory is not None:
            shutil.rmtree(self.directory)
            self.directory = None
        return None

class FilesystemTransactionTestCase(DakTestCase):
    def _copy_a_b(self, tmp, fs, **kwargs):
        fs.copy(tmp.filename('a'), tmp.filename('b'), **kwargs)

    def _write_to_a(self, tmp):
        with open(tmp.filename('a'), 'w') as fh:
            print >>fh, 'a'

    def test_copy_non_existing(self):
        def copy():
            with TemporaryDirectory() as t:
                with FilesystemTransaction() as fs:
                    self._copy_a_b(t, fs)

        self.assertRaises(IOError, copy)

    def test_copy_existing_and_commit(self):
        with TemporaryDirectory() as t:
            self._write_to_a(t)

            with FilesystemTransaction() as fs:
                self._copy_a_b(t, fs)
                self.assert_(os.path.exists(t.filename('a')))
                self.assert_(os.path.exists(t.filename('b')))

            self.assert_(os.path.exists(t.filename('a')))
            self.assert_(os.path.exists(t.filename('b')))

    def test_copy_existing_and_rollback(self):
        with TemporaryDirectory() as t:
            self._write_to_a(t)

            class TestException(Exception):
                pass
            try:
                with FilesystemTransaction() as fs:
                    self._copy_a_b(t, fs)
                    self.assert_(os.path.exists(t.filename('a')))
                    self.assert_(os.path.exists(t.filename('b')))
                    raise TestException()
            except TestException:
                pass

            self.assert_(os.path.exists(t.filename('a')))
            self.assert_(not os.path.exists(t.filename('b')))

    def test_unlink_and_commit(self):
        with TemporaryDirectory() as t:
            self._write_to_a(t)
            a = t.filename('a')
            with FilesystemTransaction() as fs:
                self.assert_(os.path.exists(a))
                fs.unlink(a)
                self.assert_(not os.path.exists(a))
            self.assert_(not os.path.exists(a))

    def test_unlink_and_rollback(self):
        with TemporaryDirectory() as t:
            self._write_to_a(t)
            a = t.filename('a')
            class TestException(Exception):
                pass

            try:
                with FilesystemTransaction() as fs:
                    self.assert_(os.path.exists(a))
                    fs.unlink(a)
                    self.assert_(not os.path.exists(a))
                    raise TestException()
            except TestException:
                pass
            self.assert_(os.path.exists(a))

if __name__ == '__main__':
    main()
