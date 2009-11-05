#!/usr/bin/env python

from base_test import DakTestCase, DAK_ROOT_DIR

import glob
import unittest

from os.path import join, basename, splitext

class ImportTestCase(DakTestCase):
    for filename in glob.glob(join(DAK_ROOT_DIR, 'dak', '*.py')):
        cmd, ext = splitext(basename(filename))

        def test_fn(self, cmd=cmd):
            __import__('dak', fromlist=[cmd])

        locals()['test_importing_%s' % cmd] = test_fn

if __name__ == '__main__':
    unittest.main()
