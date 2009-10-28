#!/usr/bin/env python

import unittest

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from daklib.formats import parse_format
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
