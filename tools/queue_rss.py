#! /usr/bin/env python3
# Generate two rss feeds for a directory with .changes file

# License: GPL v2 or later
# Author: Filippo Giunchedi <filippo@debian.org>
# Version: 0.5

import html
import os
import os.path
import pickle
import re
import sys
import time
from optparse import OptionParser
from datetime import datetime
from email.utils import parseaddr

import PyRSS2Gen

from debian.deb822 import Changes

inrss_filename = "NEW_in.rss"
outrss_filename = "NEW_out.rss"
db_filename = "status.db"

parser = OptionParser()
parser.set_defaults(queuedir="queue", outdir="out", datadir="status",
                    logdir="log", max_entries="30")

parser.add_option("-q", "--queuedir", dest="queuedir",
        help="The queue dir (%default)")
parser.add_option("-o", "--outdir", dest="outdir",
        help="The output directory (%default)")
parser.add_option("-d", "--datadir", dest="datadir",
        help="The data dir (%default)")
parser.add_option("-l", "--logdir", dest="logdir",
        help="The ACCEPT/REJECT dak log dir (%default)")
parser.add_option("-m", "--max-entries", dest="max_entries", type="int",
        help="Max number of entries to keep (%default)")


class Status:
    def __init__(self):
        self.feed_in = PyRSS2Gen.RSS2(
                       title="Packages entering NEW",
                       link="https://ftp-master.debian.org/new.html",
                       description="Debian packages entering the NEW queue")

        self.feed_out = PyRSS2Gen.RSS2(
                       title="Packages leaving NEW",
                       link="https://ftp-master.debian.org/new.html",
                       description="Debian packages leaving the NEW queue")

        self.queue = {}


def purge_old_items(feed, max):
    """ Purge RSSItem from feed, no more than max. """
    if feed.items is None or len(feed.items) == 0:
        return False

    feed.items = feed.items[:max]
    return True


def parse_changes(fname):
    """ Parse a .changes file named fname.

    Return {fname: parsed} """

    m = Changes(open(fname))

    wanted_fields = set(['Source', 'Version', 'Architecture', 'Distribution',
                         'Date', 'Changed-By', 'Description', 'Changes'])

    if not set(m.keys()).issuperset(wanted_fields):
        return None

    return {os.path.basename(fname): m}


def parse_queuedir(dir):
    """ Parse dir for .changes files.

    Return a dictionary {filename: parsed_file}"""

    if not os.path.exists(dir):
        return None

    res = {}
    for fname in os.listdir(dir):
        if not fname.endswith(".changes"):
            continue

        parsed = parse_changes(os.path.join(dir, fname))
        if parsed:
            res.update(parsed)

    return res


def parse_leave_reason(fname):
    """ Parse a dak log file fname for ACCEPT/REJECT reason from process-new.

    Return a dictionary {filename: reason}"""

    reason_re = re.compile(r".+\|process-new\|(.+)\|NEW (ACCEPT|REJECT)\|(\S+)")

    try:
        f = open(fname)
    except IOError as e:
        print("Can't open %s: %s" % (fname, e), file=sys.stderr)
        return {}

    res = {}
    for l in f.readlines():
        m = reason_re.search(l)
        if m:
            res[m.group(3)] = (m.group(2), m.group(1))

    f.close()
    return res


def add_rss_item(status, msg, direction):
    if direction == "in":
        feed = status.feed_in
        title = "%s %s entered NEW" % (msg['Source'], msg['Version'])
        pubdate = msg['Date']
    elif direction == "out":
        feed = status.feed_out
        if 'Leave-Reason' in msg:
            title = "%s %s left NEW (%s)" % (msg['Source'], msg['Version'],
                                             msg['Leave-Reason'][0])
        else:
            title = "%s %s left NEW" % (msg['Source'], msg['Version'])

        pubdate = datetime.utcnow()
    else:
        return False

    description = "<pre>Description: %s\nChanges: %s\n</pre>" % \
            (html.escape(msg['Description']),
             html.escape(msg['Changes']))

    link = "https://ftp-master.debian.org/new/%s_%s.html" % \
            (msg['Source'], msg['Version'])
    guid = msg['Checksums-Sha256'][0]['sha256']

    if 'Processed-By' in msg:
        author = msg['Processed-By']
    else:
        changedby = parseaddr(msg['Changed-By'])
        author = "%s (%s)" % (changedby[1], changedby[0])

    feed.items.insert(0,
        PyRSS2Gen.RSSItem(
            title,
            pubDate=pubdate,
            description=description,
            author=html.escape(author),
            link=link,
            guid=guid
        )
    )


def update_feeds(curqueue, status, settings):
    # inrss -> append all items in curqueue not in status.queue
    # outrss -> append all items in status.queue not in curqueue

    leave_reason = None
    # logfile from dak's process-new
    reason_log = os.path.join(settings.logdir, time.strftime("%Y-%m"))

    for (name, parsed) in curqueue.items():
        if name not in status.queue:
            # new package
            add_rss_item(status, parsed, "in")

    for (name, parsed) in status.queue.items():
        if name not in curqueue:
            # removed package, try to find out why
            if leave_reason is None:
                leave_reason = parse_leave_reason(reason_log)
            if leave_reason and name in leave_reason:
                parsed['Leave-Reason'] = leave_reason[name][0]
                parsed['Processed-By'] = leave_reason[name][1] + "@debian.org"
            add_rss_item(status, parsed, "out")


if __name__ == "__main__":

    (settings, args) = parser.parse_args()

    if not os.path.exists(settings.outdir):
        print("Outdir '%s' does not exists" % settings.outdir, file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(settings.datadir):
        print("Datadir '%s' does not exists" % settings.datadir, file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    status_db = os.path.join(settings.datadir, db_filename)

    try:
        with open(status_db, 'rb') as fh:
            try:
                status = pickle.load(fh, encoding="utf-8")
            except UnicodeDecodeError:
                fh.seek(0)
                status = pickle.load(fh, encoding="latin-1")
    except IOError:
        status = Status()

    current_queue = parse_queuedir(settings.queuedir)

    update_feeds(current_queue, status, settings)

    purge_old_items(status.feed_in, settings.max_entries)
    purge_old_items(status.feed_out, settings.max_entries)

    feed_in_file = os.path.join(settings.outdir, inrss_filename)
    feed_out_file = os.path.join(settings.outdir, outrss_filename)

    try:
        status.feed_in.write_xml(open(feed_in_file, "w+"), "utf-8")
        status.feed_out.write_xml(open(feed_out_file, "w+"), "utf-8")
    except IOError as why:
        print("Unable to write feeds:", why, file=sys.stderr)
        sys.exit(1)

    status.queue = current_queue

    try:
        with open(status_db, 'wb+') as fh:
            pickle.dump(status, fh)
    except IOError as why:
        print("Unable to save status:", why, file=sys.stderr)
        sys.exit(1)

# vim:et:ts=4
