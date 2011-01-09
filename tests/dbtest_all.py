#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import unittest

def suite():
    suite = unittest.TestSuite()
    for _, _, files in os.walk('.'):
        for name in filter(is_test, files):
            tests = unittest.defaultTestLoader.loadTestsFromName(name[:-3])
            suite.addTests(tests)
    return suite

def is_test(filename):
    return filename.startswith('dbtest_') and filename.endswith('.py')

if __name__ == "__main__":
    unittest.main(defaultTest="suite")
