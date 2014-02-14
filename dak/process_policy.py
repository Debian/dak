#!/usr/bin/env python
# vim:set et ts=4 sw=4:

""" Handles packages from policy queues

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009 Joerg Jaspert <joerg@debian.org>
@copyright: 2009 Frank Lichtenheld <djpig@debian.org>
@copyright: 2009 Mark Hymers <mhy@debian.org>
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

# <mhy> So how do we handle that at the moment?
# <stew> Probably incorrectly.

################################################################################

import os
import datetime
import re
import sys
import traceback
import apt_pkg

from daklib.dbconn import *
from daklib import daklog
from daklib import utils
from daklib.dak_exceptions import CantOpenError, AlreadyLockedError, CantGetLockError
from daklib.config import Config
from daklib.archive import ArchiveTransaction
from daklib.urgencylog import UrgencyLog

import daklib.announce

# Globals
Options = None
Logger = None

################################################################################

def do_comments(dir, srcqueue, opref, npref, line, fn, transaction):
    session = transaction.session
    actions = []
    for comm in [ x for x in os.listdir(dir) if x.startswith(opref) ]:
        lines = open(os.path.join(dir, comm)).readlines()
        if len(lines) == 0 or lines[0] != line + "\n": continue

        # If the ACCEPT includes a _<arch> we only accept that .changes.
        # Otherwise we accept all .changes that start with the given prefix
        changes_prefix = comm[len(opref):]
        if changes_prefix.count('_') < 2:
            changes_prefix = changes_prefix + '_'
        else:
            changes_prefix = changes_prefix + '.changes'

        # We need to escape "_" as we use it with the LIKE operator (via the
        # SQLA startwith) later.
        changes_prefix = changes_prefix.replace("_", r"\_")

        uploads = session.query(PolicyQueueUpload).filter_by(policy_queue=srcqueue) \
            .join(PolicyQueueUpload.changes).filter(DBChange.changesname.startswith(changes_prefix)) \
            .order_by(PolicyQueueUpload.source_id)
        reason = "".join(lines[1:])
        actions.extend((u, reason) for u in uploads)

        if opref != npref:
            newcomm = npref + comm[len(opref):]
            newcomm = utils.find_next_free(os.path.join(dir, newcomm))
            transaction.fs.move(os.path.join(dir, comm), newcomm)

    actions.sort()

    for u, reason in actions:
        print("Processing changes file: {0}".format(u.changes.changesname))
        fn(u, srcqueue, reason, transaction)

################################################################################

def try_or_reject(function):
    def wrapper(upload, srcqueue, comments, transaction):
        try:
            function(upload, srcqueue, comments, transaction)
        except Exception as e:
            comments = 'An exception was raised while processing the package:\n{0}\nOriginal comments:\n{1}'.format(traceback.format_exc(), comments)
            try:
                transaction.rollback()
                real_comment_reject(upload, srcqueue, comments, transaction)
            except Exception as e:
                comments = 'In addition an exception was raised while trying to reject the upload:\n{0}\nOriginal rejection:\n{1}'.format(traceback.format_exc(), comments)
                transaction.rollback()
                real_comment_reject(upload, srcqueue, comments, transaction, notify=False)
        if not Options['No-Action']:
            transaction.commit()
    return wrapper

################################################################################

@try_or_reject
def comment_accept(upload, srcqueue, comments, transaction):
    for byhand in upload.byhand:
        path = os.path.join(srcqueue.path, byhand.filename)
        if os.path.exists(path):
            raise Exception('E: cannot ACCEPT upload with unprocessed byhand file {0}'.format(byhand.filename))

    cnf = Config()

    fs = transaction.fs
    session = transaction.session
    changesname = upload.changes.changesname
    allow_tainted = srcqueue.suite.archive.tainted

    # We need overrides to get the target component
    overridesuite = upload.target_suite
    if overridesuite.overridesuite is not None:
        overridesuite = session.query(Suite).filter_by(suite_name=overridesuite.overridesuite).one()

    def binary_component_func(db_binary):
        override = session.query(Override).filter_by(suite=overridesuite, package=db_binary.package) \
            .join(OverrideType).filter(OverrideType.overridetype == db_binary.binarytype) \
            .join(Component).one()
        return override.component

    def source_component_func(db_source):
        override = session.query(Override).filter_by(suite=overridesuite, package=db_source.source) \
            .join(OverrideType).filter(OverrideType.overridetype == 'dsc') \
            .join(Component).one()
        return override.component

    all_target_suites = [upload.target_suite]
    all_target_suites.extend([q.suite for q in upload.target_suite.copy_queues])

    for suite in all_target_suites:
        if upload.source is not None:
            transaction.copy_source(upload.source, suite, source_component_func(upload.source), allow_tainted=allow_tainted)
        for db_binary in upload.binaries:
            # build queues may miss the source package if this is a binary-only upload
            if suite != upload.target_suite:
                transaction.copy_source(db_binary.source, suite, source_component_func(db_binary.source), allow_tainted=allow_tainted)
            transaction.copy_binary(db_binary, suite, binary_component_func(db_binary), allow_tainted=allow_tainted, extra_archives=[upload.target_suite.archive])

    # Copy .changes if needed
    if upload.target_suite.copychanges:
        src = os.path.join(upload.policy_queue.path, upload.changes.changesname)
        dst = os.path.join(upload.target_suite.path, upload.changes.changesname)
        fs.copy(src, dst, mode=upload.target_suite.archive.mode)

    # Copy upload to Process-Policy::CopyDir
    # Used on security.d.o to sync accepted packages to ftp-master, but this
    # should eventually be replaced by something else.
    copydir = cnf.get('Process-Policy::CopyDir') or None
    if copydir is not None:
        mode = upload.target_suite.archive.mode
        if upload.source is not None:
            for f in [ df.poolfile for df in upload.source.srcfiles ]:
                dst = os.path.join(copydir, f.basename)
                if not os.path.exists(dst):
                    fs.copy(f.fullpath, dst, mode=mode)

        for db_binary in upload.binaries:
            f = db_binary.poolfile
            dst = os.path.join(copydir, f.basename)
            if not os.path.exists(dst):
                fs.copy(f.fullpath, dst, mode=mode)

        src = os.path.join(upload.policy_queue.path, upload.changes.changesname)
        dst = os.path.join(copydir, upload.changes.changesname)
        if not os.path.exists(dst):
            fs.copy(src, dst, mode=mode)

    if upload.source is not None and not Options['No-Action']:
        urgency = upload.changes.urgency
        if urgency not in cnf.value_list('Urgency::Valid'):
            urgency = cnf['Urgency::Default']
        UrgencyLog().log(upload.source.source, upload.source.version, urgency)

    print "  ACCEPT"
    if not Options['No-Action']:
        Logger.log(["Policy Queue ACCEPT", srcqueue.queue_name, changesname])

    pu = get_processed_upload(upload)
    daklib.announce.announce_accept(pu)

    # TODO: code duplication. Similar code is in process-upload.
    # Move .changes to done
    src = os.path.join(upload.policy_queue.path, upload.changes.changesname)
    now = datetime.datetime.now()
    donedir = os.path.join(cnf['Dir::Done'], now.strftime('%Y/%m/%d'))
    dst = os.path.join(donedir, upload.changes.changesname)
    dst = utils.find_next_free(dst)
    fs.copy(src, dst, mode=0o644)

    remove_upload(upload, transaction)

################################################################################

@try_or_reject
def comment_reject(*args):
    real_comment_reject(*args, manual=True)

def real_comment_reject(upload, srcqueue, comments, transaction, notify=True, manual=False):
    cnf = Config()

    fs = transaction.fs
    session = transaction.session
    changesname = upload.changes.changesname
    queuedir = upload.policy_queue.path
    rejectdir = cnf['Dir::Reject']

    ### Copy files to reject/

    poolfiles = [b.poolfile for b in upload.binaries]
    if upload.source is not None:
        poolfiles.extend([df.poolfile for df in upload.source.srcfiles])
    # Not beautiful...
    files = [ af.path for af in session.query(ArchiveFile) \
                  .filter_by(archive=upload.policy_queue.suite.archive) \
                  .join(ArchiveFile.file) \
                  .filter(PoolFile.file_id.in_([ f.file_id for f in poolfiles ])) ]
    for byhand in upload.byhand:
        path = os.path.join(queuedir, byhand.filename)
        if os.path.exists(path):
            files.append(path)
    files.append(os.path.join(queuedir, changesname))

    for fn in files:
        dst = utils.find_next_free(os.path.join(rejectdir, os.path.basename(fn)))
        fs.copy(fn, dst, link=True)

    ### Write reason

    dst = utils.find_next_free(os.path.join(rejectdir, '{0}.reason'.format(changesname)))
    fh = fs.create(dst)
    fh.write(comments)
    fh.close()

    ### Send mail notification

    if notify:
        rejected_by = None
        reason = comments

        # Try to use From: from comment file if there is one.
        # This is not very elegant...
        match = re.match(r"\AFrom: ([^\n]+)\n\n", comments)
        if match:
            rejected_by = match.group(1)
            reason = '\n'.join(comments.splitlines()[2:])

        pu = get_processed_upload(upload)
        daklib.announce.announce_reject(pu, reason, rejected_by)

    print "  REJECT"
    if not Options["No-Action"]:
        Logger.log(["Policy Queue REJECT", srcqueue.queue_name, upload.changes.changesname])

    changes = upload.changes
    remove_upload(upload, transaction)
    session.delete(changes)

################################################################################

def remove_upload(upload, transaction):
    fs = transaction.fs
    session = transaction.session
    changes = upload.changes

    # Remove byhand and changes files. Binary and source packages will be
    # removed from {bin,src}_associations and eventually removed by clean-suites automatically.
    queuedir = upload.policy_queue.path
    for byhand in upload.byhand:
        path = os.path.join(queuedir, byhand.filename)
        if os.path.exists(path):
            fs.unlink(path)
        session.delete(byhand)
    fs.unlink(os.path.join(queuedir, upload.changes.changesname))

    session.delete(upload)
    session.flush()

################################################################################

def get_processed_upload(upload):
    pu = daklib.announce.ProcessedUpload()

    pu.maintainer = upload.changes.maintainer
    pu.changed_by = upload.changes.changedby
    pu.fingerprint = upload.changes.fingerprint

    pu.suites = [ upload.target_suite ]
    pu.from_policy_suites = [ upload.target_suite ]

    changes_path = os.path.join(upload.policy_queue.path, upload.changes.changesname)
    pu.changes = open(changes_path, 'r').read()
    pu.changes_filename = upload.changes.changesname
    pu.sourceful = upload.source is not None
    pu.source = upload.changes.source
    pu.version = upload.changes.version
    pu.architecture = upload.changes.architecture
    pu.bugs = upload.changes.closes

    pu.program = "process-policy"

    return pu

################################################################################

def remove_unreferenced_binaries(policy_queue, transaction):
    """Remove binaries that are no longer referenced by an upload

    @type  policy_queue: L{daklib.dbconn.PolicyQueue}

    @type  transaction: L{daklib.archive.ArchiveTransaction}
    """
    session = transaction.session
    suite = policy_queue.suite

    query = """
       SELECT b.*
         FROM binaries b
         JOIN bin_associations ba ON b.id = ba.bin
        WHERE ba.suite = :suite_id
          AND NOT EXISTS (SELECT 1 FROM policy_queue_upload_binaries_map pqubm
                                   JOIN policy_queue_upload pqu ON pqubm.policy_queue_upload_id = pqu.id
                                  WHERE pqu.policy_queue_id = :policy_queue_id
                                    AND pqubm.binary_id = b.id)"""
    binaries = session.query(DBBinary).from_statement(query) \
        .params({'suite_id': policy_queue.suite_id, 'policy_queue_id': policy_queue.policy_queue_id})

    for binary in binaries:
        Logger.log(["removed binary from policy queue", policy_queue.queue_name, binary.package, binary.version])
        transaction.remove_binary(binary, suite)

def remove_unreferenced_sources(policy_queue, transaction):
    """Remove sources that are no longer referenced by an upload or a binary

    @type  policy_queue: L{daklib.dbconn.PolicyQueue}

    @type  transaction: L{daklib.archive.ArchiveTransaction}
    """
    session = transaction.session
    suite = policy_queue.suite

    query = """
       SELECT s.*
         FROM source s
         JOIN src_associations sa ON s.id = sa.source
        WHERE sa.suite = :suite_id
          AND NOT EXISTS (SELECT 1 FROM policy_queue_upload pqu
                                  WHERE pqu.policy_queue_id = :policy_queue_id
                                    AND pqu.source_id = s.id)
          AND NOT EXISTS (SELECT 1 FROM binaries b
                                   JOIN bin_associations ba ON b.id = ba.bin
                                  WHERE b.source = s.id
                                    AND ba.suite = :suite_id)"""
    sources = session.query(DBSource).from_statement(query) \
        .params({'suite_id': policy_queue.suite_id, 'policy_queue_id': policy_queue.policy_queue_id})

    for source in sources:
        Logger.log(["removed source from policy queue", policy_queue.queue_name, source.source, source.version])
        transaction.remove_source(source, suite)

################################################################################

def main():
    global Options, Logger

    cnf = Config()
    session = DBConn().session()

    Arguments = [('h',"help","Process-Policy::Options::Help"),
                 ('n',"no-action","Process-Policy::Options::No-Action")]

    for i in ["help", "no-action"]:
        if not cnf.has_key("Process-Policy::Options::%s" % (i)):
            cnf["Process-Policy::Options::%s" % (i)] = ""

    queue_name = apt_pkg.parse_commandline(cnf.Cnf,Arguments,sys.argv)

    if len(queue_name) != 1:
        print "E: Specify exactly one policy queue"
        sys.exit(1)

    queue_name = queue_name[0]

    Options = cnf.subtree("Process-Policy::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger("process-policy")
    if not Options["No-Action"]:
        urgencylog = UrgencyLog()

    with ArchiveTransaction() as transaction:
        session = transaction.session
        try:
            pq = session.query(PolicyQueue).filter_by(queue_name=queue_name).one()
        except NoResultFound:
            print "E: Cannot find policy queue %s" % queue_name
            sys.exit(1)

        commentsdir = os.path.join(pq.path, 'COMMENTS')
        # The comments stuff relies on being in the right directory
        os.chdir(pq.path)

        do_comments(commentsdir, pq, "REJECT.", "REJECTED.", "NOTOK", comment_reject, transaction)
        do_comments(commentsdir, pq, "ACCEPT.", "ACCEPTED.", "OK", comment_accept, transaction)
        do_comments(commentsdir, pq, "ACCEPTED.", "ACCEPTED.", "OK", comment_accept, transaction)

        remove_unreferenced_binaries(pq, transaction)
        remove_unreferenced_sources(pq, transaction)

    if not Options['No-Action']:
        urgencylog.close()

################################################################################

if __name__ == '__main__':
    main()
