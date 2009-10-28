#!/usr/bin/env python

import unittest

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from daklib.formats import parse_format, validate_changes_format
from daklib.dak_exceptions import UnknownFormatError

class ParseFormatTestCase(unittest.TestCase):
    def assertParse(self, format, expected):
        self.assertEqual(parse_format(format), expected)

    def assertParseFail(self, format):
        self.assertRaises(
            UnknownFormatError,
            lambda: parse_format(format)
        )

    def testParse(self):
        self.assertParse('1.0', (1, 0))

    def testEmpty(self):
        self.assertParseFail('')
        self.assertParseFail(' ')
        self.assertParseFail('  ')

    def textText(self):
        self.assertParse('1.2 (three)', (1, 2, 'three'))
        self.assertParseFail('0.0 ()')

class ValidateChangesFormat(unittest.TestCase):
    def assertValid(self, changes, field='files'):
        validate_changes_format(changes, field)

    def assertInvalid(self, *args, **kwargs):
        self.assertRaises(
            UnknownFormatError,
            lambda: self.assertValid(*args, **kwargs)
        )

    ##

    def testBinary(self):
        self.assertValid((1, 5))
        self.assertValid((1, 8))
        self.assertInvalid((1, 0))

    def testRange(self):
        self.assertInvalid((1, 3))
        self.assertValid((1, 5))
        self.assertValid((1, 8))
        self.assertInvalid((1, 9))

    def testFilesField(self):
        self.assertInvalid((1, 7), field='notfiles')
        self.assertValid((1, 8), field='notfiles')
