#! /usr/bin/env python
#
# Copyright (C) 2017, Niels Thykier <niels@thykier.net>
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

import apt_pkg
import unittest
from base_test import DakTestCase

from daklib.utils import (arch_compare_sw, is_in_debug_section,
                          parse_built_using,
                          extract_component_from_section)

apt_pkg.init()

class UtilsTest(DakTestCase):

    def test_utils_arch_compare_sw(self):
        data = [
            ('source', 'source', 0),
            ('source', 'amd64', -1),
            ('amd64', 'amd64', 0),
            ('amd64', 'source', 1),
            ('amd64', 'i386', -1),
            ('i386', 'amd64', 1),
        ]
        for a, b, r in data:
            self.assertEqual(arch_compare_sw(a, b), r)


    def test_is_in_debug_section(self):
        data = [
            (
                {
                    'Section': 'debug',
                    'Auto-Built-Package': 'debug-symbols',
                },
                True,
            ),
            (
                {
                    'Section': 'non-free/debug',
                    'Auto-Built-Package': 'debug-symbols',
                },
                True
            ),
            (
                {
                    'Section': 'debug',
                    'Auto-Built-Package': 'other',
                },
                False
            ),
            (
                {
                    'Section': 'non-free/debug',
                    'Auto-Built-Package': 'other',
                },
                False
            ),
            (
                {
                    'Section': 'debug',
                },
                False
            ),
            (
                {
                    'Section': 'non-free/debug',
                },
                False
            ),
        ]
        for ctrl, r in data:
            self.assertEqual(is_in_debug_section(ctrl), r)

    def test_parse_built_using(self):
        field = 'binutils (= 1.0-1), gcc-6 (= 6.3-2)'
        expected = [('binutils', '1.0-1'), ('gcc-6', '6.3-2')]
        ctrl = {
            'Built-Using': field,
        }
        self.assertEqual(parse_built_using(ctrl), expected)
        self.assertEqual(parse_built_using({}), [])

    def test_extract_component_from_section(self):
        data = [
            # Argument is passed through as first return value. There
            # is a comment in docs/TODO.old suggesting that it should
            # be changed.
            ('utils', ('utils', 'main')),
            ('main/utils', ('main/utils', 'main')),
            ('non-free/libs', ('non-free/libs', 'non-free')),
            ('contrib/net', ('contrib/net', 'contrib')),
            ('non-free/two/slashes', ('non-free/two/slashes', 'non-free'))
        ]
        for v, r in data:
            self.assertEqual(extract_component_from_section(v), r)


if __name__ == '__main__':
    unittest.main()
