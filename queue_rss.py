#!/usr/bin/python
# Generate two rss feeds for a directory with .changes file

# License: GPL v2 or later
# Author: Filippo Giunchedi <filippo@debian.org>
# Version: 0.4

import os
import os.path
import cPickle
import sys
import encodings.ascii
from email.Parser import HeaderParser
from optparse import OptionParser
from datetime import datetime

import PyRSS2Gen

from debian_bundle.deb822 import Changes

inrss_filename = "changes_in.rss"
outrss_filename = "changes_out.rss"
db_filename = "status.db"

parser = OptionParser()
parser.set_defaults(queuedir="queue", outdir="out", datadir="status", max_entries="30")

parser.add_option("-q", "--queuedir", dest="queuedir",
        help="The queue dir (%default)")
parser.add_option("-o", "--outdir", dest="outdir",
        help="The output directory (%default)")
parser.add_option("-d", "--datadir", dest="datadir",
        help="The data dir (%default)")
parser.add_option("-m", "--max-entries", dest="max_entries", type="int",
        help="Max number of entries to keep (%default)")

class Status:
    def __init__(self):
        self.feed_in = PyRSS2Gen.RSS2(
                       title = "Packages entering NEW",
                       link = "http://ftp-master.debian.org/new.html",
                       description = "Debian packages entering the NEW queue" )

        self.feed_out = PyRSS2Gen.RSS2(
                       title = "Packages leaving NEW",
                       link = "http://ftp-master.debian.org/new.html",
                       description = "Debian packages leaving the NEW queue" )

        self.queue = {}

def utf2ascii(src):
    """ Return an ASCII encoded copy of the input UTF-8 string """
    try:
        res = unicode(src, 'utf-8').encode('ascii', 'replace')
    except UnicodeDecodeError:
        res = None
    return res

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
                         'Date', 'Maintainer', 'Description', 'Changes'])

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

def add_rss_item(status, msg, direction):
    if direction == "in":
        feed = status.feed_in
        title = "%s %s entered NEW" % (msg['Source'], msg['Version'])
        pubdate = msg['Date']
    elif direction == "out":
        feed = status.feed_out
        title = "%s %s left NEW" % (msg['Source'], msg['Version'])
        pubdate = datetime.utcnow()
    else:
        return False

    description = "<pre>Description: %s\nChanges: %s\n</pre>" % \
            (utf2ascii(msg['Description']), utf2ascii(msg['Changes']))

    feed.items.insert(0,
        PyRSS2Gen.RSSItem(
            title,
            pubDate = pubdate,
            description = description,
            author = utf2ascii(msg['Maintainer']),
            link = "http://ftp-master.debian.org/new/%s_%s.html" % \
                    (msg['Source'], msg['Version'])
        )
    )

def update_feeds(curqueue, status):
    # inrss -> append all items in curqueue not in status.queue
    # outrss -> append all items in status.queue not in curqueue

    for (name, parsed) in curqueue.items():
        if not status.queue.has_key(name):
            # new package
            add_rss_item(status, parsed, "in")

    for (name, parsed) in status.queue.items():
        if not curqueue.has_key(name):
            # removed package
            add_rss_item(status, parsed, "out")



if __name__ == "__main__":

    (settings, args) = parser.parse_args()

    if not os.path.exists(settings.outdir):
        sys.stderr.write("Outdir '%s' does not exists\n" % settings.outdir)
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(settings.datadir):
        sys.stderr.write("Datadir '%s' does not exists\n" % settings.datadir)
        parser.print_help()
        sys.exit(1)

    status_db = os.path.join(settings.datadir, db_filename)

    try:
        status = cPickle.load(open(status_db))
    except IOError:
        status = Status()

    current_queue = parse_queuedir(settings.queuedir)
    if not current_queue:
        sys.stderr.write("Unable to scan queuedir '%s'\n" % settings.queuedir)
        parser.print_help()
        sys.exit(1)

    update_feeds(current_queue, status)

    purge_old_items(status.feed_in, settings.max_entries)
    purge_old_items(status.feed_out, settings.max_entries)

    feed_in_file = os.path.join(settings.outdir, inrss_filename)
    feed_out_file = os.path.join(settings.outdir, outrss_filename)

    try:
        status.feed_in.write_xml(file(feed_in_file, "w+"), "utf-8")
        status.feed_out.write_xml(file(feed_out_file, "w+"), "utf-8")
    except IOError, why:
        sys.stderr.write("Unable to write feeds: %s\n", why)
        sys.exit(1)

    status.queue = current_queue

    try:
        cPickle.dump(status, open(status_db, "w+"))
    except IOError, why:
        sys.stderr.write("Unable to save status: %s\n", why)
        sys.exit(1)

# vim:et:ts=4
