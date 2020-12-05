#! /usr/bin/env python3
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

from daklib.utils import (is_in_debug_section,
                          parse_built_using,
                          extract_component_from_section,
                          ArchKey)

apt_pkg.init()


class UtilsTest(DakTestCase):

    def test_utils_ArchKey(self):
        source = ArchKey('source')
        arch1 = ArchKey('amd64')
        arch2 = ArchKey('i386')

        assert source.__eq__(source)
        assert not source.__lt__(source)

        assert arch1.__eq__(arch1)
        assert not arch1.__lt__(arch1)

        assert not source.__eq__(arch1)
        assert not arch1.__eq__(source)
        assert source.__lt__(arch1)
        assert not arch1.__lt__(source)

        assert not arch1.__eq__(arch2)
        assert not arch2.__eq__(arch1)
        assert arch1.__lt__(arch2)
        assert not arch2.__lt__(arch1)

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
