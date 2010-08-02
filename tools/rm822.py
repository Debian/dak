#!/usr/bin/python
# (c) 2010 Luca Falavigna <dktrkranz@debian.org>
# Free software licensed under the GPL version 2 or later

import re
from sys import argv

if len(argv) < 2:
    print 'Usage:\t./%s removal-file' % argv[0]
    exit()
fd = open(argv[1], 'r')
data = fd.read()
fd.close()
removals = re.split('=\n=', data)
for removal in removals:
    removal = re.sub('\n\n', '\n', removal)
    date = re.search('\[Date: (.*)\]\s\[', removal).group(1)
    ftpmaster = re.search('\[ftpmaster: (.*)]', removal).group(1)
    suite = re.search('from ([^:]+):', removal).group(1)
    packages = re.split('from [\S\s]+:\n', removal)[1].split('\n---')[0]
    reason = re.split('---\n', removal)[1].split('\n---')[0]
    bug = re.search('Closed bugs: (\d+)', removal)
    print 'Date: %s' % date
    print 'Ftpmaster: %s' % ftpmaster
    print 'Suite: %s' % suite
    sources = []
    binaries = []
    for package in packages.split('\n'):
        if package and not package.startswith('Closed bugs'):
            for row in package.split('\n'):
                element = row.split('|')
                if element[2].find('source') > 0:
                    sources.append(' %s_%s' % tuple(elem.strip(' ') for elem in element[:2]))
                    element[2] = re.sub('source\s?,?', '', element[2]).strip(' ')
                if element[2]:
                    binaries.append(' %s_%s [%s]' % tuple(elem.strip(' ') for elem in element))
    if sources:
        print 'Sources:'
        for source in sources:
            print source
    if binaries:
        print 'Binaries:'
        for binary in binaries:
            print binary
    print 'Reason: %s' % reason.replace('\n', '\n ')
    if bug:
        print 'Bug: %s' % bug.group(1)
    print
