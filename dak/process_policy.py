#! /usr/bin/env python3
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
from sqlalchemy.orm.exc import NoResultFound
import sqlalchemy.sql as sql

from daklib.dbconn import *
from daklib import daklog
from daklib import utils
from daklib.externalsignature import check_upload_for_external_signature_request
from daklib.config import Config
from daklib.archive import ArchiveTransaction, source_component_from_package_list
from daklib.urgencylog import UrgencyLog
from daklib.packagelist import PackageList

import daklib.announce
import daklib.upload
import daklib.utils

# Globals
Options = None
Logger = None

################################################################################


def do_comments(dir, srcqueue, opref, npref, line, fn, transaction):
    session = transaction.session
    actions = []
    for comm in [x for x in os.listdir(dir) if x.startswith(opref)]:
        with open(os.path.join(dir, comm)) as fd:
            lines = fd.readlines()
        if len(lines) == 0 or lines[0] != line + "\n":
            continue

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
        print(("Processing changes file: {0}".format(u.changes.changesname)))
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
        else:
            transaction.rollback()
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
        section = db_binary.proxy['Section']
        component_name = 'main'
        if section.find('/') != -1:
            component_name = section.split('/', 1)[0]
        return get_mapped_component(component_name, session=session)

    def is_debug_binary(db_binary):
        return daklib.utils.is_in_debug_section(db_binary.proxy)

    def has_debug_binaries(upload):
        return any((is_debug_binary(x) for x in upload.binaries))

    def source_component_func(db_source):
        package_list = PackageList(db_source.proxy)
        component = source_component_from_package_list(package_list, upload.target_suite)
        if component is not None:
            return get_mapped_component(component.component_name, session=session)

        # Fallback for packages without Package-List field
        query = session.query(Override).filter_by(suite=overridesuite, package=db_source.source) \
            .join(OverrideType).filter(OverrideType.overridetype == 'dsc') \
            .join(Component)
        return query.one().component

    policy_queue = upload.target_suite.policy_queue
    if policy_queue == srcqueue:
        policy_queue = None

    all_target_suites = [upload.target_suite if policy_queue is None else policy_queue.suite]
    if policy_queue is None or policy_queue.send_to_build_queues:
        all_target_suites.extend([q.suite for q in upload.target_suite.copy_queues])

    throw_away_binaries = False
    if upload.source is not None:
        source_component = source_component_func(upload.source)
        if upload.target_suite.suite_name in cnf.value_list('Dinstall::ThrowAwayNewBinarySuites') and \
           source_component.component_name in cnf.value_list('Dinstall::ThrowAwayNewBinaryComponents'):
            throw_away_binaries = True

    for suite in all_target_suites:
        debug_suite = suite.debug_suite

        if upload.source is not None:
            # If we have Source in this upload, let's include it into
            # upload suite.
            transaction.copy_source(
                upload.source,
                suite,
                source_component,
                allow_tainted=allow_tainted,
            )

            if not throw_away_binaries:
                if debug_suite is not None and has_debug_binaries(upload):
                    # If we're handing a debug package, we also need to include the
                    # source in the debug suite as well.
                    transaction.copy_source(
                        upload.source,
                        debug_suite,
                        source_component_func(upload.source),
                        allow_tainted=allow_tainted,
                    )

        if not throw_away_binaries:
            for db_binary in upload.binaries:
                # Now, let's work out where to copy this guy to -- if it's
                # a debug binary, and the suite has a debug suite, let's go
                # ahead and target the debug suite rather then the stock
                # suite.
                copy_to_suite = suite
                if debug_suite is not None and is_debug_binary(db_binary):
                    copy_to_suite = debug_suite

                # build queues and debug suites may miss the source package
                # if this is a binary-only upload.
                if copy_to_suite != upload.target_suite:
                    transaction.copy_source(
                        db_binary.source,
                        copy_to_suite,
                        source_component_func(db_binary.source),
                        allow_tainted=allow_tainted,
                    )

                transaction.copy_binary(
                    db_binary,
                    copy_to_suite,
                    binary_component_func(db_binary),
                    allow_tainted=allow_tainted,
                    extra_archives=[upload.target_suite.archive],
                )

                check_upload_for_external_signature_request(session, suite, copy_to_suite, db_binary)

        suite.update_last_changed()

    # Copy .changes if needed
    if policy_queue is None and upload.target_suite.copychanges:
        src = os.path.join(upload.policy_queue.path, upload.changes.changesname)
        dst = os.path.join(upload.target_suite.path, upload.changes.changesname)
        fs.copy(src, dst, mode=upload.target_suite.archive.mode)

    # List of files in the queue directory
    queue_files = [changesname]
    chg = daklib.upload.Changes(upload.policy_queue.path, changesname, keyrings=[], require_signature=False)
    queue_files.extend(f.filename for f in chg.buildinfo_files)

    # TODO: similar code exists in archive.py's `ArchiveUpload._install_policy`
    if policy_queue is not None:
        # register upload in policy queue
        new_upload = PolicyQueueUpload()
        new_upload.policy_queue = policy_queue
        new_upload.target_suite = upload.target_suite
        new_upload.changes = upload.changes
        new_upload.source = upload.source
        new_upload.binaries = upload.binaries
        session.add(new_upload)
        session.flush()

        # copy .changes & similar to policy queue
        for fn in queue_files:
            src = os.path.join(upload.policy_queue.path, fn)
            dst = os.path.join(policy_queue.path, fn)
            transaction.fs.copy(src, dst, mode=policy_queue.change_perms)

    # Copy upload to Process-Policy::CopyDir
    # Used on security.d.o to sync accepted packages to ftp-master, but this
    # should eventually be replaced by something else.
    copydir = cnf.get('Process-Policy::CopyDir') or None
    if policy_queue is None and copydir is not None:
        mode = upload.target_suite.archive.mode
        if upload.source is not None:
            for f in [df.poolfile for df in upload.source.srcfiles]:
                dst = os.path.join(copydir, f.basename)
                if not os.path.exists(dst):
                    fs.copy(f.fullpath, dst, mode=mode)

        for db_binary in upload.binaries:
            f = db_binary.poolfile
            dst = os.path.join(copydir, f.basename)
            if not os.path.exists(dst):
                fs.copy(f.fullpath, dst, mode=mode)

        for fn in queue_files:
            src = os.path.join(upload.policy_queue.path, fn)
            dst = os.path.join(copydir, fn)
            # We check for `src` to exist as old uploads in policy queues
            # might still miss the `.buildinfo` files.
            if os.path.exists(src) and not os.path.exists(dst):
                fs.copy(src, dst, mode=mode)

    if policy_queue is None:
        utils.process_buildinfos(upload.policy_queue.path, chg.buildinfo_files,
                                 fs, Logger)

    if policy_queue is None and upload.source is not None and not Options['No-Action']:
        urgency = upload.changes.urgency
        # As per policy 5.6.17, the urgency can be followed by a space and a
        # comment.  Extract only the urgency from the string.
        if ' ' in urgency:
            urgency, comment = urgency.split(' ', 1)
        if urgency not in cnf.value_list('Urgency::Valid'):
            urgency = cnf['Urgency::Default']
        UrgencyLog().log(upload.source.source, upload.source.version, urgency)

    if policy_queue is None:
        print("  ACCEPT")
    else:
        print("  ACCEPT-TO-QUEUE")
    if not Options['No-Action']:
        Logger.log(["Policy Queue ACCEPT", srcqueue.queue_name, changesname])

    if policy_queue is None:
        pu = get_processed_upload(upload)
        daklib.announce.announce_accept(pu)

    # TODO: code duplication. Similar code is in process-upload.
    # Move .changes to done
    now = datetime.datetime.now()
    donedir = os.path.join(cnf['Dir::Done'], now.strftime('%Y/%m/%d'))
    if policy_queue is None:
        for fn in queue_files:
            src = os.path.join(upload.policy_queue.path, fn)
            if os.path.exists(src):
                dst = os.path.join(donedir, fn)
                dst = utils.find_next_free(dst)
                fs.copy(src, dst, mode=0o644)

    if throw_away_binaries and upload.target_suite.archive.use_morgue:
        morguesubdir = cnf.get("New::MorgueSubDir", 'new')

        utils.move_to_morgue(morguesubdir,
            [db_binary.poolfile.fullpath for db_binary in upload.binaries],
            fs, Logger)

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
    files = [af.path for af in session.query(ArchiveFile)
                  .filter_by(archive=upload.policy_queue.suite.archive)
                  .join(ArchiveFile.file)
                  .filter(PoolFile.file_id.in_([f.file_id for f in poolfiles]))]
    for byhand in upload.byhand:
        path = os.path.join(queuedir, byhand.filename)
        if os.path.exists(path):
            files.append(path)
    chg = daklib.upload.Changes(queuedir, changesname, keyrings=[], require_signature=False)
    for f in chg.buildinfo_files:
        path = os.path.join(queuedir, f.filename)
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

    print("  REJECT")
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

    chg = daklib.upload.Changes(queuedir, upload.changes.changesname, keyrings=[], require_signature=False)
    queue_files = [upload.changes.changesname]
    queue_files.extend(f.filename for f in chg.buildinfo_files)
    for fn in queue_files:
        # We check for `path` to exist as old uploads in policy queues
        # might still miss the `.buildinfo` files.
        path = os.path.join(queuedir, fn)
        if os.path.exists(path):
            fs.unlink(path)

    session.delete(upload)
    session.flush()

################################################################################


def get_processed_upload(upload):
    pu = daklib.announce.ProcessedUpload()

    pu.maintainer = upload.changes.maintainer
    pu.changed_by = upload.changes.changedby
    pu.fingerprint = upload.changes.fingerprint

    pu.suites = [upload.target_suite]
    pu.from_policy_suites = [upload.target_suite]

    changes_path = os.path.join(upload.policy_queue.path, upload.changes.changesname)
    with open(changes_path, 'r') as fd:
        pu.changes = fd.read()
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

    query = sql.text("""
       SELECT b.*
         FROM binaries b
         JOIN bin_associations ba ON b.id = ba.bin
        WHERE ba.suite = :suite_id
          AND NOT EXISTS (SELECT 1 FROM policy_queue_upload_binaries_map pqubm
                                   JOIN policy_queue_upload pqu ON pqubm.policy_queue_upload_id = pqu.id
                                  WHERE pqu.policy_queue_id = :policy_queue_id
                                    AND pqubm.binary_id = b.id)""")
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

    query = sql.text("""
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
                                    AND ba.suite = :suite_id)""")
    sources = session.query(DBSource).from_statement(query) \
        .params({'suite_id': policy_queue.suite_id, 'policy_queue_id': policy_queue.policy_queue_id})

    for source in sources:
        Logger.log(["removed source from policy queue", policy_queue.queue_name, source.source, source.version])
        transaction.remove_source(source, suite)

################################################################################


def usage(status=0):
    print("""Usage: dak process-policy QUEUE""")
    sys.exit(status)

################################################################################


def main():
    global Options, Logger

    cnf = Config()
    session = DBConn().session()

    Arguments = [('h', "help", "Process-Policy::Options::Help"),
                 ('n', "no-action", "Process-Policy::Options::No-Action")]

    for i in ["help", "no-action"]:
        key = "Process-Policy::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    queue_name = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.subtree("Process-Policy::Options")
    if Options["Help"]:
        usage()

    if len(queue_name) != 1:
        print("E: Specify exactly one policy queue")
        sys.exit(1)

    queue_name = queue_name[0]

    Logger = daklog.Logger("process-policy")
    if not Options["No-Action"]:
        urgencylog = UrgencyLog()

    with ArchiveTransaction() as transaction:
        session = transaction.session
        try:
            pq = session.query(PolicyQueue).filter_by(queue_name=queue_name).one()
        except NoResultFound:
            print("E: Cannot find policy queue %s" % queue_name)
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
