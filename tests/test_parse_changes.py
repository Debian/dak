#!/usr/bin/env python

from base_test import DakTestCase, fixture

import unittest

from daklib.utils import parse_changes
from daklib.dak_exceptions import InvalidDscError, ParseChangesError

class ParseChangesTestCase(DakTestCase):
    def assertParse(self, filename, *args):
        return parse_changes(fixture(filename), *args)

    def assertFails(self, filename, line=None, *args):
        try:
            self.assertParse(filename, *args)
            self.fail('%s was not recognised as invalid' % filename)
        except ParseChangesError:
            pass
        except InvalidDscError, actual_line:
            if line is not None:
                assertEqual(actual_line, line)

class ParseDscTestCase(ParseChangesTestCase):
    def test_1(self):
        self.assertParse('dsc/1.dsc')

    def test_1_ignoreErrors(self):
        # Valid .dsc ; ignoring errors
        self.assertParse('dsc/1.dsc', 0)

    def test_2(self):
        # Missing blank line before signature body
        self.assertFails('dsc/2.dsc', line=14)

    def test_2_ignoreErrors(self):
        # Invalid .dsc ; ignoring errors
        self.assertParse('dsc/2.dsc', 0)

    def test_3(self):
        # Missing blank line after signature header
        self.assertFails('dsc/3.dsc', line=14)

    def test_4(self):
        # No blank lines at all
        self.assertFails('dsc/4.dsc', line=19)

    def test_5(self):
        # Extra blank line before signature body
        self.assertFails('dsc/5.dsc', line=15)

    def test_6(self):
        # Extra blank line after signature header
        self.assertFails('dsc/6.dsc', line=5)

class ParseChangesTestCase(ParseChangesTestCase):
    def test_1(self):
        # Empty changes
        self.assertFails('changes/1.changes', line=5)

    def test_2(self):
        changes = self.assertParse('changes/2.changes', 0)

        binaries = changes['binary']

        self.assert_('krb5-ftpd' in binaries.split())

    def test_3(self):
        for filename in ('valid', 'bogus-pre', 'bogus-post'):
            for strict_whitespace in (0, 1):
                changes = self.assertParse(
                    'changes/%s.changes' % filename,
                    strict_whitespace,
                )
                self.failIf(changes.get('you'))

if __name__ == '__main__':
    unittest.main()
