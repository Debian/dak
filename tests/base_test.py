import os
import sys
import unittest
import warnings

from os.path import abspath, dirname, join

DAK_ROOT_DIR = dirname(dirname(abspath(__file__)))

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

class DakTestCase(unittest.TestCase):
    def setUp(self):
        pass

def fixture(*dirs):
    return join(DAK_ROOT_DIR, 'tests', 'fixtures', *dirs)

os.environ['DAK_TEST'] = '1'
os.environ['DAK_CONFIG'] = fixture('dak.conf')

if DAK_ROOT_DIR not in sys.path:
    sys.path.insert(0, DAK_ROOT_DIR)
