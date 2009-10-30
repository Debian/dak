import sys
import unittest

from os.path import abspath, dirname, join

DAK_ROOT_DIR = dirname(dirname(abspath(__file__)))

class DakTestCase(unittest.TestCase):
    def setUp(self):
        pass

if DAK_ROOT_DIR not in sys.path:
    sys.path.insert(0, DAK_ROOT_DIR)
