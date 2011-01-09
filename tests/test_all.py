#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import unittest
import warnings

# suppress some deprecation warnings in squeeze related to apt_pkg,
# debian, and md5 modules
warnings.filterwarnings('ignore', \
    "Attribute '.*' of the 'apt_pkg\.Configuration' object is deprecated, use '.*' instead\.", \
    DeprecationWarning)
warnings.filterwarnings('ignore', \
    "apt_pkg\.newConfiguration\(\) is deprecated\. Use apt_pkg\.Configuration\(\) instead\.", \
    DeprecationWarning)
warnings.filterwarnings('ignore', \
    "please use 'debian' instead of 'debian_bundle'", \
    DeprecationWarning)
warnings.filterwarnings('ignore', \
    "the md5 module is deprecated; use hashlib instead", \
    DeprecationWarning)

def suite():
    suite = unittest.TestSuite()
    for _, _, files in os.walk('.'):
        for name in filter(is_test, files):
            tests = unittest.defaultTestLoader.loadTestsFromName(name[:-3])
            suite.addTests(tests)
    return suite

def is_test(filename):
    return filename.startswith('test_') and filename.endswith('.py')

if __name__ == "__main__":
    unittest.main(defaultTest="suite")
