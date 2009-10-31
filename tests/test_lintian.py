#!/usr/bin/env python

from base_test import DakTestCase

import unittest

from daklib.lintian import parse_lintian_output, generate_reject_messages

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

class GenerateRejectMessages(DakTestCase):
    def assertNumReject(self, input, defs, num):
        msgs = list(generate_reject_messages(input, defs))
        self.assertEqual(len(msgs), num)

    def testUnknownTag(self):
        self.assertNumReject(
            [('W', 'pkgname', 'unknown-tag', '')],
            {'fatal': ['known-tag'], 'nonfatal': []},
            0,
        )

    def testFatalTags(self):
        self.assertNumReject([
                ('W', 'pkgname', 'fatal-tag-1', ''),
                ('W', 'pkgname', 'fatal-tag-2', ''),
            ],
            {'fatal': ['fatal-tag-1', 'fatal-tag-2'], 'nonfatal': []},
            2,
        )

    def testMixture(self):
        self.assertNumReject([
                ('W', 'pkgname', 'fatal-tag', ''),
                ('W', 'pkgname', 'unknown-tag', ''),
            ],
            {'fatal': ['fatal-tag'], 'nonfatal': []},
            1,
        )

    def testOverridable(self):
        self.assertNumReject([
                ('W', 'pkgname', 'non-fatal-tag', ''),
            ],
            {'fatal': [], 'nonfatal': ['non-fatal-tag']},
            1 + 1, # We add an extra 'reject' hint message
        )

    def testOverrideAllowed(self):
        self.assertNumReject([
                ('O', 'pkgname', 'non-fatal-tag', ''),
            ],
            {'fatal': [], 'nonfatal': ['non-fatal-tag']},
            0,
        )

    def testOverrideNotAllowed(self):
        self.assertNumReject([
                ('O', 'pkgname', 'fatal-tag', ''),
            ],
            {'fatal': ['fatal-tag'], 'nonfatal': []},
            1,
        )

if __name__ == '__main__':
    unittest.main()
