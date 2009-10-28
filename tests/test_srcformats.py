#!/usr/bin/env python

import unittest

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict

from daklib import srcformats
from daklib.dak_exceptions import UnknownFormatError

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
        self.assertRejected({
            'native_tar': 1,
            'native_tar_gz': 1,
            'debian_diff': 1,
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

##

class ParseFormat(unittest.TestCase):
    def assertFormat(self, input, expected, **kwargs):
        self.assertEqual(
            srcformats.SourceFormat.parse_format(input, **kwargs),
            expected,
        )

    def assertInvalidFormat(self, input, **kwargs):
        self.assertRaises(
            UnknownFormatError,
            lambda: srcformats.SourceFormat.parse_format(input, **kwargs),
        )

    def testEmpty(self):
        self.assertInvalidFormat('')
        self.assertInvalidFormat(' ')
        self.assertInvalidFormat('  ')

    def testBroken(self):
        self.assertInvalidFormat('.0')
        self.assertInvalidFormat('.1')
        self.assertInvalidFormat('format')

class ParseSourceFormat(ParseFormat):
    def assertFormat(self, *args, **kwargs):
        kwargs['is_a_dsc'] = kwargs.get('is_a_dsc', True)
        super(ParseSourceFormat, self).assertFormat(*args, **kwargs)

    def assertInvalidFormat(self, *args, **kwargs):
        kwargs['is_a_dsc'] = kwargs.get('is_a_dsc', True)
        super(ParseSourceFormat, self).assertInvalidFormat(*args, **kwargs)

    def testSimple(self):
        self.assertFormat('1.0', (1, 0))

    def testZero(self):
        self.assertInvalidFormat('0.0')

    def testNative(self):
        self.assertFormat('3.0 (native)', (3, 0, 'native'))

    def testQuilt(self):
        self.assertFormat('3.0 (quilt)', (3, 0, 'quilt'))

    def testUnknownThree(self):
        self.assertInvalidFormat('3.0 (cvs)')

class ParseBinaryFormat(ParseFormat):
    def assertFormat(self, *args, **kwargs):
        kwargs['is_a_dsc'] = kwargs.get('is_a_dsc', False)
        super(ParseBinaryFormat, self).assertFormat(*args, **kwargs)

    def assertInvalidFormat(self, *args, **kwargs):
        kwargs['is_a_dsc'] = kwargs.get('is_a_dsc', False)
        super(ParseBinaryFormat, self).assertInvalidFormat(*args, **kwargs)

    def testSimple(self):
        self.assertFormat('1.5', (1, 5))

    def testRange(self):
        self.assertInvalidFormat('1.0')
        self.assertFormat('1.5', (1, 5))
        self.assertFormat('1.8', (1, 8))
        self.assertInvalidFormat('1.9')

    def testFilesField(self):
        self.assertInvalidFormat('1.7', field='notfiles')
        self.assertFormat('1.8', (1, 8), field='notfiles')

if __name__ == '__main__':
    unittest.main()
