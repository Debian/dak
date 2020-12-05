#! /usr/bin/env python3

from base_test import DakTestCase, fixture

import unittest

from daklib.gpg import GpgException
from daklib.utils import parse_changes, check_dsc_files, build_file_list
from daklib.dak_exceptions import ParseChangesError


class ParseChangesTestCase(DakTestCase):
    def assertParse(self, filename, *args):
        return parse_changes(fixture(filename), *args)


class ParseDscTestCase(ParseChangesTestCase):
    def test_1(self):
        changes = self.assertParse('dsc/1.dsc', -1, 1)
        files = build_file_list(changes, 1)
        rejmsg = check_dsc_files('1.dsc', changes, files.keys())
        self.assertEqual(rejmsg, [])

    def test_1_ignoreErrors(self):
        # Valid .dsc ; ignoring errors
        self.assertParse('dsc/1.dsc', -1, 1)

    def test_2(self):
        # Missing blank line before signature body
        self.assertParse('dsc/2.dsc', -1, 1)

    def test_2_ignoreErrors(self):
        # Invalid .dsc ; ignoring errors
        self.assertParse('dsc/2.dsc', -1, 1)

    def test_3(self):
        # Missing blank line after signature header
        self.assertParse('dsc/3.dsc', -1, 1)

    def test_4(self):
        # No blank lines at all
        with self.assertRaises(GpgException):
            self.assertParse('dsc/4.dsc', -1, 1)

    def test_5(self):
        # Extra blank line before signature body
        self.assertParse('dsc/5.dsc', -1, 1)

    def test_6(self):
        # Extra blank line after signature header
        self.assertParse('dsc/6.dsc', -1, 1)

    def test_7(self):
        # Blank file is an invalid armored GPG file
        with self.assertRaises(GpgException):
            self.assertParse('dsc/7.dsc', -1, 1)

    def test_8(self):
        # No armored contents
        with self.assertRaisesRegex(ParseChangesError, "Empty changes"):
            self.assertParse('dsc/8.dsc', -1, 1)

    def test_9(self):
        changes = self.assertParse('dsc/9.dsc', -1, 1)
        self.assertTrue(changes['question'] == 'Is this a bug?')
        self.assertFalse(changes.get('this'))

    def test_10(self):
        changes = self.assertParse('dsc/10.dsc', -1, 1)
        files = build_file_list(changes, 1)
        rejmsg = check_dsc_files('10.dsc', changes, files.keys())
        self.assertEqual(rejmsg, [])


class ParseChangesTestCase(ParseChangesTestCase):
    def test_1(self):
        # Empty changes
        with self.assertRaises(GpgException):
            self.assertParse('changes/1.changes', 1)

    def test_2(self):
        changes = self.assertParse('changes/2.changes', -1)

        binaries = changes['binary']

        self.assertTrue('krb5-ftpd' in binaries.split())

    def test_3(self):
        for filename in ('valid', 'bogus-pre', 'bogus-post'):
            for strict_whitespace in (-1,):
                changes = self.assertParse(
                    'changes/%s.changes' % filename,
                    strict_whitespace,
                )
                self.assertFalse(changes.get('you'))


if __name__ == '__main__':
    unittest.main()
