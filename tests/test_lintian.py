#!/usr/bin/env python

from base_test import DakTestCase

import unittest

from daklib.lintian import parse_lintian_output

class ParseLintianTestCase(DakTestCase):
    def assertParse(self, output, expected):
        self.assertEqual(
            list(parse_lintian_output(output)),
            expected,
        )

    def testSimple(self):
        self.assertParse(
            'W: pkgname: some-tag path/to/file',
            [('W', 'pkgname', 'some-tag', 'path/to/file')],
        )

        self.assertParse('', [])
        self.assertParse('\n\n', [])
        self.assertParse('dummy error test', [])

    def testBinaryNoDescription(self):
        self.assertParse(
            'W: pkgname: some-tag',
            [('W', 'pkgname', 'some-tag', '')],
        )

    def testSource(self):
        self.assertParse(
            'W: pkgname source: some-tag',
            [('W', 'pkgname source', 'some-tag', '')]
        )

    def testSourceNoDescription(self):
        self.assertParse(
            'W: pkgname source: some-tag path/to/file',
            [('W', 'pkgname source', 'some-tag', 'path/to/file')]
        )

if __name__ == '__main__':
    unittest.main()
