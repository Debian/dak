#!/usr/bin/env python

from base_test import DakTestCase, fixture

import unittest

from daklib.gpg import GpgException
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
        except GpgException:
            pass
        except InvalidDscError as actual_line:
            if line is not None:
                assertEqual(actual_line, line)

class ParseDscTestCase(ParseChangesTestCase):
    def test_1(self):
        self.assertParse('dsc/1.dsc', -1, 1)

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
        self.assertFails('dsc/4.dsc', -1, 1)

    def test_5(self):
        # Extra blank line before signature body
        self.assertParse('dsc/5.dsc', -1, 1)

    def test_6(self):
        # Extra blank line after signature header
        self.assertParse('dsc/6.dsc', -1, 1)

class ParseChangesTestCase(ParseChangesTestCase):
    def test_1(self):
        # Empty changes
        self.assertFails('changes/1.changes', 5, -1)

    def test_2(self):
        changes = self.assertParse('changes/2.changes', -1)

        binaries = changes['binary']

        self.assert_('krb5-ftpd' in binaries.split())

    def test_3(self):
        for filename in ('valid', 'bogus-pre', 'bogus-post'):
            for strict_whitespace in (-1,):
                changes = self.assertParse(
                    'changes/%s.changes' % filename,
                    strict_whitespace,
                )
                self.failIf(changes.get('you'))

    def test_4(self):
        changes = self.assertParse('changes/two-beginnings.changes', -1, 1)
        self.assert_(changes['question'] == 'Is this a bug?')
        self.failIf(changes.get('this'))

if __name__ == '__main__':
    unittest.main()
