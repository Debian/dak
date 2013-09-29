#!/usr/bin/env python

""" Various statistical pr0nography fun and games """
# Copyright (C) 2000, 2001, 2002, 2003, 2006  James Troup <james@nocrew.org>
# Copyright (C) 2013  Luca Falavigna <dktrkranz@debian.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

################################################################################

# <aj>    can we change the standards instead?
# <neuro> standards?
# <aj>    whatever we're not conforming to
# <aj>    if there's no written standard, why don't we declare linux as
#         the defacto standard
# <aj>    go us!

# [aj's attempt to avoid ABI changes for released architecture(s)]

################################################################################

import sys
import apt_pkg

from datetime import datetime
from email.utils import mktime_tz, parsedate_tz
from mailbox import mbox
from os import listdir, system, unlink
from os.path import isfile, join, splitext
from re import findall, DOTALL, MULTILINE
from sys import stderr
from yaml import safe_load, safe_dump

from daklib import utils
from daklib.dbconn import DBConn, get_suite_architectures, Suite, Architecture

################################################################################

Cnf = None

stats = {}
users = {}
buffer = 0
FORMAT_SWITCH = '2009-08'
blacklisted = ('dak', 'katie')

NEW = ('^(\d{14})\|(?:jennifer|process-unchecked|.*?\|dak)'
       '\|(Moving to new|ACCEPT-TO-NEW)')
new_ACTIONS = '^(\d{14})\|[^\|]*\|(\S+)\|NEW (\S+)[:\|]'
old_ACTIONS = ('(?:lisa|process-new)\|program start\|(.*?)\|'
               '(?:lisa|process-new)\|program end')
old_ACTION = '^(\d{14})\|(?:lisa|process-new)\|(Accepting changes|rejected)\|'

################################################################################

def usage(exit_code=0):
    print """Usage: dak stats MODE
Print various stats.

  -h, --help                show this help and exit.

The following MODEs are available:

  arch-space    - displays space used by each architecture
  pkg-nums      - displays the number of packages by suite/architecture
  daily-install - displays daily install stats suitable for graphing
  new           - stores stats about the NEW queue
"""
    sys.exit(exit_code)

################################################################################

def per_arch_space_use():
    session = DBConn().session()
    q = session.execute("""
SELECT a.arch_string as Architecture, sum(f.size) AS sum
  FROM files f, binaries b, architecture a
  WHERE a.id=b.architecture AND f.id=b.file
  GROUP BY a.arch_string ORDER BY sum""").fetchall()
    for j in q:
        print "%-15.15s %s" % (j[0], j[1])
    print
    q = session.execute("SELECT sum(size) FROM files WHERE filename ~ '.(diff.gz|tar.gz|dsc)$'").fetchall()
    print "%-15.15s %s" % ("Source", q[0][0])

################################################################################

def daily_install_stats():
    stats = {}
    f = utils.open_file("2001-11")
    for line in f.readlines():
        split = line.strip().split('|')
        program = split[1]
        if program != "katie" and program != "process-accepted":
            continue
        action = split[2]
        if action != "installing changes" and action != "installed":
            continue
        date = split[0][:8]
        if not stats.has_key(date):
            stats[date] = {}
            stats[date]["packages"] = 0
            stats[date]["size"] = 0.0
        if action == "installing changes":
            stats[date]["packages"] += 1
        elif action == "installed":
            stats[date]["size"] += float(split[5])

    dates = stats.keys()
    dates.sort()
    for date in dates:
        packages = stats[date]["packages"]
        size = int(stats[date]["size"] / 1024.0 / 1024.0)
        print "%s %s %s" % (date, packages, size)

################################################################################

def longest(list):
    longest = 0
    for i in list:
        l = len(i)
        if l > longest:
            longest = l
    return longest

def output_format(suite):
    output_suite = []
    for word in suite.split("-"):
        output_suite.append(word[0])
    return "-".join(output_suite)

def number_of_packages():
    arches = {}
    arch_ids = {}
    suites = {}
    suite_ids = {}
    d = {}
    session = DBConn().session()
    # Build up suite mapping
    for i in session.query(Suite).all():
        suites[i.suite_id] = i.suite_name
        suite_ids[i.suite_name] = i.suite_id
    # Build up architecture mapping
    for i in session.query(Architecture).all():
        arches[i.arch_id] = i.arch_string
        arch_ids[i.arch_string] = i.arch_id
    # Pre-create the dictionary
    for suite_id in suites.keys():
        d[suite_id] = {}
        for arch_id in arches.keys():
            d[suite_id][arch_id] = 0
    # Get the raw data for binaries
    # Simultate 'GROUP by suite, architecture' with a dictionary
    # XXX: Why don't we just get the DB to do this?
    for i in session.execute("""SELECT suite, architecture, COUNT(suite)
                                FROM bin_associations
                           LEFT JOIN binaries ON bin = binaries.id
                            GROUP BY suite, architecture""").fetchall():
        d[ i[0] ][ i[1] ] = i[2]
    # Get the raw data for source
    arch_id = arch_ids["source"]
    for i in session.execute('SELECT suite, COUNT(suite) FROM src_associations GROUP BY suite').fetchall():
        (suite_id, count) = i
        d[suite_id][arch_id] = d[suite_id][arch_id] + count
    ## Print the results
    # Setup
    suite_list = suites.values()
    suite_id_list = []
    suite_arches = {}
    for suite in suite_list:
        suite_id = suite_ids[suite]
        suite_arches[suite_id] = {}
        for arch in get_suite_architectures(suite):
            suite_arches[suite_id][arch.arch_string] = ""
        suite_id_list.append(suite_id)
    output_list = [ output_format(i) for i in suite_list ]
    longest_suite = longest(output_list)
    arch_list = arches.values()
    arch_list.sort()
    longest_arch = longest(arch_list)
    # Header
    output = (" "*longest_arch) + " |"
    for suite in output_list:
        output = output + suite.center(longest_suite)+" |"
    output = output + "\n"+(len(output)*"-")+"\n"
    # per-arch data
    arch_list = arches.values()
    arch_list.sort()
    longest_arch = longest(arch_list)
    for arch in arch_list:
        arch_id = arch_ids[arch]
        output = output + arch.center(longest_arch)+" |"
        for suite_id in suite_id_list:
            if suite_arches[suite_id].has_key(arch):
                count = "%d" % d[suite_id][arch_id]
            else:
                count = "-"
            output = output + count.rjust(longest_suite)+" |"
        output = output + "\n"
    print output

################################################################################

def parse_new_uploads(data):
    global stats
    latest_timestamp = stats['timestamp']
    for entry in findall(NEW, data, MULTILINE):
        timestamp = entry[0]
        if stats['timestamp'] >= timestamp:
            continue
        date = parse_timestamp(timestamp)
        if date not in stats:
            stats[date] = {'stats': {'NEW': 0, 'ACCEPT': 0,
                           'REJECT': 0, 'PROD': 0}, 'members': {}}
        stats[date]['stats']['NEW'] += 1
        stats['history']['stats']['NEW'] += 1
        latest_timestamp = timestamp
    return latest_timestamp


def parse_actions(data, logdate):
    global stats
    latest_timestamp = stats['timestamp']
    if logdate <= FORMAT_SWITCH:
        for batch in findall(old_ACTIONS, data, DOTALL):
            who = batch.split()[0]
            if who in blacklisted:
                continue
            for entry in findall(old_ACTION, batch, MULTILINE):
                action = entry[1]
                if action.startswith('Accepting'):
                    action = 'ACCEPT'
                elif action.startswith('rejected'):
                    action = 'REJECT'
                timestamp = entry[0]
                if stats['timestamp'] >= timestamp:
                    continue
                date = parse_timestamp(entry[0])
                if date not in stats:
                    stats[date] = {'stats': {'NEW': 0, 'ACCEPT': 0,
                                   'REJECT': 0, 'PROD': 0}, 'members': {}}
                stats[date]['stats'][action] += 1
                stats['history']['stats'][action] += 1
                if who not in stats[date]['members']:
                    stats[date]['members'][who] = {'ACCEPT': 0, 'REJECT': 0,
                                                   'PROD': 0}
                stats[date]['members'][who][action] += 1
                if who not in stats['history']['members']:
                    stats['history']['members'][who] = {'ACCEPT': 0, 'REJECT': 0,
                                                    'PROD': 0}
                stats['history']['members'][who][action] += 1
                latest_timestamp = timestamp
        parse_prod(logdate)
    if logdate >= FORMAT_SWITCH:
        for entry in findall(new_ACTIONS, data, MULTILINE):
            action = entry[2]
            timestamp = entry[0]
            if stats['timestamp'] >= timestamp:
                continue
            date = parse_timestamp(timestamp)
            if date not in stats:
                stats[date] = {'stats': {'NEW': 0, 'ACCEPT': 0,
                               'REJECT': 0, 'PROD': 0}, 'members': {}}
            member = entry[1]
            if member in blacklisted:
                continue
            if date not in stats:
                stats[date] = {'stats': {'NEW': 0, 'ACCEPT': 0,
                               'REJECT': 0, 'PROD': 0}, 'members': {}}
            if member not in stats[date]['members']:
                stats[date]['members'][member] = {'ACCEPT': 0, 'REJECT': 0,
                                                  'PROD': 0}
            if member not in stats['history']['members']:
                stats['history']['members'][member] = {'ACCEPT': 0,
                                                       'REJECT': 0, 'PROD': 0}
            stats[date]['stats'][action] += 1
            stats[date]['members'][member][action] += 1
            stats['history']['stats'][action] += 1
            stats['history']['members'][member][action] += 1
            latest_timestamp = timestamp
    return latest_timestamp


def parse_prod(logdate):
    global stats
    global users
    maildate = ''.join([x[-2:] for x in logdate.split('-')])
    mailarchive = join(utils.get_conf()['Dir::Base'], 'mail/archive',
                       'mail-%s.xz' % maildate)
    if not isfile(mailarchive):
        return
    (fd, tmpfile) = utils.temp_filename(utils.get_conf()['Dir::TempPath'])
    system('xzcat %s > %s' % (mailarchive, tmpfile))
    for message in mbox(tmpfile):
        if (message['subject'] and
                message['subject'].startswith('Comments regarding')):
            try:
                member = users[' '.join(message['From'].split()[:-1])]
            except KeyError:
                continue
            ts = mktime_tz(parsedate_tz(message['date']))
            timestamp = datetime.fromtimestamp(ts).strftime("%Y%m%d%H%M%S")
            date = parse_timestamp(timestamp)
            if date not in stats:
                stats[date] = {'stats': {'NEW': 0, 'ACCEPT': 0,
                                 'REJECT': 0, 'PROD': 0}, 'members': {}}
            if member not in stats[date]['members']:
                stats[date]['members'][member] = {'ACCEPT': 0, 'REJECT': 0,
                                                     'PROD': 0}
            if member not in stats['history']['members']:
                stats['history']['members'][member] = {'ACCEPT': 0,
                                                       'REJECT': 0, 'PROD': 0}
            stats[date]['stats']['PROD'] += 1
            stats[date]['members'][member]['PROD'] += 1
            stats['history']['stats']['PROD'] += 1
            stats['history']['members'][member]['PROD'] += 1
    unlink(tmpfile)


def parse_timestamp(timestamp):
    y = int(timestamp[:4])
    m = int(timestamp[4:6])
    return '%d-%02d' % (y, m)


def new_stats(logdir, yaml):
    global Cnf
    global stats
    try:
        with open(yaml, 'r') as fd:
            stats = safe_load(fd)
    except IOError:
        pass
    if not stats:
        stats = {'history': {'stats': {'NEW': 0, 'ACCEPT': 0,
                 'REJECT': 0, 'PROD': 0}, 'members': {}},
                 'timestamp': '19700101000000'}
    latest_timestamp = stats['timestamp']
    for fn in sorted(listdir(logdir)):
        if fn == 'current':
            continue
        log = splitext(fn)[0]
        if log < parse_timestamp(stats['timestamp']):
            continue
        logfile = join(logdir, fn)
        if isfile(logfile):
            if fn.endswith('.bz2'):
                # This hack is required becaue python2 does not support
                # multi-stream files (http://bugs.python.org/issue1625)
                (fd, tmpfile) = utils.temp_filename(Cnf['Dir::TempPath'])
                system('bzcat %s > %s' % (logfile, tmpfile))
                with open(tmpfile, 'r') as fd:
                    data = fd.read()
                unlink(tmpfile)
            else:
                with open(logfile, 'r') as fd:
                    data = fd.read()
            ts = parse_new_uploads(data)
            if ts > latest_timestamp:
                latest_timestamp = ts
            ts = parse_actions(data, log)
            if ts > latest_timestamp:
                latest_timestamp = ts
            stderr.write('.')
            stderr.flush()
    stderr.write('\n')
    stderr.flush()
    stats['timestamp'] = latest_timestamp
    with open(yaml, 'w') as fd:
        safe_dump(stats, fd)

################################################################################

def main ():
    global Cnf
    global users

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Stats::Options::Help")]
    for i in [ "help" ]:
        if not Cnf.has_key("Stats::Options::%s" % (i)):
            Cnf["Stats::Options::%s" % (i)] = ""

    args = apt_pkg.parse_commandline(Cnf, Arguments, sys.argv)

    Options = Cnf.subtree("Stats::Options")
    if Options["Help"]:
        usage()

    if len(args) < 1:
        utils.warn("dak stats requires a MODE argument")
        usage(1)
    elif len(args) > 1:
        if args[0].lower() != "new":
            utils.warn("dak stats accepts only one MODE argument")
            usage(1)
    elif args[0].lower() == "new":
            utils.warn("new MODE requires an output file")
            usage(1)
    mode = args[0].lower()

    if mode == "arch-space":
        per_arch_space_use()
    elif mode == "pkg-nums":
        number_of_packages()
    elif mode == "daily-install":
        daily_install_stats()
    elif mode == "new":
        users = utils.get_users_from_ldap()
        new_stats(Cnf["Dir::Log"], args[1])
    else:
        utils.warn("unknown mode '%s'" % (mode))
        usage(1)

################################################################################

if __name__ == '__main__':
    main()
