#!/usr/bin/env python

from db_test import DBDakTestCase

import unittest

from daklib.utils import extract_component_from_section

class ExtractComponentTestCase(DBDakTestCase):
    """
    prefix: non-US
    component: main, contrib, non-free
    section: games, admin, libs, [...]

    [1] Order is as above.
    [2] Prefix is optional for the default archive, but mandatory when
        uploads are going anywhere else.
    [3] Default component is main and may be omitted.
    [4] Section is optional.
    [5] Prefix is case insensitive
    [6] Everything else is case sensitive.
    """

    def assertExtract(self, input, output):
        self.setup_components()
        self.assertEqual(
            extract_component_from_section(input, self.session)[1],
            output,
        )

    def test_1(self):
        # Validate #3
        self.assertExtract('utils', 'main')

    def test_2(self):
        # Err, whoops?  should probably be 'utils', 'main'...
        self.assertExtract('main/utils', 'main')

    def test_3(self):
        self.assertExtract('non-free/libs', 'non-free')

    def test_4(self):
        self.assertExtract('contrib/net', 'contrib')

    def test_5(self):
        # Validate #4
        self.assertExtract('main', 'main')

    def test_6(self):
        self.assertExtract('contrib', 'contrib')

    def test_7(self):
        self.assertExtract('non-free', 'non-free')

    def test_8(self):
        # Validate #6 (section)
        self.assertExtract('utIls', 'main')

if __name__ == '__main__':
    unittest.main()
