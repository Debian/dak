#!/usr/bin/python
# (c) 2010 Luca Falavigna <dktrkranz@debian.org>
# Free software licensed under the GPL version 2 or later

import os
import sys
import fnmatch
from glob import glob
sys.path.append('../dak')
from daklib.dbconn import *
from daklib import utils
from daklib.queue import Upload

i = 0
t = 0
pattern = '*.changes'
changes_dir = '/srv/ftp.debian.org/queue/done'

def find_changes(pattern, root):
    for path, dirs, files in os.walk(os.path.abspath(root)):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(path, filename)

for changes_file in find_changes(pattern, changes_dir):
    t = t + 1
for changes_file in find_changes(pattern, changes_dir):
    u = Upload()
    u.pkg.changes_file = changes_file
    (u.pkg.changes["fingerprint"], rejects) = utils.check_signature(changes_file)
    if u.load_changes(changes_file):
        try:
            u.store_changelog()
        except:
            print 'Unable to handle %s' % changes_file
    else:
        print u.rejects
    i = i + 1
    sys.stdout.write('%d out of %d processed\r' % (i, t))
