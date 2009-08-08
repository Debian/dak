#!/usr/bin/env python

"""
Installs Debian packages from queue/accepted into the pool

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
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

###############################################################################

#    Cartman: "I'm trying to make the best of a bad situation, I don't
#              need to hear crap from a bunch of hippy freaks living in
#              denial.  Screw you guys, I'm going home."
#
#    Kyle: "But Cartman, we're trying to..."
#
#    Cartman: "uhh.. screw you guys... home."

###############################################################################

import errno
import fcntl
import os
import sys
from datetime import datetime
import re
import apt_pkg, commands

from daklib import daklog
from daklib import queue
from daklib import utils
from daklib.dbconn import *
from daklib.binary import copy_temporary_contents
from daklib.dak_exceptions import *
from daklib.regexes import re_default_answer, re_issource, re_fdnic
from daklib.urgencylog import UrgencyLog
from daklib.summarystats import SummaryStats

###############################################################################

Options = None
Logger = None

###############################################################################

def init():
    global Options

    # Initialize config and connection to db
    cnf = Config()
    DBConn()

    Arguments = [('a',"automatic","Dinstall::Options::Automatic"),
                 ('h',"help","Dinstall::Options::Help"),
                 ('n',"no-action","Dinstall::Options::No-Action"),
                 ('p',"no-lock", "Dinstall::Options::No-Lock"),
                 ('s',"no-mail", "Dinstall::Options::No-Mail"),
                 ('d',"directory", "Dinstall::Options::Directory", "HasArg")]

    for i in ["automatic", "help", "no-action", "no-lock", "no-mail",
              "version", "directory"]:
        if not cnf.has_key("Dinstall::Options::%s" % (i)):
            cnf["Dinstall::Options::%s" % (i)] = ""

    changes_files = apt_pkg.ParseCommandLine(cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Dinstall::Options")

    if Options["Help"]:
        usage()

    # If we have a directory flag, use it to find our files
    if cnf["Dinstall::Options::Directory"] != "":
        # Note that we clobber the list of files we were given in this case
        # so warn if the user has done both
        if len(changes_files) > 0:
            utils.warn("Directory provided so ignoring files given on command line")

        changes_files = utils.get_changes_files(cnf["Dinstall::Options::Directory"])

    return changes_files

###############################################################################

def usage (exit_code=0):
    print """Usage: dak process-accepted [OPTION]... [CHANGES]...
  -a, --automatic           automatic run
  -h, --help                show this help and exit.
  -n, --no-action           don't do anything
  -p, --no-lock             don't check lockfile !! for cron.daily only !!
  -s, --no-mail             don't send any mail
  -V, --version             display the version number and exit"""
    sys.exit(exit_code)

###############################################################################

def action (u, stable_queue=None, log_urgency=True):
    (summary, short_summary) = u.build_summaries()
    pi = u.package_info()

    (prompt, answer) = ("", "XXX")
    if Options["No-Action"] or Options["Automatic"]:
        answer = 'S'

    if len(u.rejects) > 0:
        print "REJECT\n" + pi
        prompt = "[R]eject, Skip, Quit ?"
        if Options["Automatic"]:
            answer = 'R'
    else:
        print "INSTALL to " + ", ".join(u.pkg.changes["distribution"].keys())
        print pi + summary,
        prompt = "[I]nstall, Skip, Quit ?"
        if Options["Automatic"]:
            answer = 'I'

    while prompt.find(answer) == -1:
        answer = utils.our_raw_input(prompt)
        m = re_default_answer.match(prompt)
        if answer == "":
            answer = m.group(1)
        answer = answer[:1].upper()

    if answer == 'R':
        u.do_unaccept()
        Logger.log(["unaccepted", u.pkg.changes_file])
    elif answer == 'I':
        if stable_queue:
            stable_install(u, summary, short_summary, stable_queue, log_urgency)
        else:
            install(u, log_urgency)
    elif answer == 'Q':
        sys.exit(0)


###############################################################################
def add_poolfile(filename, datadict, location_id, session):
    poolfile = PoolFile()
    poolfile.filename = filename
    poolfile.filesize = datadict["size"]
    poolfile.md5sum = datadict["md5sum"]
    poolfile.sha1sum = datadict["sha1sum"]
    poolfile.sha256sum = datadict["sha256sum"]
    poolfile.location_id = location_id

    session.add(poolfile)
    # Flush to get a file id (NB: This is not a commit)
    session.flush()

    return poolfile

def add_dsc_to_db(u, filename, session):
    entry = u.pkg.files[filename]
    source = DBSource()

    source.source = u.pkg.dsc["source"]
    source.version = u.pkg.dsc["version"] # NB: not files[file]["version"], that has no epoch
    source.maintainer_id = get_or_set_maintainer(u.pkg.dsc["maintainer"], session).maintainer_id
    source.changedby_id = get_or_set_maintainer(u.pkg.dsc["changed-by"], session).maintainer_id
    source.fingerprint_id = get_or_set_fingerprint(u.pkg.dsc["fingerprint"], session).fingerprint_id
    source.install_date = datetime.now().date()

    dsc_component = entry["component"]
    dsc_location_id = entry["location id"]

    source.dm_upload_allowed = (u.pkg.dsc.get("dm-upload-allowed", '') == "yes")

    # Set up a new poolfile if necessary
    if not entry.has_key("files id") or not entry["files id"]:
        filename = entry["pool name"] + filename
        poolfile = add_poolfile(filename, entry, dsc_location_id, session)
        entry["files id"] = poolfile.file_id

    source.poolfile_id = entry["files id"]
    session.add(source)
    session.flush()

    for suite_name in u.pkg.changes["distribution"].keys():
        sa = SrcAssociation()
        sa.source_id = source.source_id
        sa.suite_id = get_suite(suite_name).suite_id
        session.add(sa)

    session.flush()

    # Add the source files to the DB (files and dsc_files)
    dscfile = DSCFile()
    dscfile.source_id = source.source_id
    dscfile.poolfile_id = entry["files id"]
    session.add(dscfile)

    for dsc_file, dentry in u.pkg.dsc_files.keys():
        df = DSCFile()
        df.source_id = source.source_id

        # If the .orig.tar.gz is already in the pool, it's
        # files id is stored in dsc_files by check_dsc().
        files_id = dentry.get("files id", None)

        if files_id is None:
            filename = dentry["pool name"] + dsc_file

            (found, obj) = check_poolfile(filename, dentry["size"], dentry["md5sum"], dsc_location_id)
            # FIXME: needs to check for -1/-2 and or handle exception
            if found and obj is not None:
                files_id = obj.file_id

            # If still not found, add it
            if files_id is None:
                poolfile = add_poolfile(filename, dentry, dsc_location_id, session)
                files_id = poolfile.file_id

        df.poolfile_id = files_id
        session.add(df)

    session.flush()

    # Add the src_uploaders to the DB
    uploader_ids = [maintainer_id]
    if u.pkg.dsc.has_key("uploaders"):
        for up in u.pkg.dsc["uploaders"].split(","):
            up = up.strip()
            uploader_ids.append(get_or_set_maintainer(up, session).maintainer_id)

    added_ids = {}
    for up in uploader_ids:
        if added_ids.has_key(up):
            utils.warn("Already saw uploader %s for source %s" % (up, source.source))
            continue

        added_ids[u]=1

        su = SrcUploader()
        su.maintainer_id = up
        su.source_id = source_id
        session.add(su)

    session.flush()

    return dsc_component, dsc_location_id

def add_deb_to_db(u, filename, session):
    """
    Contrary to what you might expect, this routine deals with both
    debs and udebs.  That info is in 'dbtype', whilst 'type' is
    'deb' for both of them
    """
    cnf = Config()
    entry = u.pkg.files[filename]

    bin = DBBinary()
    bin.package = entry["package"]
    bin.version = entry["version"]
    bin.maintainer_id = get_or_set_maintainer(entry["maintainer"], session).maintainer_id
    bin.fingerprint_id = get_or_set_fingerprint(u.pkg.changes["fingerprint"], session).fingerprint_id
    bin.arch_id = get_architecture(entry["architecture"], session).arch_id
    bin.binarytype = entry["dbtype"]

    # Find poolfile id
    filename = entry["pool name"] + filename
    if not entry.get("location id", None):
        entry["location id"] = get_location(cnf["Dir::Pool"], entry["component"], utils.where_am_i(), session).location_id

    if not entry.get("files id", None):
        poolfile = add_poolfile(filename, entry, entry["location id"], session)
        entry["files id"] = poolfile.file_id

    bin.poolfile_id = entry["files id"]

    # Find source id
    bin_sources = get_sources_from_name(entry["source package"], entry["source version"])
    if len(bin_sources) != 1:
        raise NoSourceFieldError, "Unable to find a unique source id for %s (%s), %s, file %s, type %s, signed by %s" % \
                                  (bin.package, bin.version, bin.architecture.arch_string,
                                   filename, bin.binarytype, u.pkg.changes["fingerprint"])

    bin.source_id = bin_sources[0].source_id

    # Add and flush object so it has an ID
    session.add(bin)
    session.flush()

    # Add BinAssociations
    for suite_name in u.pkg.changes["distribution"].keys():
        ba = BinAssociation()
        ba.binary_id = bin.binary_id
        ba.suite_id = get_suite(suite_name).suite_id
        session.add(sa)

    session.flush()

    # Deal with contents
    contents = copy_temporary_contents(bin.package, bin.version, bin.architecture.arch_string, filename, reject=None)
    if not contents:
        print "REJECT\n" + "\n".join(contents.rejects)
        session.rollback()
        raise MissingContents, "No contents stored for package %s, and couldn't determine contents of %s" % (bin.package, filename)


def install(u, log_urgency=True):
    cnf = Config()
    summarystats = SummaryStats()

    print "Installing."

    Logger.log(["installing changes",pkg.changes_file])

    # Begin a transaction; if we bomb out anywhere between here and the COMMIT WORK below, the DB will not be changed.
    session = DBConn().session()

    # Ensure that we have all the hashes we need below.
    u.ensure_hashes()
    if len(u.rejects) > 0:
        # There were errors.  Print them and SKIP the changes.
        for msg in u.rejects:
            utils.warn(msg)
        return

    # Add the .dsc file to the DB first
    for newfile in u.pkg.files.keys():
        if entry["type"] == "dsc":
            dsc_component, dsc_location_id = add_dsc_to_db(u, newfile, session)

    # Add .deb / .udeb files to the DB (type is always deb, dbtype is udeb/deb)
    for newfile in u.pkg.files.keys():
        if entry["type"] == "deb":
            add_deb_to_db(u, newfile, session)

    # If this is a sourceful diff only upload that is moving
    # cross-component we need to copy the .orig.tar.gz into the new
    # component too for the same reasons as above.
    #
    if u.pkg.changes["architecture"].has_key("source") and u.pkg.orig_tar_id and \
       u.pkg.orig_tar_location != dsc_location_id:

        oldf = get_poolfile_by_id(u.pkg.orig_tar_id, session)
        old_filename = os.path.join(oldf.location.path, oldf.filename)
        old_dat = {'size': oldf.filesize,   'md5sum': oldf.md5sum,
                   'sha1sum': oldf.sha1sum, 'sha256sum': oldf.sha256sum}

        new_filename = os.path.join(utils.poolify(u.pkg.changes["source"], dsc_component), os.path.basename(old_filename))

        # TODO: Care about size/md5sum collisions etc
        (found, newf) = check_poolfile(new_filename, file_size, file_md5sum, dsc_location_id, session)

        if newf is None:
            utils.copy(old_filename, os.path.join(cnf["Dir::Pool"], new_filename))
            newf = add_poolfile(new_filename, old_dat, dsc_location_id, session)

            # TODO: Check that there's only 1 here
            source = get_sources_from_name(u.pkg.changes["source"], u.pkg.changes["version"])[0]
            dscf = get_dscfiles(source_id = source.source_id, poolfile_id=u.pkg.orig_tar_id, session=session)[0]
            dscf.poolfile_id = newf.file_id
            session.add(dscf)
            session.flush()

    # Install the files into the pool
    for newfile, entry in u.pkg.files.items():
        destination = os.path.join(cnf["Dir::Pool"], entry["pool name"], newfile)
        utils.move(newfile, destination)
        Logger.log(["installed", newfile, entry["type"], entry["size"], entry["architecture"]])
        summarystats.accept_bytes += float(entry["size"])

    # Copy the .changes file across for suite which need it.
    copy_changes = {}
    copy_dot_dak = {}
    for suite_name in changes["distribution"].keys():
        if cnf.has_key("Suite::%s::CopyChanges" % (suite_name)):
            copy_changes[cnf["Suite::%s::CopyChanges" % (suite_name)]] = ""
        # and the .dak file...
        if cnf.has_key("Suite::%s::CopyDotDak" % (suite_name)):
            copy_dot_dak[cnf["Suite::%s::CopyDotDak" % (suite_name)]] = ""

    for dest in copy_changes.keys():
        utils.copy(u.pkg.changes_file, os.path.join(cnf["Dir::Root"], dest))

    for dest in copy_dot_dak.keys():
        utils.copy(u.pkg.changes_file[:-8]+".dak", dest)

    # We're done - commit the database changes
    session.commit()

    # Move the .changes into the 'done' directory
    utils.move(u.pkg.changes_file,
               os.path.join(cnf["Dir::Queue::Done"], os.path.basename(u.pkg.changes_file)))

    # Remove the .dak file
    os.unlink(u.pkg.changes_file[:-8] + ".dak")

    if u.pkg.changes["architecture"].has_key("source") and log_urgency:
        UrgencyLog().log(u.pkg.dsc["source"], u.pkg.dsc["version"], u.pkg.changes["urgency"])

    # Our SQL session will automatically start a new transaction after
    # the last commit

    # Undo the work done in queue.py(accept) to help auto-building
    # from accepted.
    now_date = datetime.now()

    for suite_name in u.pkg.changes["distribution"].keys():
        if suite_name not in cnf.ValueList("Dinstall::QueueBuildSuites"):
            continue

        suite = get_suite(suite_name, session)
        dest_dir = cnf["Dir::QueueBuild"]

        if cnf.FindB("Dinstall::SecurityQueueBuild"):
            dest_dir = os.path.join(dest_dir, suite_name)

        for newfile, entry in u.pkg.files.items():
            dest = os.path.join(dest_dir, newfile)

            qb = get_queue_build(dest, suite.suite_id, session)

            # Remove it from the list of packages for later processing by apt-ftparchive
            if qb:
                qb.last_used = now_date
                qb.in_queue = False
                session.add(qb)

            if not cnf.FindB("Dinstall::SecurityQueueBuild"):
                # Update the symlink to point to the new location in the pool
                pool_location = utils.poolify(u.pkg.changes["source"], entry["component"])
                src = os.path.join(cnf["Dir::Pool"], pool_location, os.path.basename(newfile))
                if os.path.islink(dest):
                    os.unlink(dest)
                os.symlink(src, dest)

        # Update last_used on any non-upload .orig.tar.gz symlink
        if u.pkg.orig_tar_id:
            # Determine the .orig.tar.gz file name
            for dsc_file in u.pkg.dsc_files.keys():
                if dsc_file.endswith(".orig.tar.gz"):
                    u.pkg.orig_tar_gz = os.path.join(dest_dir, dsc_file)

            # Remove it from the list of packages for later processing by apt-ftparchive
            qb = get_queue_build(u.pkg.orig_tar_gz, suite.suite_id, session)
            if qb:
                qb.in_queue = False
                qb.last_used = now_date
                session.add(qb)

    session.commit()

    # Finally...
    summarystats.accept_count += 1

################################################################################
### XXX: UP TO HERE

def stable_install(u, summary, short_summary, fromsuite_name="proposed-updates"):
    summarystats = SummaryStats()

    fromsuite_name = fromsuite_name.lower()
    tosuite_name = "Stable"
    if fromsuite_name == "oldstable-proposed-updates":
        tosuite_name = "OldStable"

    print "Installing from %s to %s." % (fromsuite_name, tosuite_name)

    fromsuite = get_suite(fromsuite_name)
    tosuite = get_suite(tosuite_name)

    # Begin a transaction; if we bomb out anywhere between here and
    # the COMMIT WORK below, the DB won't be changed.
    session = DBConn().session()

    # Add the source to stable (and remove it from proposed-updates)
    for newfile, entry in u.pkg.files.items():
        if entry["type"] == "dsc":
            package = u.pkg.dsc["source"]
            # NB: not files[file]["version"], that has no epoch
            version = u.pkg.dsc["version"]

            source = get_sources_from_name(package, version, session)
            if len(source) < 1:
                utils.fubar("[INTERNAL ERROR] couldn't find '%s' (%s) in source table." % (package, version))
            source = source[0]

            # Remove from old suite
            old = session.query(SrcAssociation).filter_by(source_id = source.source_id)
            old = old.filter_by(suite_id = fromsuite.suite_id)
            old.delete()

            # Add to new suite
            new = SrcAssociation()
            new.source_id = source.source_id
            new.suite_id = tosuite.suite_id
            session.add(new)

    # Add the binaries to stable (and remove it/them from proposed-updates)
    for newfile, entry in u.pkg.files.items():
        if entry["type"] == "deb":
            package = entry["package"]
            version = entry["version"]
            architecture = entry["architecture"]

            binary = get_binaries_from_name(package, version, [architecture, 'all'])

            if len(binary) < 1:
                utils.fubar("[INTERNAL ERROR] couldn't find '%s' (%s for %s architecture) in binaries table." % (package, version, architecture))
            binary = binary[0]

            # Remove from old suite
            old = session.query(BinAssociation).filter_by(binary_id = binary.binary_id)
            old = old.filter_by(suite_id = fromsuite.suite_id)
            old.delete()

            # Add to new suite
            new = BinAssociation()
            new.binary_id = binary.binary_id
            new.suite_id = tosuite.suite_id
            session.add(new)

    session.commit()

    utils.move(u.pkg.changes_file,
               os.path.join(cnf["Dir::Morgue"], 'process-accepted', os.path.basename(u.pkg.changes_file)))

    ## Update the Stable ChangeLog file
    # TODO: URGH - Use a proper tmp file
    new_changelog_filename = cnf["Dir::Root"] + cnf["Suite::%s::ChangeLogBase" % (tosuite.suite_name)] + ".ChangeLog"
    changelog_filename = cnf["Dir::Root"] + cnf["Suite::%s::ChangeLogBase" % (tosuite.suite_name)] + "ChangeLog"
    if os.path.exists(new_changelog_filename):
        os.unlink(new_changelog_filename)

    new_changelog = utils.open_file(new_changelog_filename, 'w')
    for newfile, entry in u.pkg.files.items():
        if entry["type"] == "deb":
            new_changelog.write("%s/%s/binary-%s/%s\n" % (tosuite.suite_name,
                                                          entry["component"],
                                                          entry["architecture"],
                                                          newfile))
        elif re_issource.match(newfile):
            new_changelog.write("%s/%s/source/%s\n" % (tosuite.suite_name,
                                                       entry["component"],
                                                       newfile))
        else:
            new_changelog.write("%s\n" % (newfile))

    chop_changes = re_fdnic.sub("\n", u.pkg.changes["changes"])
    new_changelog.write(chop_changes + '\n\n')

    if os.access(changelog_filename, os.R_OK) != 0:
        changelog = utils.open_file(changelog_filename)
        new_changelog.write(changelog.read())

    new_changelog.close()

    if os.access(changelog_filename, os.R_OK) != 0:
        os.unlink(changelog_filename)
    utils.move(new_changelog_filename, changelog_filename)

    summarystats.accept_count += 1

    if not Options["No-Mail"] and u.pkg.changes["architecture"].has_key("source"):
        u.Subst["__SUITE__"] = " into %s" % (tosuite)
        u.Subst["__SUMMARY__"] = summary
        u.Subst["__BCC__"] = "X-DAK: dak process-accepted\nX-Katie: $Revision: 1.18 $"

        if cnf.has_key("Dinstall::Bcc"):
            u.Subst["__BCC__"] += "\nBcc: %s" % (cnf["Dinstall::Bcc"])

        template = os.path.join(cnf["Dir::Templates"], 'process-accepted.install')

        mail_message = utils.TemplateSubst(u.Subst, template)
        utils.send_mail(mail_message)
        u.announce(short_summary, True)

    # Finally remove the .dak file
    dot_dak_file = os.path.join(cnf["Suite::%s::CopyDotDak" % (fromsuite.suite_name)],
                                os.path.basename(u.pkg.changes_file[:-8]+".dak"))
    os.unlink(dot_dak_file)

################################################################################

def process_it(changes_file, stable_queue=None, log_urgency=True):
    cnf = Config()
    u = Upload()

    overwrite_checks = True

    # Absolutize the filename to avoid the requirement of being in the
    # same directory as the .changes file.
    cfile = os.path.abspath(changes_file)

    # And since handling of installs to stable munges with the CWD
    # save and restore it.
    u.prevdir = os.getcwd()

    if stable_queue:
        old = cfile
        cfile = os.path.basename(old)
        os.chdir(cnf["Suite::%s::CopyDotDak" % (stable_queue)])
        # overwrite_checks should not be performed if installing to stable
        overwrite_checks = False

    u.load_dot_dak(cfile)
    u.update_subst()

    if stable_queue:
        u.pkg.changes_file = old

    u.accepted_checks(overwrite_checks)
    action(u, stable_queue, log_urgency)

    # Restore CWD
    os.chdir(u.prevdir)

###############################################################################

def main():
    global Logger

    cnf = Config()
    summarystats = SummaryStats()
    changes_files = init()
    log_urgency = False
    stable_queue = None

    # -n/--dry-run invalidates some other options which would involve things happening
    if Options["No-Action"]:
        Options["Automatic"] = ""

    # Check that we aren't going to clash with the daily cron job

    if not Options["No-Action"] and os.path.exists("%s/Archive_Maintenance_In_Progress" % (cnf["Dir::Root"])) and not Options["No-Lock"]:
        utils.fubar("Archive maintenance in progress.  Try again later.")

    # If running from within proposed-updates; assume an install to stable
    queue = ""
    if os.getenv('PWD').find('oldstable-proposed-updates') != -1:
        stable_queue = "Oldstable-Proposed-Updates"
    elif os.getenv('PWD').find('proposed-updates') != -1:
        stable_queue = "Proposed-Updates"

    # Obtain lock if not in no-action mode and initialize the log
    if not Options["No-Action"]:
        lock_fd = os.open(cnf["Dinstall::LockFile"], os.O_RDWR | os.O_CREAT)
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError, e:
            if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EAGAIN':
                utils.fubar("Couldn't obtain lock; assuming another 'dak process-accepted' is already running.")
            else:
                raise
        Logger = daklog.Logger(cnf, "process-accepted")
        if not stable_queue and cnf.get("Dir::UrgencyLog"):
            # Initialise UrgencyLog()
            log_urgency = True
            UrgencyLog()

    # Sort the .changes files so that we process sourceful ones first
    changes_files.sort(utils.changes_compare)

    # Process the changes files
    for changes_file in changes_files:
        print "\n" + changes_file
        process_it(changes_file, stable_queue, log_urgency)

    if summarystats.accept_count:
        sets = "set"
        if summarystats.accept_count > 1:
            sets = "sets"
        sys.stderr.write("Installed %d package %s, %s.\n" % (summarystats.accept_count, sets,
                                                             utils.size_type(int(summarystats.accept_bytes))))
        Logger.log(["total", summarystats.accept_count, summarystats.accept_bytes])

    if not Options["No-Action"]:
        Logger.close()
        if log_urg:
            UrgencyLog().close()

###############################################################################

if __name__ == '__main__':
    main()
