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
            'W: pkgname: some-tag path/to/file', [{
                'level': 'W',
                'package': 'pkgname',
                'tag': 'some-tag',
                'description': 'path/to/file',
            }],
        )

        self.assertParse('', [])
        self.assertParse('\n\n', [])
        self.assertParse('dummy error test', [])

    def testBinaryNoDescription(self):
        self.assertParse(
            'W: pkgname: some-tag', [{
                'level': 'W',
                'package': 'pkgname',
                'tag': 'some-tag',
                'description': '',
            }],
        )

    def testSource(self):
        self.assertParse(
            'W: pkgname source: some-tag', [{
                'level': 'W',
                'package': 'pkgname source',
                'tag': 'some-tag',
                'description': '',
            }]
        )

    def testSourceNoDescription(self):
        self.assertParse(
            'W: pkgname source: some-tag path/to/file', [{
                'level': 'W',
                'package': 'pkgname source',
                'tag': 'some-tag',
                'description': 'path/to/file',
            }]
        )

class GenerateRejectMessages(DakTestCase):
    def assertNumReject(self, input, defs, num):
        msgs = list(generate_reject_messages(input, defs))
        self.assertEqual(len(msgs), num)

    def testUnknownTag(self):
        self.assertNumReject([
            {
                'level': 'W',
                'package': 'pkgname',
                'tag': 'unknown-tag',
                'description': '',
            }
            ], {'fatal': ['known-tag'], 'nonfatal': []},
            0,
        )

    def testFatalTags(self):
        self.assertNumReject([
            {
                'level': 'W',
                'package': 'pkgname',
                'tag': 'fatal-tag-1',
                'description': '',
            },
            {
                'level': 'W',
                'package': 'pkgname',
                'tag': 'fatal-tag-2',
                'description': '',
            },
            ], {'fatal': ['fatal-tag-1', 'fatal-tag-2'], 'nonfatal': []},
            2,
        )

    def testMixture(self):
        self.assertNumReject([
            {
                'level': 'W',
                'package': 'pkgname',
                'tag': 'fatal-tag',
                'description': '',
            },
            {
                'level': 'W',
                'package': 'pkgname',
                'tag': 'unknown-tag',
                'description': '',
            },
            ], {'fatal': ['fatal-tag'], 'nonfatal': []},
            1,
        )

    def testOverridable(self):
        self.assertNumReject([
            {
                'level': 'W',
                'package': 'pkgname',
                'tag': 'non-fatal-tag',
                'description': '',
            },
            ], {'fatal': [], 'nonfatal': ['non-fatal-tag']},
            1 + 1, # We add an extra 'reject' hint message
        )

    def testOverrideAllowed(self):
        self.assertNumReject([
                {'level': 'O',
                'package': 'pkgname',
                'tag': 'non-fatal-tag',
                'description': ''},
            ], {'fatal': [], 'nonfatal': ['non-fatal-tag']},
            0,
        )

    def testOverrideNotAllowed(self):
        self.assertNumReject([
            {
                'level': 'O',
                'package': 'pkgname',
                'tag': 'fatal-tag',
                'description': '',
            },
            ], {'fatal': ['fatal-tag'], 'nonfatal': []},
            1,
        )

if __name__ == '__main__':
    unittest.main()
