#! /usr/bin/env python3
#
# Copyright (C) 2014, Ansgar Burchardt <ansgar@debian.org>
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

import unittest

from daklib.architecture import match_architecture


class MatchArchitecture(DakTestCase):
    def testEqual(self):
        self.assertTrue(match_architecture('amd64', 'amd64'))
        self.assertTrue(match_architecture('linux-amd64', 'linux-amd64'))
        self.assertTrue(match_architecture('linux-amd64', 'amd64'))
        self.assertTrue(match_architecture('amd64', 'linux-amd64'))
        self.assertTrue(not match_architecture('amd64', 'i386'))
        self.assertTrue(match_architecture('kfreebsd-amd64', 'kfreebsd-amd64'))
        self.assertTrue(not match_architecture('kfreebsd-amd64', 'amd64'))

    def testAny(self):
        self.assertTrue(match_architecture('amd64', 'any'))
        self.assertTrue(match_architecture('amd64', 'any-amd64'))
        self.assertTrue(match_architecture('x32', 'any-amd64'))
        self.assertTrue(match_architecture('kfreebsd-amd64', 'any-amd64'))
        self.assertTrue(not match_architecture('amd64', 'any-i386'))

        self.assertTrue(match_architecture('kfreebsd-amd64', 'kfreebsd-any'))
        self.assertTrue(not match_architecture('amd64', 'kfreebsd-any'))

    def testAll(self):
        self.assertTrue(match_architecture('all', 'all'))

        self.assertTrue(not match_architecture('amd64', 'all'))
        self.assertTrue(not match_architecture('all', 'amd64'))

        self.assertTrue(not match_architecture('all', 'any'))


if __name__ == '__main__':
    unittest.main()
