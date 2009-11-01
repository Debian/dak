#!/usr/bin/env python
# -*- coding: utf-8 -*-

from base_test import DakTestCase

import unittest

from daklib.textutils import fix_maintainer
from daklib.dak_exceptions import ParseMaintError

class FixMaintainerTestCase(DakTestCase):
    def assertValid(self, input, a, b, c, d):
        a_, b_, c_, d_ = fix_maintainer(input)

        self.assertEqual(a, a_)
        self.assertEqual(b, b_)
        self.assertEqual(c, c_)
        self.assertEqual(d, d_)

    def assertNotValid(self, input):
        self.assertRaises(ParseMaintError, lambda: fix_maintainer(input))

    def testUTF8Maintainer(self):
        # Check Valid UTF-8 maintainer field
        self.assertValid(
            "Noèl Köthe <noel@debian.org>",
            "Noèl Köthe <noel@debian.org>",
            "=?utf-8?b?Tm/DqGwgS8O2dGhl?= <noel@debian.org>",
            "Noèl Köthe",
            "noel@debian.org",
        )

    def testASCII(self):
        # Check valid ASCII maintainer field
        self.assertValid(
            "James Troup <james@nocrew.org>",
            "James Troup <james@nocrew.org>",
            "James Troup <james@nocrew.org>",
            "James Troup",
            "james@nocrew.org",
        )

    def testRFC822(self):
        # Check "Debian vs RFC822" fixup of names with '.' or ',' in them
        self.assertValid(
            "James J. Troup <james@nocrew.org>",
            "james@nocrew.org (James J. Troup)",
            "james@nocrew.org (James J. Troup)",
            "James J. Troup",
            "james@nocrew.org",
        )

    def testSimple(self):
        self.assertValid(
            "James J, Troup <james@nocrew.org>",
            "james@nocrew.org (James J, Troup)",
            "james@nocrew.org (James J, Troup)",
            "James J, Troup",
            "james@nocrew.org",
        )

    def testJustEmail(self):
        # Check just-email form
        self.assertValid(
            "james@nocrew.org",
            " <james@nocrew.org>",
            " <james@nocrew.org>",
            "",
            "james@nocrew.org",
        )

    def testBracketedEmail(self):
        # Check bracketed just-email form
        self.assertValid(
            "<james@nocrew.org>",
            " <james@nocrew.org>",
            " <james@nocrew.org>",
            "",
            "james@nocrew.org",
        )

    def testKrazy(self):
        # Check Krazy quoted-string local part email address
        self.assertValid(
            "Cris van Pelt <\"Cris van Pelt\"@tribe.eu.org>",
            "Cris van Pelt <\"Cris van Pelt\"@tribe.eu.org>",
            "Cris van Pelt <\"Cris van Pelt\"@tribe.eu.org>",
            "Cris van Pelt",
            "\"Cris van Pelt\"@tribe.eu.org",
        )

    def testEmptyString(self):
        # Check empty string
        self.assertValid("", "", "", "", "")

    def testMissingEmailAddress(self):
        # Check for missing email address
        self.assertNotValid("James Troup")

    def testInvalidEmail(self):
        # Check for invalid email address
        self.assertNotValid("James Troup <james@nocrew.org")

if __name__ == '__main__':
    unittest.main()
