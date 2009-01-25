#!/usr/bin/env python

""" Manually reject packages for proprosed-updates """
# Copyright (C) 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>

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

import os, pg, sys
import apt_pkg
from daklib import database
from daklib import logging
from daklib import queue
from daklib import utils
from daklib.regexes import re_default_answer

################################################################################

# Globals
Cnf = None
Options = None
projectB = None
Upload = None
Logger = None

################################################################################

def usage(exit_code=0):
    print """Usage: dak reject-proposed-updates .CHANGES[...]
Manually reject the .CHANGES file(s).

  -h, --help                show this help and exit.
  -m, --message=MSG         use this message for the rejection.
  -s, --no-mail             don't send any mail."""
    sys.exit(exit_code)

################################################################################

def main():
    global Cnf, Logger, Options, projectB, Upload

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Reject-Proposed-Updates::Options::Help"),
                 ('m',"manual-reject","Reject-Proposed-Updates::Options::Manual-Reject", "HasArg"),
                 ('s',"no-mail", "Reject-Proposed-Updates::Options::No-Mail")]
    for i in [ "help", "manual-reject", "no-mail" ]:
        if not Cnf.has_key("Reject-Proposed-Updates::Options::%s" % (i)):
            Cnf["Reject-Proposed-Updates::Options::%s" % (i)] = ""

    arguments = apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Reject-Proposed-Updates::Options")
    if Options["Help"]:
        usage()
    if not arguments:
        utils.fubar("need at least one .changes filename as an argument.")

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    Upload = queue.Upload(Cnf)
    Logger = Upload.Logger = logging.Logger(Cnf, "reject-proposed-updates")

    bcc = "X-DAK: dak rejected-proposed-updates\nX-Katie: lauren $Revision: 1.4 $"
    if Cnf.has_key("Dinstall::Bcc"):
        Upload.Subst["__BCC__"] = bcc + "\nBcc: %s" % (Cnf["Dinstall::Bcc"])
    else:
        Upload.Subst["__BCC__"] = bcc

    for arg in arguments:
        arg = utils.validate_changes_file_arg(arg)
        Upload.pkg.changes_file = arg
        Upload.init_vars()
        cwd = os.getcwd()
        os.chdir(Cnf["Suite::Proposed-Updates::CopyDotDak"])
        Upload.update_vars()
        os.chdir(cwd)
        Upload.update_subst()

        print arg
        done = 0
        prompt = "Manual reject, [S]kip, Quit ?"
        while not done:
            answer = "XXX"

            while prompt.find(answer) == -1:
                answer = utils.our_raw_input(prompt)
                m = re_default_answer.search(prompt)
                if answer == "":
                    answer = m.group(1)
                answer = answer[:1].upper()

            if answer == 'M':
                aborted = reject(Options["Manual-Reject"])
                if not aborted:
                    done = 1
            elif answer == 'S':
                done = 1
            elif answer == 'Q':
                sys.exit(0)

    Logger.close()

################################################################################

def reject (reject_message = ""):
    files = Upload.pkg.files
    dsc = Upload.pkg.dsc
    changes_file = Upload.pkg.changes_file

    # If we weren't given a manual rejection message, spawn an editor
    # so the user can add one in...
    if not reject_message:
        (fd, temp_filename) = utils.temp_filename()
        editor = os.environ.get("EDITOR","vi")
        answer = 'E'
        while answer == 'E':
            os.system("%s %s" % (editor, temp_filename))
            f = os.fdopen(fd)
            reject_message = "".join(f.readlines())
            f.close()
            print "Reject message:"
            print utils.prefix_multi_line_string(reject_message,"  ", include_blank_lines=1)
            prompt = "[R]eject, Edit, Abandon, Quit ?"
            answer = "XXX"
            while prompt.find(answer) == -1:
                answer = utils.our_raw_input(prompt)
                m = re_default_answer.search(prompt)
                if answer == "":
                    answer = m.group(1)
                answer = answer[:1].upper()
        os.unlink(temp_filename)
        if answer == 'A':
            return 1
        elif answer == 'Q':
            sys.exit(0)

    print "Rejecting.\n"

    # Reject the .changes file
    Upload.force_reject([changes_file])

    # Setup the .reason file
    reason_filename = changes_file[:-8] + ".reason"
    reject_filename = Cnf["Dir::Queue::Reject"] + '/' + reason_filename

    # If we fail here someone is probably trying to exploit the race
    # so let's just raise an exception ...
    if os.path.exists(reject_filename):
        os.unlink(reject_filename)
    reject_fd = os.open(reject_filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0644)

    # Build up the rejection email
    user_email_address = utils.whoami() + " <%s>" % (Cnf["Dinstall::MyAdminAddress"])

    Upload.Subst["__REJECTOR_ADDRESS__"] = user_email_address
    Upload.Subst["__MANUAL_REJECT_MESSAGE__"] = reject_message
    Upload.Subst["__STABLE_REJECTOR__"] = Cnf["Reject-Proposed-Updates::StableRejector"]
    Upload.Subst["__STABLE_MAIL__"] = Cnf["Reject-Proposed-Updates::StableMail"]
    Upload.Subst["__MORE_INFO_URL__"] = Cnf["Reject-Proposed-Updates::MoreInfoURL"]
    Upload.Subst["__CC__"] = "Cc: " + Cnf["Dinstall::MyEmailAddress"]
    reject_mail_message = utils.TemplateSubst(Upload.Subst,Cnf["Dir::Templates"]+"/reject-proposed-updates.rejected")

    # Write the rejection email out as the <foo>.reason file
    os.write(reject_fd, reject_mail_message)
    os.close(reject_fd)

    # Remove the packages from proposed-updates
    suite_id = database.get_suite_id('proposed-updates')

    projectB.query("BEGIN WORK")
    # Remove files from proposed-updates suite
    for f in files.keys():
        if files[f]["type"] == "dsc":
            package = dsc["source"]
            version = dsc["version"];  # NB: not files[f]["version"], that has no epoch
            q = projectB.query("SELECT id FROM source WHERE source = '%s' AND version = '%s'" % (package, version))
            ql = q.getresult()
            if not ql:
                utils.fubar("reject: Couldn't find %s_%s in source table." % (package, version))
            source_id = ql[0][0]
            projectB.query("DELETE FROM src_associations WHERE suite = '%s' AND source = '%s'" % (suite_id, source_id))
        elif files[f]["type"] == "deb":
            package = files[f]["package"]
            version = files[f]["version"]
            architecture = files[f]["architecture"]
            q = projectB.query("SELECT b.id FROM binaries b, architecture a WHERE b.package = '%s' AND b.version = '%s' AND (a.arch_string = '%s' OR a.arch_string = 'all') AND b.architecture = a.id" % (package, version, architecture))
            ql = q.getresult()

            # Horrible hack to work around partial replacement of
            # packages with newer versions (from different source
            # packages).  This, obviously, should instead check for a
            # newer version of the package and only do the
            # warn&continue thing if it finds one.
            if not ql:
                utils.warn("reject: Couldn't find %s_%s_%s in binaries table." % (package, version, architecture))
            else:
                binary_id = ql[0][0]
                projectB.query("DELETE FROM bin_associations WHERE suite = '%s' AND bin = '%s'" % (suite_id, binary_id))
    projectB.query("COMMIT WORK")

    # Send the rejection mail if appropriate
    if not Options["No-Mail"]:
        utils.send_mail(reject_mail_message)

    # Finally remove the .dak file
    dot_dak_file = os.path.join(Cnf["Suite::Proposed-Updates::CopyDotDak"], os.path.basename(changes_file[:-8]+".dak"))
    os.unlink(dot_dak_file)

    Logger.log(["rejected", changes_file])
    return 0

################################################################################

if __name__ == '__main__':
    main()
