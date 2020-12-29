#! /usr/bin/env python3
# -*- coding: utf-8 -*-
#
# © 2020, 😸 <😸@43-1.org>
#
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

import os

from base_test import DakTestCase

import daklib.dakapt


class TestDakHashes(DakTestCase):
    def testDakHashes(self):
        with open(os.devnull) as fh:
            hashes = daklib.dakapt.DakHashes(fh)
        self.assertEqual(hashes.md5, "d41d8cd98f00b204e9800998ecf8427e")
        self.assertEqual(hashes.sha1, "da39a3ee5e6b4b0d3255bfef95601890afd80709")
        self.assertEqual(hashes.sha256, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
