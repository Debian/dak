#!/usr/bin/env python

from base_test import DakTestCase

from daklib.textutils import split_uploaders

import unittest

class SplitUploadersTestCase(DakTestCase):
    def test_main(self):
        expected = ['"A, B" <a@b.c>', 'D E <d@e.f>']
        l = list(split_uploaders('"A, B" <a@b.c>, D E <d@e.f>'))
        self.assertEqual(expected, l)
        l = list(split_uploaders('"A, B" <a@b.c> , D E <d@e.f>'))
        self.assertEqual(expected, l)
        l = list(split_uploaders('"A, B" <a@b.c>,D E <d@e.f>'))
        self.assertEqual(expected, l)
        l = list(split_uploaders('"A, B" <a@b.c>   ,D E <d@e.f>'))
        self.assertEqual(expected, l)

if __name__ == '__main__':
    unittest.main()
