#!/usr/bin/env python
# vim:set et sw=4:

"""
Utility functions for process-upload

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
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

import os

from daklib import utils
from daklib.dbconn import *
from daklib.config import Config

###############################################################################

def determine_target(u):
    cnf = Config()
    
    queues = [ "New", "Autobyhand", "Byhand" ]
    if cnf.FindB("Dinstall::SecurityQueueHandling"):
        queues += [ "Unembargo", "Embargo" ]
    else:
        queues += [ "OldStableUpdate", "StableUpdate" ]

    target = None
    for q in queues:
        if QueueInfo[q]["is"](u):
            target = q
            break

    return target

################################################################################

def package_to_suite(u, suite):
    if not u.pkg.changes["distribution"].has_key(suite):
        return False

    ret = True

    if not u.pkg.changes["architecture"].has_key("source"):
        s = DBConn().session()
        q = s.query(SrcAssociation.sa_id)
        q = q.join(Suite).filter_by(suite_name=suite)
        q = q.join(DBSource).filter_by(source=u.pkg.changes['source'])
        q = q.filter_by(version=u.pkg.changes['version']).limit(1)

        # NB: Careful, this logic isn't what you would think it is
        # Source is already in {old-,}proposed-updates so no need to hold
        # Instead, we don't move to the holding area, we just do an ACCEPT
        if q.count() > 0:
            ret = False

        s.close()

    return ret

def package_to_queue(u, summary, short_summary, queue, perms=0660, build=True, announce=None):
    cnf = Config()
    dir = cnf["Dir::Queue::%s" % queue]

    print "Moving to %s holding area" % queue.upper()
    u.logger.log(["Moving to %s" % queue, u.pkg.changes_file])

    u.move_to_dir(dir, perms=perms)
    if build:
        get_or_set_queue(queue.lower()).autobuild_upload(u.pkg, dir)

    # Check for override disparities
    u.check_override()

    # Send accept mail, announce to lists and close bugs
    if announce and not cnf["Dinstall::Options::No-Mail"]:
        template = os.path.join(cnf["Dir::Templates"], announce)
        u.update_subst()
        u.Subst["__SUITE__"] = ""
        mail_message = utils.TemplateSubst(u.Subst, template)
        utils.send_mail(mail_message)
        u.announce(short_summary, True)

################################################################################

def is_unembargo(u):
    session = DBConn().session()
    cnf = Config()

    q = session.execute("SELECT package FROM disembargo WHERE package = :source AND version = :version", u.pkg.changes)
    if q.rowcount > 0:
        session.close()
        return True

    oldcwd = os.getcwd()
    os.chdir(cnf["Dir::Queue::Disembargo"])
    disdir = os.getcwd()
    os.chdir(oldcwd)

    ret = False

    if u.pkg.directory == disdir:
        if u.pkg.changes["architecture"].has_key("source"):
            session.execute("INSERT INTO disembargo (package, version) VALUES (:package, :version)", u.pkg.changes)
            session.commit()

            ret = True

    session.close()

    return ret

def queue_unembargo(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "Unembargoed",
                            perms=0660, build=True, announce='process-unchecked.accepted')

################################################################################

def is_embargo(u):
    # if embargoed queues are enabled always embargo
    return True

def queue_embargo(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "Unembargoed",
                            perms=0660, build=True, announce='process-unchecked.accepted')

################################################################################

def is_stableupdate(u):
    return package_to_suite(u, 'proposed-updates')

def do_stableupdate(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "ProposedUpdates",
                            perms=0664, build=False, announce=None)

################################################################################

def is_oldstableupdate(u):
    return package_to_suite(u, 'oldstable-proposed-updates')

def do_oldstableupdate(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "OldProposedUpdates",
                            perms=0664, build=False, announce=None)

################################################################################

def is_autobyhand(u):
    cnf = Config()

    all_auto = 1
    any_auto = 0
    for f in u.pkg.files.keys():
        if u.pkg.files[f].has_key("byhand"):
            any_auto = 1

            # filename is of form "PKG_VER_ARCH.EXT" where PKG, VER and ARCH
            # don't contain underscores, and ARCH doesn't contain dots.
            # further VER matches the .changes Version:, and ARCH should be in
            # the .changes Architecture: list.
            if f.count("_") < 2:
                all_auto = 0
                continue

            (pckg, ver, archext) = f.split("_", 2)
            if archext.count(".") < 1 or u.pkg.changes["version"] != ver:
                all_auto = 0
                continue

            ABH = cnf.SubTree("AutomaticByHandPackages")
            if not ABH.has_key(pckg) or \
              ABH["%s::Source" % (pckg)] != u.pkg.changes["source"]:
                print "not match %s %s" % (pckg, u.pkg.changes["source"])
                all_auto = 0
                continue

            (arch, ext) = archext.split(".", 1)
            if arch not in u.pkg.changes["architecture"]:
                all_auto = 0
                continue

            u.pkg.files[f]["byhand-arch"] = arch
            u.pkg.files[f]["byhand-script"] = ABH["%s::Script" % (pckg)]

    return any_auto and all_auto

def do_autobyhand(u, summary, short_summary):
    print "Attempting AUTOBYHAND."
    byhandleft = True
    for f, entry in u.pkg.files.items():
        byhandfile = f

        if not entry.has_key("byhand"):
            continue

        if not entry.has_key("byhand-script"):
            byhandleft = True
            continue

        os.system("ls -l %s" % byhandfile)

        result = os.system("%s %s %s %s %s" % (
                entry["byhand-script"],
                byhandfile,
                u.pkg.changes["version"],
                entry["byhand-arch"],
                os.path.abspath(u.pkg.changes_file)))

        if result == 0:
            os.unlink(byhandfile)
            del entry
        else:
            print "Error processing %s, left as byhand." % (f)
            byhandleft = True

    if byhandleft:
        do_byhand(u, summary, short_summary)
    else:
        u.accept(summary, short_summary)
        u.check_override()
        # XXX: We seem to be missing a u.remove() here
        #      This might explain why we get byhand leftovers in unchecked - mhy

################################################################################

def is_byhand(u):
    for f in u.pkg.files.keys():
        if u.pkg.files[f].has_key("byhand"):
            return True
    return False

def do_byhand(u, summary, short_summary):
    return package_to_queue(u, summary, short_summary, "Byhand",
                            perms=0660, build=False, announce=None)

################################################################################

def is_new(u):
    for f in u.pkg.files.keys():
        if u.pkg.files[f].has_key("new"):
            return True
    return False

def acknowledge_new(u, summary, short_summary):
    cnf = Config()

    print "Moving to NEW holding area."
    u.logger.log(["Moving to new", u.pkg.changes_file])

    u.move_to_dir(cnf["Dir::Queue::New"], perms=0640, changesperms=0644)

    if not Options["No-Mail"]:
        print "Sending new ack."
        template = os.path.join(cnf["Dir::Templates"], 'process-unchecked.new')
        u.update_subst()
        u.Subst["__SUMMARY__"] = summary
        new_ack_message = utils.TemplateSubst(u.Subst, template)
        utils.send_mail(new_ack_message)

################################################################################

# q-unapproved hax0ring
QueueInfo = {
    "New": { "is": is_new, "process": acknowledge_new },
    "Autobyhand" : { "is" : is_autobyhand, "process": do_autobyhand },
    "Byhand" : { "is": is_byhand, "process": do_byhand },
    "OldStableUpdate" : { "is": is_oldstableupdate,
                          "process": do_oldstableupdate },
    "StableUpdate" : { "is": is_stableupdate, "process": do_stableupdate },
    "Unembargo" : { "is": is_unembargo, "process": queue_unembargo },
    "Embargo" : { "is": is_embargo, "process": queue_embargo },
}
