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

import daklib.dbconn


class DummyChanges(object):
    def __init__(self, source, version, changesname):
        self.source = source
        self.version = version
        self.changesname = changesname


class DummySortablePolicyQueueUpload(daklib.dbconn.PolicyQueueUpload):
    def __init__(self, source, version, sourceful, filename):
        self.changes = DummyChanges(source, version, filename)
        self.source = True if sourceful else None


class TestSortableChanges(DakTestCase):
    def testEq(self):
        a = DummySortablePolicyQueueUpload(
            'source', '1.0-1', True, 'source_1.0-1_amd64.changes')

        self.assertTrue(a == a)
        self.assertTrue(a <= a)
        self.assertTrue(a >= a)
        self.assertFalse(a < a)
        self.assertFalse(a > a)

    def testSourceDiffers1(self):
        a = DummySortablePolicyQueueUpload(
            'a', '1.0-1', False, 'a_1.0-1_amd64.changes')
        b = DummySortablePolicyQueueUpload(
            'b', '1.0-1', False, 'b_1.0-1_amd64.changes')

        self.assertTrue(a < b)
        self.assertFalse(a == b)

    def testSourceDiffers2(self):
        a = DummySortablePolicyQueueUpload(
            'a', '2.0-1', False, 'a_2.0-1_amd64.changes')
        b = DummySortablePolicyQueueUpload(
            'b', '1.0-1', False, 'b_1.0-1_amd64.changes')

        self.assertTrue(a < b)
        self.assertFalse(a == b)

    def testSourcefulSortsFirst(self):
        a = DummySortablePolicyQueueUpload(
            'a', '1.0-1', True, 'a_1.0-1_powerpc.changes')
        b = DummySortablePolicyQueueUpload(
            'a', '1.0-1', False, 'a_1.0-1_amd64.changes')

        self.assertTrue(a < b)
        self.assertFalse(a == b)
