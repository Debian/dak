#!/usr/bin/env python

from base_test import DakTestCase

from daklib import srcformats
from collections import defaultdict
from daklib.formats import parse_format
from daklib.dak_exceptions import UnknownFormatError

class SourceFormatTestCase(DakTestCase):
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

class FormatFromStringTestCase(DakTestCase):
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
