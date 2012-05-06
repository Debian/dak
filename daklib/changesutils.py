#!/usr/bin/env python
# vim:set et ts=4 sw=4:

"""Utilities for handling changes files

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009 Joerg Jaspert <joerg@debian.org>
@copyright: 2009 Frank Lichtenheld <djpig@debian.org>
@license: GNU General Public License version 2 or later
"""
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

import copy
import os
import stat
import apt_pkg

from daklib.dbconn import *
from daklib.queue import *
from daklib import utils
from daklib.config import Config

################################################################################

__all__ = []

################################################################################

def indiv_sg_compare (a, b):
    """Sort by source name, source, version, 'have source', and
       finally by filename."""
    # Sort by source version
    q = apt_pkg.version_compare(a["version"], b["version"])
    if q:
        return -q

    # Sort by 'have source'
    a_has_source = a["architecture"].get("source")
    b_has_source = b["architecture"].get("source")
    if a_has_source and not b_has_source:
        return -1
    elif b_has_source and not a_has_source:
        return 1

    return cmp(a["filename"], b["filename"])

__all__.append('indiv_sg_compare')

############################################################

def sg_compare (a, b):
    a = a[1]
    b = b[1]
    """Sort by have note, source already in database and time of oldest upload."""
    # Sort by have note
    a_note_state = a["note_state"]
    b_note_state = b["note_state"]
    if a_note_state < b_note_state:
        return -1
    elif a_note_state > b_note_state:
        return 1
    # Sort by source already in database (descending)
    source_in_database = cmp(a["source_in_database"], b["source_in_database"])
    if source_in_database:
        return -source_in_database

    # Sort by time of oldest upload
    return cmp(a["oldest"], b["oldest"])

__all__.append('sg_compare')

def sort_changes(changes_files, session, binaries = None):
    """Sort into source groups, then sort each source group by version,
    have source, filename.  Finally, sort the source groups by have
    note, time of oldest upload of each source upload."""
    if len(changes_files) == 1:
        return changes_files

    sorted_list = []
    cache = {}
    # Read in all the .changes files
    for filename in changes_files:
        u = Upload()
        try:
            u.pkg.changes_file = filename
            u.load_changes(filename)
            u.update_subst()
            cache[filename] = copy.copy(u.pkg.changes)
            cache[filename]["filename"] = filename
        except:
            sorted_list.append(filename)
            break
    # Divide the .changes into per-source groups
    per_source = {}
    for filename in cache.keys():
        source = cache[filename]["source"]
        if not per_source.has_key(source):
            per_source[source] = {}
            per_source[source]["list"] = []
        per_source[source]["list"].append(cache[filename])
    # Determine oldest time and have note status for each source group
    for source in per_source.keys():
        q = session.query(DBSource).filter_by(source = source).all()
        per_source[source]["source_in_database"] = binaries and -(len(q)>0) or len(q)>0
        source_list = per_source[source]["list"]
        first = source_list[0]
        oldest = os.stat(first["filename"])[stat.ST_MTIME]
        have_note = 0
        for d in per_source[source]["list"]:
            mtime = os.stat(d["filename"])[stat.ST_MTIME]
            if mtime < oldest:
                oldest = mtime
            have_note += has_new_comment(d["source"], d["version"], session)
        per_source[source]["oldest"] = oldest
        if not have_note:
            per_source[source]["note_state"] = 0; # none
        elif have_note < len(source_list):
            per_source[source]["note_state"] = 1; # some
        else:
            per_source[source]["note_state"] = 2; # all
        per_source[source]["list"].sort(indiv_sg_compare)
    per_source_items = per_source.items()
    per_source_items.sort(sg_compare)
    for i in per_source_items:
        for j in i[1]["list"]:
            sorted_list.append(j["filename"])
    return sorted_list

__all__.append('sort_changes')

################################################################################

def changes_to_queue(upload, srcqueue, destqueue, session):
    """Move a changes file to a different queue and mark as approved for the
       source queue"""

    try:
        chg = session.query(DBChange).filter_by(changesname=os.path.basename(upload.pkg.changes_file)).one()
    except NoResultFound:
        return False

    chg.approved_for_id = srcqueue.policy_queue_id

    for f in chg.files:
        # update the changes_pending_files row
        f.queue = destqueue
        # Only worry about unprocessed files
        if not f.processed:
            utils.move(os.path.join(srcqueue.path, f.filename), destqueue.path, perms=int(destqueue.perms, 8))

    utils.move(os.path.join(srcqueue.path, upload.pkg.changes_file), destqueue.path, perms=int(destqueue.perms, 8))
    chg.in_queue = destqueue
    session.commit()

    return True

__all__.append('changes_to_queue')

def new_accept(upload, dry_run, session):
    print "ACCEPT"

    if not dry_run:
        cnf = Config()

        (summary, short_summary) = upload.build_summaries()
        destqueue = get_policy_queue('newstage', session)

        srcqueue = get_policy_queue_from_path(upload.pkg.directory, session)

        if not srcqueue:
            # Assume NEW and hope for the best
            srcqueue = get_policy_queue('new', session)

        changes_to_queue(upload, srcqueue, destqueue, session)

__all__.append('new_accept')
