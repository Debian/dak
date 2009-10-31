import os
import sys
import unittest

from os.path import abspath, dirname, join

DAK_ROOT_DIR = dirname(dirname(abspath(__file__)))
DAK_TEST_FIXTURES = join(DAK_ROOT_DIR, 'tests', 'fixtures')

class DakTestCase(unittest.TestCase):
    def setUp(self):
        pass

os.environ['DAK_TEST'] = '1'
os.environ['DAK_CONFIG'] = join(DAK_TEST_FIXTURES, 'dak.conf')

if DAK_ROOT_DIR not in sys.path:
    sys.path.insert(0, DAK_ROOT_DIR)
