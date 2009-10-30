#!/usr/bin/env python

from base_test import DakTestCase

from daklib import regexes

class re_single_line_field(DakTestCase):
    MATCH = regexes.re_single_line_field.match

    def testSimple(self):
        self.assertEqual(self.MATCH('Foo: bar').groups(), ('Foo', 'bar'))

    def testLeadingWhitespace(self):
        self.assertEqual(self.MATCH(' Foo: bar'), None)

    def testTrailingWhitespace(self):
        self.assertEqual(self.MATCH('Foo: bar \n').groups(), ('Foo', 'bar '))

    def testMiddleWhitespace(self):
        self.assertEqual(self.MATCH('Foo:  bar').groups(), ('Foo', 'bar'))
        self.assertEqual(self.MATCH('Foo :  bar').groups(), ('Foo', 'bar'))
        self.assertEqual(self.MATCH('Foo \n:\n  bar').groups(), ('Foo', 'bar'))
        self.assertEqual(self.MATCH('Foo:bar').groups(), ('Foo', 'bar'))

    def testColons(self):
        self.assertEqual(self.MATCH('Foo: :').groups(), ('Foo', ':'))
        self.assertEqual(self.MATCH('Foo: ::').groups(), ('Foo', '::'))
        self.assertEqual(self.MATCH(': ::').groups(), ('', '::'))
        self.assertEqual(self.MATCH('Foo::bar').groups(), ('Foo', ':bar'))
        self.assertEqual(self.MATCH('Foo: :bar').groups(), ('Foo', ':bar'))

class re_parse_lintian(DakTestCase):
    MATCH = regexes.re_parse_lintian.match

    def testBinary(self):
        self.assertEqual(
            self.MATCH('W: pkgname: some-tag path/to/file').groups(),
            ('W', 'pkgname', 'some-tag', 'path/to/file')
        )

    def testBinaryNoDescription(self):
        self.assertEqual(
            self.MATCH('W: pkgname: some-tag').groups(),
            ('W', 'pkgname', 'some-tag', '')
        )

    def testSource(self):
        self.assertEqual(
            self.MATCH('W: pkgname source: some-tag').groups(),
            ('W', 'pkgname source', 'some-tag', '')
        )

    def testSourceNoDescription(self):
        self.assertEqual(
            self.MATCH('W: pkgname source: some-tag path/to/file').groups(),
            ('W', 'pkgname source', 'some-tag', 'path/to/file')
        )

if __name__ == '__main__':
    unittest.main()
