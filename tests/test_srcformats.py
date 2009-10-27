#!/usr/bin/env python

import unittest

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict

from daklib import srcformats

class SourceFormatTestCase(unittest.TestCase):
    def get_rejects(self, has_vars):
        has = defaultdict(lambda: 0)
        has.update(has_vars)
        return list(self.fmt.reject_msgs(has))

    def assertAccepted(self, has):
        self.assertEqual(self.get_rejects(has), [])

    def assertRejected(self, has):
        self.assertNotEqual(self.get_rejects(has), [])

class FormatOneTestCase(SourceFormatTestCase):
    fmt = srcformats.FormatOne

    def testEmpty(self):
        self.assertRejected({})

    def testNative(self):
        self.assertAccepted({'native_tar': 1, 'native_tar_gz': 1})

    def testStandard(self):
        self.assertAccepted({
            'orig_tar': 1,
            'orig_tar_gz': 1,
            'debian_diff': 1,
        })

    def testDisallowed(self):
        self.assertRejected({
            'native_tar': 1,
            'native_tar_gz': 1,
            'debian_tar': 1,
        })
        self.assertRejected({
            'orig_tar': 1,
            'orig_tar_gz': 1,
            'debian_diff': 0,
        })
        self.assertRejected({
            'native_tar': 1,
            'native_tar_gz': 1,
            'more_orig_tar': 1,
        })

class FormatTreeTestCase(SourceFormatTestCase):
    fmt = srcformats.FormatThree

    def testEmpty(self):
        self.assertRejected({})

    def testSimple(self):
        self.assertAccepted({'native_tar': 1})

    def testDisallowed(self):
        self.assertRejected({'native_tar': 1, 'orig_tar': 1})
        self.assertRejected({'native_tar': 1, 'debian_diff': 1})
        self.assertRejected({'native_tar': 1, 'debian_tar': 1})
        self.assertRejected({'native_tar': 1, 'more_orig_tar': 1})

class FormatTreeQuiltTestCase(SourceFormatTestCase):
    fmt = srcformats.FormatThreeQuilt

    def testEmpty(self):
        self.assertRejected({})

    def testSimple(self):
        self.assertAccepted({'orig_tar': 1, 'debian_tar': 1})

    def testMultipleTarballs(self):
        self.assertAccepted({
            'orig_tar': 1,
            'debian_tar': 1,
            'more_orig_tar': 42,
        })

    def testDisallowed(self):
        self.assertRejected({
            'orig_tar': 1,
            'debian_tar': 1,
            'debian_diff': 1
        })
        self.assertRejected({
            'orig_tar': 1,
            'debian_tar': 1,
            'native_tar': 1,
        })

if __name__ == '__main__':
    unittest.main()
