#!/usr/bin/env python

from base_test import DakTestCase

import unittest

from daklib.utils import process_gpgv_output

class ProcessGPGVOutputTestCase(DakTestCase):
    def assertParse(self, input, output):
        self.assertEqual(process_gpgv_output(input)[0], output)

    def assertNotParse(self, input):
        ret = process_gpgv_output(input)
        self.assertNotEqual(len(ret[1]), 0)

    ##

    def testEmpty(self):
        self.assertParse('', {})

    def testBroken(self):
        self.assertNotParse('foo')
        self.assertNotParse('  foo  ')
        self.assertNotParse('[PREFIXPG:] KEY VAL1 VAL2 VAL3')

    def testSimple(self):
        self.assertParse(
            '[GNUPG:] KEY VAL1 VAL2 VAL3',
            {'KEY': ['VAL1', 'VAL2', 'VAL3']},
        )

    def testNoKeys(self):
        self.assertParse('[GNUPG:] KEY', {'KEY': []})

    def testDuplicate(self):
        self.assertNotParse('[GNUPG:] TEST_KEY\n[GNUPG:] TEST_KEY')
        self.assertNotParse('[GNUPG:] KEY VAL1\n[GNUPG:] KEY VAL2')

    def testDuplicateSpecial(self):
        # NODATA and friends are special
        for special in ('NODATA', 'SIGEXPIRED', 'KEYEXPIRED'):
            self.assertParse(
                '[GNUPG:] %s\n[GNUPG:] %s' % (special, special),
                {special: []},
            )

if __name__ == '__main__':
    unittest.main()
