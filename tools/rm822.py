#! /usr/bin/env python3
# (c) 2010 Luca Falavigna <dktrkranz@debian.org>
# Free software licensed under the GPL version 2 or later

import re
from sys import argv

if len(argv) < 2:
    print('Usage:\t./%s removal-file' % argv[0])
    exit()
with open(argv[1]) as fh:
    data = fh.read()
removals = re.split('=\n=', data)
for removal in removals:
    removal = re.sub('\n\n', '\n', removal)
    date = re.search(r'\[Date: (.*)\]\s\[', removal).group(1)
    ftpmaster = re.search(r'\[ftpmaster: (.*)]', removal).group(1)
    suite = re.search('from ([^:]+):', removal).group(1)
    packages = re.split(r'from [\S\s]+:\n', removal)[1].split('\n---')[0]
    reason = re.split('---\n', removal)[1].split('\n---')[0]
    bug = re.search(r'Closed bugs: (\d+)', removal)
    print(f'Date: {date}')
    print(f'Ftpmaster: {ftpmaster}')
    print(f'Suite: {suite}')
    sources = []
    binaries = []
    for package in packages.split('\n'):
        if package and not package.startswith('Closed bugs'):
            for row in package.split('\n'):
                element = row.split('|')
                if element[2].find('source') > 0:
                    sources.append(' %s_%s' % tuple(elem.strip(' ') for elem in element[:2]))
                    element[2] = re.sub(r'source\s?,?', '', element[2]).strip(' ')
                if element[2]:
                    binaries.append(' %s_%s [%s]' % tuple(elem.strip(' ') for elem in element))
    if sources:
        print('Sources:', *sources, sep='\n')
    if binaries:
        print('Binaries:', *binaries, sep='\n')
    print('Reason: {}'.format(reason.replace('\n', '\n ')))
    if bug:
        print(f'Bug: {bug.group(1)}')
    print()
