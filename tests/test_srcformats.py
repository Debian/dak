#!/usr/bin/env python

import unittest

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict

from daklib import srcformats
from daklib.formats import parse_format
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

class ValidateFormatTestCase(unittest.TestCase):
    def assertValid(self, format, **kwargs):
        kwargs['is_a_dsc'] = kwargs.get('is_a_dsc', True)
        self.fmt.validate_format(format, **kwargs)

    def assertInvalid(self, *args, **kwargs):
        self.assertRaises(
            UnknownFormatError,
            lambda: self.assertValid(*args, **kwargs),
        )

class ValidateFormatOneTestCase(ValidateFormatTestCase):
    fmt = srcformats.FormatOne

    def testValid(self):
        self.assertValid((1, 0))

    def testInvalid(self):
        self.assertInvalid((0, 1))
        self.assertInvalid((3, 0, 'quilt'))

    ##

    def testBinary(self):
        self.assertValid((1, 5), is_a_dsc=False)
        self.assertInvalid((1, 0), is_a_dsc=False)

    def testRange(self):
        self.assertInvalid((1, 3), is_a_dsc=False)
        self.assertValid((1, 5), is_a_dsc=False)
        self.assertValid((1, 8), is_a_dsc=False)
        self.assertInvalid((1, 9), is_a_dsc=False)

    def testFilesField(self):
        self.assertInvalid((1, 7), is_a_dsc=False, field='notfiles')
        self.assertValid((1, 8), is_a_dsc=False, field='notfiles')

class ValidateFormatThreeTestCase(ValidateFormatTestCase):
    fmt = srcformats.FormatThree

    def testValid(self):
        self.assertValid((3, 0, 'native'))

    def testInvalid(self):
        self.assertInvalid((1, 0))
        self.assertInvalid((0, 0))
        self.assertInvalid((3, 0, 'quilt'))

class ValidateFormatThreeQuiltTestCase(ValidateFormatTestCase):
    fmt = srcformats.FormatThreeQuilt

    def testValid(self):
        self.assertValid((3, 0, 'quilt'))

    def testInvalid(self):
        self.assertInvalid((1, 0))
        self.assertInvalid((0, 0))
        self.assertInvalid((3, 0, 'native'))

class FormatFromStringTestCase(unittest.TestCase):
    def assertFormat(self, txt, klass):
        self.assertEqual(srcformats.get_format_from_string(txt), klass)

    def assertInvalid(self, txt):
        self.assertRaises(
            UnknownFormatError,
            lambda: srcformats.get_format_from_string(txt),
        )

    def testFormats(self):
        self.assertFormat('1.0', srcformats.FormatOne)
        self.assertFormat('3.0 (native)', srcformats.FormatThree)
        self.assertFormat('3.0 (quilt)', srcformats.FormatThreeQuilt)

    def testInvalidFormats(self):
        self.assertInvalid('')
        self.assertInvalid('.')
        self.assertInvalid('3.0 (cvs)')
        self.assertInvalid(' 1.0 ')
        self.assertInvalid('8.4 (hardy)')

if __name__ == '__main__':
    unittest.main()
