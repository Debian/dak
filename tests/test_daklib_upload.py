#! /usr/bin/env python3
#
# Copyright (C) 2018, Ansgar Burchardt <ansgar@debian.org>
# License: GPL-2+
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
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from base_test import DakTestCase
import unittest

import daklib.upload


class DummySortableChanges(daklib.upload.Changes):
    def __init__(self, source, version, architectures, filename):
        self.changes = {
            'Source': source,
            'Version': version,
            'Architecture': architectures,
        }
        self.filename = filename


class TestSortableChanges(DakTestCase):
    def testEq(self):
        a = DummySortableChanges(
            'source', '1.0-1', 'source all', 'source_1.0-1_amd64.changes')

        self.assertTrue(a == a)
        self.assertTrue(a <= a)
        self.assertTrue(a >= a)
        self.assertFalse(a < a)
        self.assertFalse(a > a)

    def testSourceDiffers1(self):
        a = DummySortableChanges(
            'a', '1.0-1', 'all', 'a_1.0-1_amd64.changes')
        b = DummySortableChanges(
            'b', '1.0-1', 'all', 'b_1.0-1_amd64.changes')

        self.assertTrue(a < b)
        self.assertFalse(a == b)

    def testSourceDiffers2(self):
        a = DummySortableChanges(
            'a', '2.0-1', 'all', 'a_2.0-1_amd64.changes')
        b = DummySortableChanges(
            'b', '1.0-1', 'all', 'b_1.0-1_amd64.changes')

        self.assertTrue(a < b)
        self.assertFalse(a == b)

    def testSourcefulSortsFirst(self):
        a = DummySortableChanges(
            'a', '1.0-1', 'source powerpc', 'a_1.0-1_powerpc.changes')
        b = DummySortableChanges(
            'a', '1.0-1', 'amd64', 'a_1.0-1_amd64.changes')

        self.assertTrue(a < b)
        self.assertFalse(a == b)
