#!/usr/bin/env python

import unittest

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from daklib import regexes

class re_single_line_field(unittest.TestCase):
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

class re_parse_lintian(unittest.TestCase):
    MATCH = regexes.re_parse_lintian.match

    def testSimple(self):
        self.assertEqual(
            self.MATCH('W: tzdata: binary-without-manpage usr/sbin/tzconfig').groups(),
            ('W', 'tzdata', 'binary-without-manpage', 'usr/sbin/tzconfig')
        )

if __name__ == '__main__':
    unittest.main()
