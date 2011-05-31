import os
import sys
import unittest
import warnings

from os.path import abspath, dirname, join

DAK_ROOT_DIR = dirname(dirname(abspath(__file__)))

class DakTestCase(unittest.TestCase):
    def setUp(self):
        pass

def fixture(*dirs):
    return join(DAK_ROOT_DIR, 'tests', 'fixtures', *dirs)

os.environ['DAK_TEST'] = '1'
os.environ['DAK_CONFIG'] = fixture('dak.conf')

if DAK_ROOT_DIR not in sys.path:
    sys.path.insert(0, DAK_ROOT_DIR)
