#! /usr/bin/env python3

from base_test import DakTestCase, DAK_ROOT_DIR

import glob
import importlib
import unittest

from os.path import join, basename, splitext


class ImportTestCase(DakTestCase):
    for filename in glob.glob(join(DAK_ROOT_DIR, 'dak', '*.py')):
        cmd, ext = splitext(basename(filename))

        def test_fn(self, cmd=cmd):
            importlib.import_module("dak.{}".format(cmd))

        locals()['test_importing_%s' % cmd] = test_fn


if __name__ == '__main__':
    unittest.main()
