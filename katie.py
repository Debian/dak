#!/usr/bin/env python

# Utility functions for katie
# Copyright (C) 2001, 2002, 2003  James Troup <james@nocrew.org>
# $Id: katie.py,v 1.41 2003-10-14 21:52:46 troup Exp $

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

import cPickle, errno, os, pg, re, stat, string, sys, tempfile, time;
import utils, db_access;
import apt_inst, apt_pkg;

from types import *;

###############################################################################

re_isanum = re.compile (r"^\d+$");
re_default_answer = re.compile(r"\[(.*)\]");
re_fdnic = re.compile("\n\n");
re_bin_only_nmu_of_mu = re.compile("\.\d+\.\d+$");
re_bin_only_nmu_of_nmu = re.compile("\.\d+$");

###############################################################################

# Convenience wrapper to carry around all the package information in

class Pkg:
    def __init__(self, **kwds):
        self.__dict__.update(kwds);

    def update(self, **kwds):
        self.__dict__.update(kwds);

###############################################################################

class nmu_p:
    # Read in the group maintainer override file
    def __init__ (self, Cnf):
        self.group_maint = {};
        self.Cnf = Cnf;
        if Cnf.get("Dinstall::GroupOverrideFilename"):
            filename = Cnf["Dir::Override"] + Cnf["Dinstall::GroupOverrideFilename"];
            file = utils.open_file(filename);
            for line in file.readlines():
                line = utils.re_comments.sub('', line).lower().strip();
                if line != "":
                    self.group_maint[line] = 1;
            file.close();

    def is_an_nmu (self, pkg):
        Cnf = self.Cnf;
        changes = pkg.changes;
        dsc = pkg.dsc;

        (dsc_rfc822, dsc_name, dsc_email) = utils.fix_maintainer (dsc.get("maintainer",Cnf["Dinstall::MyEmailAddress"]).lower());
        # changes["changedbyname"] == dsc_name is probably never true, but better safe than sorry
        if dsc_name == changes["maintainername"].lower() and \
           (changes["changedby822"] == "" or changes["changedbyname"].lower() == dsc_name):
            return 0;

        if dsc.has_key("uploaders"):
            uploaders = dsc["uploaders"].lower().split(",");
            uploadernames = {};
            for i in uploaders:
                (rfc822, name, email) = utils.fix_maintainer (i.strip());
                uploadernames[name] = "";
            if uploadernames.has_key(changes["changedbyname"].lower()):
                return 0;

        # Some group maintained packages (e.g. Debian QA) are never NMU's
        if self.group_maint.has_key(changes["maintaineremail"].lower()):
            return 0;

        return 1;

###############################################################################

class Katie:

    def __init__(self, Cnf):
        self.Cnf = Cnf;
        self.values = {};
        # Read in the group-maint override file
        self.nmu = nmu_p(Cnf);
        self.accept_count = 0;
        self.accept_bytes = 0L;
        self.pkg = Pkg(changes = {}, dsc = {}, dsc_files = {}, files = {},
                       legacy_source_untouchable = {});

        # Initialize the substitution template mapping global
        Subst = self.Subst = {};
        Subst["__ADMIN_ADDRESS__"] = Cnf["Dinstall::MyAdminAddress"];
        Subst["__BUG_SERVER__"] = Cnf["Dinstall::BugServer"];
        Subst["__DISTRO__"] = Cnf["Dinstall::MyDistribution"];
        Subst["__KATIE_ADDRESS__"] = Cnf["Dinstall::MyEmailAddress"];

        self.projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]));
        db_access.init(Cnf, self.projectB);

    ###########################################################################

    def init_vars (self):
        for i in [ "changes", "dsc", "files", "dsc_files", "legacy_source_untouchable" ]:
            exec "self.pkg.%s.clear();" % (i);
        self.pkg.orig_tar_id = None;
        self.pkg.orig_tar_location = "";

    ###########################################################################

    def update_vars (self):
        dump_filename = self.pkg.changes_file[:-8]+".katie";
        dump_file = utils.open_file(dump_filename);
        p = cPickle.Unpickler(dump_file);
        for i in [ "changes", "dsc", "files", "dsc_files", "legacy_source_untouchable" ]:
            exec "self.pkg.%s.update(p.load());" % (i);
        for i in [ "orig_tar_id", "orig_tar_location" ]:
            exec "self.pkg.%s = p.load();" % (i);
        dump_file.close();

    ###########################################################################

    # This could just dump the dictionaries as is, but I'd like to avoid
    # this so there's some idea of what katie & lisa use from jennifer

    def dump_vars(self, dest_dir):
        for i in [ "changes", "dsc", "files", "dsc_files",
                   "legacy_source_untouchable", "orig_tar_id", "orig_tar_location" ]:
            exec "%s = self.pkg.%s;" % (i,i);
        dump_filename = os.path.join(dest_dir,self.pkg.changes_file[:-8] + ".katie");
        dump_file = utils.open_file(dump_filename, 'w');
        try:
            os.chmod(dump_filename, 0660);
        except OSError, e:
            if errno.errorcode[e.errno] == 'EPERM':
                perms = stat.S_IMODE(os.stat(dump_filename)[stat.ST_MODE]);
                if perms & stat.S_IROTH:
                    utils.fubar("%s is world readable and chmod failed." % (dump_filename));
            else:
                raise;

        p = cPickle.Pickler(dump_file, 1);
        for i in [ "d_changes", "d_dsc", "d_files", "d_dsc_files" ]:
            exec "%s = {}" % i;
        ## files
        for file in files.keys():
            d_files[file] = {};
            for i in [ "package", "version", "architecture", "type", "size",
                       "md5sum", "component", "location id", "source package",
                       "source version", "maintainer", "dbtype", "files id",
                       "new", "section", "priority", "othercomponents",
                       "pool name", "original component" ]:
                if files[file].has_key(i):
                    d_files[file][i] = files[file][i];
        ## changes
        # Mandatory changes fields
        for i in [ "distribution", "source", "architecture", "version", "maintainer",
                   "urgency", "fingerprint", "changedby822", "changedbyname",
                   "maintainername", "maintaineremail", "closes" ]:
            d_changes[i] = changes[i];
        # Optional changes fields
        # FIXME: changes should be mandatory
        for i in [ "changed-by", "maintainer822", "filecontents", "format",
                   "changes", "lisa note" ]:
            if changes.has_key(i):
                d_changes[i] = changes[i];
        ## dsc
        for i in [ "source", "version", "maintainer", "fingerprint", "uploaders" ]:
            if dsc.has_key(i):
                d_dsc[i] = dsc[i];
        ## dsc_files
        for file in dsc_files.keys():
            d_dsc_files[file] = {};
            # Mandatory dsc_files fields
            for i in [ "size", "md5sum" ]:
                d_dsc_files[file][i] = dsc_files[file][i];
            # Optional dsc_files fields
            for i in [ "files id" ]:
                if dsc_files[file].has_key(i):
                    d_dsc_files[file][i] = dsc_files[file][i];

        for i in [ d_changes, d_dsc, d_files, d_dsc_files,
                   legacy_source_untouchable, orig_tar_id, orig_tar_location ]:
            p.dump(i);
        dump_file.close();

    ###########################################################################

    # Set up the per-package template substitution mappings

    def update_subst (self, reject_message = ""):
        Subst = self.Subst;
        changes = self.pkg.changes;
        # If jennifer crashed out in the right place, architecture may still be a string.
        if not changes.has_key("architecture") or not isinstance(changes["architecture"], DictType):
            changes["architecture"] = { "Unknown" : "" };
        # and maintainer822 may not exist.
        if not changes.has_key("maintainer822"):
            changes["maintainer822"] = self.Cnf["Dinstall::MyEmailAddress"];

        Subst["__ARCHITECTURE__"] = " ".join(changes["architecture"].keys());
        Subst["__CHANGES_FILENAME__"] = os.path.basename(self.pkg.changes_file);
        Subst["__FILE_CONTENTS__"] = changes.get("filecontents", "");

        # For source uploads the Changed-By field wins; otherwise Maintainer wins.
        if changes["architecture"].has_key("source") and changes["changedby822"] != "" and (changes["changedby822"] != changes["maintainer822"]):
            Subst["__MAINTAINER_FROM__"] = changes["changedby822"];
            Subst["__MAINTAINER_TO__"] = changes["changedby822"] + ", " + changes["maintainer822"];
            Subst["__MAINTAINER__"] = changes.get("changed-by", "Unknown");
        else:
            Subst["__MAINTAINER_FROM__"] = changes["maintainer822"];
            Subst["__MAINTAINER_TO__"] = changes["maintainer822"];
            Subst["__MAINTAINER__"] = changes.get("maintainer", "Unknown");
        if self.Cnf.has_key("Dinstall::TrackingServer") and changes.has_key("source"):
            Subst["__MAINTAINER_TO__"] += "\nBcc: %s@%s" % (changes["source"], self.Cnf["Dinstall::TrackingServer"])

        # Apply any global override of the Maintainer field
        if self.Cnf.get("Dinstall::OverrideMaintainer"):
            Subst["__MAINTAINER_TO__"] = self.Cnf["Dinstall::OverrideMaintainer"];
            Subst["__MAINTAINER_FROM__"] = self.Cnf["Dinstall::OverrideMaintainer"];

        Subst["__REJECT_MESSAGE__"] = reject_message;
        Subst["__SOURCE__"] = changes.get("source", "Unknown");
        Subst["__VERSION__"] = changes.get("version", "Unknown");

    ###########################################################################

    def build_summaries(self):
        changes = self.pkg.changes;
        files = self.pkg.files;

        byhand = summary = new = "";

        # changes["distribution"] may not exist in corner cases
        # (e.g. unreadable changes files)
        if not changes.has_key("distribution") or not isinstance(changes["distribution"], DictType):
            changes["distribution"] = {};

        file_keys = files.keys();
        file_keys.sort();
        for file in file_keys:
            if files[file].has_key("byhand"):
                byhand = 1
                summary += file + " byhand\n"
            elif files[file].has_key("new"):
                new = 1
                summary += "(new) %s %s %s\n" % (file, files[file]["priority"], files[file]["section"])
                if files[file].has_key("othercomponents"):
                    summary += "WARNING: Already present in %s distribution.\n" % (files[file]["othercomponents"])
                if files[file]["type"] == "deb":
                    summary += apt_pkg.ParseSection(apt_inst.debExtractControl(utils.open_file(file)))["Description"] + '\n';
            else:
                files[file]["pool name"] = utils.poolify (changes["source"], files[file]["component"])
                destination = self.Cnf["Dir::PoolRoot"] + files[file]["pool name"] + file
                summary += file + "\n  to " + destination + "\n"

        short_summary = summary;

        # This is for direport's benefit...
        f = re_fdnic.sub("\n .\n", changes.get("changes",""));

        if byhand or new:
            summary += "Changes: " + f;

        summary += self.announce(short_summary, 0)

        return (summary, short_summary);

    ###########################################################################

    def close_bugs (self, summary, action):
        changes = self.pkg.changes;
        Subst = self.Subst;
        Cnf = self.Cnf;

        bugs = changes["closes"].keys();

        if not bugs:
            return summary;

        bugs.sort();
        if not self.nmu.is_an_nmu(self.pkg):
            if changes["distribution"].has_key("experimental"):
		# tag bugs as fixed-in-experimental for uploads to experimental
		summary += "Setting bugs to severity fixed: ";
		control_message = "";
		for bug in bugs:
		    summary += "%s " % (bug);
		    control_message += "tag %s + fixed-in-experimental\n" % (bug);
		if action and control_message != "":
		    Subst["__CONTROL_MESSAGE__"] = control_message;
		    mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/jennifer.bug-experimental-fixed");
		    utils.send_mail (mail_message);
		if action:
		    self.Logger.log(["setting bugs to fixed"]+bugs);


	    else:
		summary += "Closing bugs: ";
		for bug in bugs:
		    summary += "%s " % (bug);
		    if action:
			Subst["__BUG_NUMBER__"] = bug;
			if changes["distribution"].has_key("stable"):
			    Subst["__STABLE_WARNING__"] = """
Note that this package is not part of the released stable Debian
distribution.  It may have dependencies on other unreleased software,
or other instabilities.  Please take care if you wish to install it.
The update will eventually make its way into the next released Debian
distribution.""";
		        else:
			    Subst["__STABLE_WARNING__"] = "";
			    mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/jennifer.bug-close");
			    utils.send_mail (mail_message);
                if action:
                    self.Logger.log(["closing bugs"]+bugs);

	else:                     # NMU
            summary += "Setting bugs to severity fixed: ";
            control_message = "";
            for bug in bugs:
                summary += "%s " % (bug);
                control_message += "tag %s + fixed\n" % (bug);
            if action and control_message != "":
                Subst["__CONTROL_MESSAGE__"] = control_message;
                mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/jennifer.bug-nmu-fixed");
                utils.send_mail (mail_message);
            if action:
                self.Logger.log(["setting bugs to fixed"]+bugs);
        summary += "\n";
        return summary;

    ###########################################################################

    def announce (self, short_summary, action):
        Subst = self.Subst;
        Cnf = self.Cnf;
        changes = self.pkg.changes;

        # Only do announcements for source uploads with a recent dpkg-dev installed
        if float(changes.get("format", 0)) < 1.6 or not changes["architecture"].has_key("source"):
            return "";

        lists_done = {};
        summary = "";
        Subst["__SHORT_SUMMARY__"] = short_summary;

        for dist in changes["distribution"].keys():
            list = Cnf.Find("Suite::%s::Announce" % (dist));
            if list == "" or lists_done.has_key(list):
                continue;
            lists_done[list] = 1;
            summary += "Announcing to %s\n" % (list);

            if action:
                Subst["__ANNOUNCE_LIST_ADDRESS__"] = list;
                if Cnf.get("Dinstall::TrackingServer") and changes["architecture"].has_key("source"):
                    Subst["__ANNOUNCE_LIST_ADDRESS__"] = Subst["__ANNOUNCE_LIST_ADDRESS__"] + "\nBcc: %s@%s" % (changes["source"], Cnf["Dinstall::TrackingServer"]);
                mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/jennifer.announce");
                utils.send_mail (mail_message);

        if Cnf.FindB("Dinstall::CloseBugs"):
            summary = self.close_bugs(summary, action);

        return summary;

    ###########################################################################

    def accept (self, summary, short_summary):
        Cnf = self.Cnf;
        Subst = self.Subst;
        files = self.pkg.files;

        print "Accepting."
        self.Logger.log(["Accepting changes",self.pkg.changes_file]);

        self.dump_vars(Cnf["Dir::Queue::Accepted"]);

        # Move all the files into the accepted directory
        utils.move(self.pkg.changes_file, Cnf["Dir::Queue::Accepted"]);
        file_keys = files.keys();
        for file in file_keys:
            utils.move(file, Cnf["Dir::Queue::Accepted"]);
            self.accept_bytes += float(files[file]["size"])
        self.accept_count += 1;

        # Send accept mail, announce to lists, close bugs and check for
        # override disparities
        if not Cnf["Dinstall::Options::No-Mail"]:
            Subst["__SUITE__"] = "";
            Subst["__SUMMARY__"] = summary;
            mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/jennifer.accepted");
            utils.send_mail(mail_message)
            self.announce(short_summary, 1)

        # Special support to enable clean auto-building of accepted packages
        self.projectB.query("BEGIN WORK");
        for suite in self.pkg.changes["distribution"].keys():
            if suite not in Cnf.ValueList("Dinstall::AcceptedAutoBuildSuites"):
                continue;
            suite_id = db_access.get_suite_id(suite);
            dest_dir = Cnf["Dir::AcceptedAutoBuild"];
            if Cnf.FindB("Dinstall::SecurityAcceptedAutoBuild"):
                dest_dir = os.path.join(dest_dir, suite);
            for file in file_keys:
                src = os.path.join(Cnf["Dir::Queue::Accepted"], file);
                dest = os.path.join(dest_dir, file);
                if Cnf.FindB("Dinstall::SecurityAcceptedAutoBuild"):
                    # Copy it since the original won't be readable by www-data
                    utils.copy(src, dest);
                else:
                    # Create a symlink to it
                    os.symlink(src, dest);
                # Add it to the list of packages for later processing by apt-ftparchive
                self.projectB.query("INSERT INTO accepted_autobuild (suite, filename, in_accepted) VALUES (%s, '%s', 't')" % (suite_id, dest));
            # If the .orig.tar.gz is in the pool, create a symlink to
            # it (if one doesn't already exist)
            if self.pkg.orig_tar_id:
                # Determine the .orig.tar.gz file name
                for dsc_file in self.pkg.dsc_files.keys():
                    if dsc_file.endswith(".orig.tar.gz"):
                        filename = dsc_file;
                dest = os.path.join(dest_dir, filename);
                # If it doesn't exist, create a symlink
                if not os.path.exists(dest):
                    # Find the .orig.tar.gz in the pool
                    q = self.projectB.query("SELECT l.path, f.filename from location l, files f WHERE f.id = %s and f.location = l.id" % (self.pkg.orig_tar_id));
                    ql = q.getresult();
                    if not ql:
                        utils.fubar("[INTERNAL ERROR] Couldn't find id %s in files table." % (self.pkg.orig_tar_id));
                    src = os.path.join(ql[0][0], ql[0][1]);
                    os.symlink(src, dest);
                    # Add it to the list of packages for later processing by apt-ftparchive
                    self.projectB.query("INSERT INTO accepted_autobuild (suite, filename, in_accepted) VALUES (%s, '%s', 't')" % (suite_id, dest));
                # if it does, update things to ensure it's not removed prematurely
                else:
                    self.projectB.query("UPDATE accepted_autobuild SET in_accepted = 't', last_used = NULL WHERE filename = '%s' AND suite = %s" % (dest, suite_id));

        self.projectB.query("COMMIT WORK");

    ###########################################################################

    def check_override (self):
        Subst = self.Subst;
        changes = self.pkg.changes;
        files = self.pkg.files;
        Cnf = self.Cnf;

        # Abandon the check if:
        #  a) it's a non-sourceful upload
        #  b) override disparity checks have been disabled
        #  c) we're not sending mail
        if not changes["architecture"].has_key("source") or \
           not Cnf.FindB("Dinstall::OverrideDisparityCheck") or \
           Cnf["Dinstall::Options::No-Mail"]:
            return;

        summary = "";
        for file in files.keys():
            if not files[file].has_key("new") and files[file]["type"] == "deb":
                section = files[file]["section"];
                override_section = files[file]["override section"];
                if section.lower() != override_section.lower() and section != "-":
                    # Ignore this; it's a common mistake and not worth whining about
                    if section.lower() == "non-us/main" and override_section.lower() == "non-us":
                        continue;
                    summary += "%s: package says section is %s, override says %s.\n" % (file, section, override_section);
                priority = files[file]["priority"];
                override_priority = files[file]["override priority"];
                if priority != override_priority and priority != "-":
                    summary += "%s: package says priority is %s, override says %s.\n" % (file, priority, override_priority);

        if summary == "":
            return;

        Subst["__SUMMARY__"] = summary;
        mail_message = utils.TemplateSubst(Subst,self.Cnf["Dir::Templates"]+"/jennifer.override-disparity");
        utils.send_mail(mail_message);

    ###########################################################################

    def force_reject (self, files):
        """Forcefully move files from the current directory to the
           reject directory.  If any file already exists in the reject
           directory it will be moved to the morgue to make way for
           the new file."""

        Cnf = self.Cnf

        for file in files:
            # Skip any files which don't exist or which we don't have permission to copy.
            if os.access(file,os.R_OK) == 0:
                continue;
            dest_file = os.path.join(Cnf["Dir::Queue::Reject"], file);
            try:
                os.open(dest_file, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0644);
            except OSError, e:
                # File exists?  Let's try and move it to the morgue
                if errno.errorcode[e.errno] == 'EEXIST':
                    morgue_file = os.path.join(Cnf["Dir::Morgue"],Cnf["Dir::MorgueReject"],file);
                    try:
                        morgue_file = utils.find_next_free(morgue_file);
                    except utils.tried_too_hard_exc:
                        # Something's either gone badly Pete Tong, or
                        # someone is trying to exploit us.
                        utils.warn("**WARNING** failed to move %s from the reject directory to the morgue." % (file));
                        return;
                    utils.move(dest_file, morgue_file, perms=0660);
                    try:
                        os.open(dest_file, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0644);
                    except OSError, e:
                        # Likewise
                        utils.warn("**WARNING** failed to claim %s in the reject directory." % (file));
                        return;
                else:
                    raise;
            # If we got here, we own the destination file, so we can
            # safely overwrite it.
            utils.move(file, dest_file, 1, perms=0660);

    ###########################################################################

    def do_reject (self, manual = 0, reject_message = ""):
        # If we weren't given a manual rejection message, spawn an
        # editor so the user can add one in...
        if manual and not reject_message:
            temp_filename = tempfile.mktemp();
            fd = os.open(temp_filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0700);
            os.close(fd);
            editor = os.environ.get("EDITOR","vi")
            answer = 'E';
            while answer == 'E':
                os.system("%s %s" % (editor, temp_filename))
                file = utils.open_file(temp_filename);
                reject_message = "".join(file.readlines());
                file.close();
                print "Reject message:";
                print utils.prefix_multi_line_string(reject_message,"  ",include_blank_lines=1);
                prompt = "[R]eject, Edit, Abandon, Quit ?"
                answer = "XXX";
                while prompt.find(answer) == -1:
                    answer = utils.our_raw_input(prompt);
                    m = re_default_answer.search(prompt);
                    if answer == "":
                        answer = m.group(1);
                    answer = answer[:1].upper();
            os.unlink(temp_filename);
            if answer == 'A':
                return 1;
            elif answer == 'Q':
                sys.exit(0);

        print "Rejecting.\n"

        Cnf = self.Cnf;
        Subst = self.Subst;
        pkg = self.pkg;

        reason_filename = pkg.changes_file[:-8] + ".reason";
        reason_filename = Cnf["Dir::Queue::Reject"] + '/' + reason_filename;

        # Move all the files into the reject directory
        reject_files = pkg.files.keys() + [pkg.changes_file];
        self.force_reject(reject_files);

        # If we fail here someone is probably trying to exploit the race
        # so let's just raise an exception ...
        if os.path.exists(reason_filename):
            os.unlink(reason_filename);
        reason_file = os.open(reason_filename, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0644);

        if not manual:
            Subst["__REJECTOR_ADDRESS__"] = Cnf["Dinstall::MyEmailAddress"];
            Subst["__MANUAL_REJECT_MESSAGE__"] = "";
            Subst["__CC__"] = "X-Katie-Rejection: automatic (moo)";
            os.write(reason_file, reject_message);
            reject_mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/katie.rejected");
        else:
            # Build up the rejection email
            user_email_address = utils.whoami() + " <%s>" % (Cnf["Dinstall::MyAdminAddress"]);

            Subst["__REJECTOR_ADDRESS__"] = user_email_address;
            Subst["__MANUAL_REJECT_MESSAGE__"] = reject_message;
            Subst["__CC__"] = "Cc: " + Cnf["Dinstall::MyEmailAddress"];
            reject_mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/katie.rejected");
            # Write the rejection email out as the <foo>.reason file
            os.write(reason_file, reject_mail_message);

        os.close(reason_file);

        # Send the rejection mail if appropriate
        if not Cnf["Dinstall::Options::No-Mail"]:
            utils.send_mail(reject_mail_message);

        self.Logger.log(["rejected", pkg.changes_file]);
        return 0;

    ################################################################################

    # Ensure that source exists somewhere in the archive for the binary
    # upload being processed.
    #
    # (1) exact match                      => 1.0-3
    # (2) Bin-only NMU of an MU            => 1.0-3.0.1
    # (3) Bin-only NMU of a sourceful-NMU  => 1.0-3.1.1

    def source_exists (self, package, source_version, suites = ["any"]):
	okay = 1
	for suite in suites:
	    if suite == "any":
	    	que = "SELECT s.version FROM source s WHERE s.source = '%s'" % \
		    (package)
	    else:
		# source must exist in suite X, or in some other suite that's
		# mapped to X, recursively... silent-maps are counted too,
		# unreleased-maps aren't.
		maps = self.Cnf.ValueList("SuiteMappings")[:]
		maps.reverse()
		maps = [ m.split() for m in maps ]
		maps = [ (x[1], x[2]) for x in maps 
				if x[0] == "map" or x[0] == "silent-map" ]
		s = [suite]
		for x in maps:
			if x[1] in s and x[0] not in s:
				s.append(x[0])
		
		que = "SELECT s.version FROM source s JOIN src_associations sa ON (s.id = sa.source) JOIN suite su ON (sa.suite = su.id) WHERE s.source = '%s' AND (%s)" % (package, string.join(["su.suite_name = '%s'" % a for a in s], " OR "));
            q = self.projectB.query(que)

            # Reduce the query results to a list of version numbers
            ql = map(lambda x: x[0], q.getresult());

            # Try (1)
            if ql.count(source_version):
                continue

            # Try (2)
            orig_source_version = re_bin_only_nmu_of_mu.sub('', source_version)
            if ql.count(orig_source_version):
                continue

            # Try (3)
            orig_source_version = re_bin_only_nmu_of_nmu.sub('', source_version)
            if ql.count(orig_source_version):
                continue

            # No source found...
            okay = 0
	return okay

    ################################################################################

    def in_override_p (self, package, component, suite, binary_type, file):
        files = self.pkg.files;

        if binary_type == "": # must be source
            type = "dsc";
        else:
            type = binary_type;

        # Override suite name; used for example with proposed-updates
        if self.Cnf.Find("Suite::%s::OverrideSuite" % (suite)) != "":
            suite = self.Cnf["Suite::%s::OverrideSuite" % (suite)];

        # Avoid <undef> on unknown distributions
        suite_id = db_access.get_suite_id(suite);
        if suite_id == -1:
            return None;
        component_id = db_access.get_component_id(component);
        type_id = db_access.get_override_type_id(type);

        # FIXME: nasty non-US speficic hack
        if component[:7].lower() == "non-us/":
            component = component[7:];

        q = self.projectB.query("SELECT s.section, p.priority FROM override o, section s, priority p WHERE package = '%s' AND suite = %s AND component = %s AND type = %s AND o.section = s.id AND o.priority = p.id"
                           % (package, suite_id, component_id, type_id));
        result = q.getresult();
        # If checking for a source package fall back on the binary override type
        if type == "dsc" and not result:
            deb_type_id = db_access.get_override_type_id("deb");
            udeb_type_id = db_access.get_override_type_id("udeb");
            q = self.projectB.query("SELECT s.section, p.priority FROM override o, section s, priority p WHERE package = '%s' AND suite = %s AND component = %s AND (type = %s OR type = %s) AND o.section = s.id AND o.priority = p.id"
                               % (package, suite_id, component_id, deb_type_id, udeb_type_id));
            result = q.getresult();

        # Remember the section and priority so we can check them later if appropriate
        if result:
            files[file]["override section"] = result[0][0];
            files[file]["override priority"] = result[0][1];

        return result;

    ################################################################################

    def reject (self, str, prefix="Rejected: "):
        if str:
            # Unlike other rejects we add new lines first to avoid trailing
            # new lines when this message is passed back up to a caller.
            if self.reject_message:
                self.reject_message += "\n";
            self.reject_message += prefix + str;

    ################################################################################

    def cross_suite_version_check(self, query_result, file, new_version):
        """Ensure versions are newer than existing packages in target
        suites and that cross-suite version checking rules as
        set out in the conf file are satisfied."""

        # Check versions for each target suite
        for target_suite in self.pkg.changes["distribution"].keys():
            must_be_newer_than = map(string.lower, self.Cnf.ValueList("Suite::%s::VersionChecks::MustBeNewerThan" % (target_suite)));
            must_be_older_than = map(string.lower, self.Cnf.ValueList("Suite::%s::VersionChecks::MustBeOlderThan" % (target_suite)));
            # Enforce "must be newer than target suite" even if conffile omits it
            if target_suite not in must_be_newer_than:
                must_be_newer_than.append(target_suite);
            for entry in query_result:
                existent_version = entry[0];
                suite = entry[1];
                if suite in must_be_newer_than and \
                   apt_pkg.VersionCompare(new_version, existent_version) != 1:
                    self.reject("%s: old version (%s) in %s >= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite));
                if suite in must_be_older_than and \
                   apt_pkg.VersionCompare(new_version, existent_version) != -1:
                    self.reject("%s: old version (%s) in %s <= new version (%s) targeted at %s." % (file, existent_version, suite, new_version, target_suite));

    ################################################################################

    def check_binary_against_db(self, file):
        self.reject_message = "";
        files = self.pkg.files;

        # Ensure version is sane
        q = self.projectB.query("""
SELECT b.version, su.suite_name FROM binaries b, bin_associations ba, suite su,
                                     architecture a
 WHERE b.package = '%s' AND (a.arch_string = '%s' OR a.arch_string = 'all')
   AND ba.bin = b.id AND ba.suite = su.id AND b.architecture = a.id"""
                                % (files[file]["package"],
                                   files[file]["architecture"]));
        self.cross_suite_version_check(q.getresult(), file, files[file]["version"]);

        # Check for any existing copies of the file
        q = self.projectB.query("""
SELECT b.id FROM binaries b, architecture a
 WHERE b.package = '%s' AND b.version = '%s' AND a.arch_string = '%s'
   AND a.id = b.architecture"""
                                % (files[file]["package"],
                                   files[file]["version"],
                                   files[file]["architecture"]))
        if q.getresult():
            self.reject("%s: can not overwrite existing copy already in the archive." % (file));

        return self.reject_message;

    ################################################################################

    def check_source_against_db(self, file):
        self.reject_message = "";
        dsc = self.pkg.dsc;

        # Ensure version is sane
        q = self.projectB.query("""
SELECT s.version, su.suite_name FROM source s, src_associations sa, suite su
 WHERE s.source = '%s' AND sa.source = s.id AND sa.suite = su.id""" % (dsc.get("source")));
        self.cross_suite_version_check(q.getresult(), file, dsc.get("version"));

        return self.reject_message;

    ################################################################################

    # **WARNING**
    # NB: this function can remove entries from the 'files' index [if
    # the .orig.tar.gz is a duplicate of the one in the archive]; if
    # you're iterating over 'files' and call this function as part of
    # the loop, be sure to add a check to the top of the loop to
    # ensure you haven't just tried to derefernece the deleted entry.
    # **WARNING**

    def check_dsc_against_db(self, file):
        self.reject_message = "";
        files = self.pkg.files;
        dsc_files = self.pkg.dsc_files;
        legacy_source_untouchable = self.pkg.legacy_source_untouchable;
        orig_tar_gz = None;

        # Try and find all files mentioned in the .dsc.  This has
        # to work harder to cope with the multiple possible
        # locations of an .orig.tar.gz.
        for dsc_file in dsc_files.keys():
            found = None;
            if files.has_key(dsc_file):
                actual_md5 = files[dsc_file]["md5sum"];
                actual_size = int(files[dsc_file]["size"]);
                found = "%s in incoming" % (dsc_file)
                # Check the file does not already exist in the archive
                q = self.projectB.query("SELECT size, md5sum, filename FROM files WHERE filename LIKE '%%%s%%'" % (dsc_file));

                ql = q.getresult();
                # Strip out anything that isn't '%s' or '/%s$'
                for i in ql:
                    if i[2] != dsc_file and i[2][-(len(dsc_file)+1):] != '/'+dsc_file:
                        self.Logger.log(["check_dsc_against_db",i[2],dsc_file]);
                        ql.remove(i);

                # "[katie] has not broken them.  [katie] has fixed a
                # brokenness.  Your crappy hack exploited a bug in
                # the old dinstall.
                #
                # "(Come on!  I thought it was always obvious that
                # one just doesn't release different files with
                # the same name and version.)"
                #                        -- ajk@ on d-devel@l.d.o

                if ql:
                    # Ignore exact matches for .orig.tar.gz
                    match = 0;
                    if dsc_file.endswith(".orig.tar.gz"):
                        for i in ql:
                            if files.has_key(dsc_file) and \
                               int(files[dsc_file]["size"]) == int(i[0]) and \
                               files[dsc_file]["md5sum"] == i[1]:
                                self.reject("ignoring %s, since it's already in the archive." % (dsc_file), "Warning: ");
                                del files[dsc_file];
                                match = 1;

                    if not match:
                        self.reject("can not overwrite existing copy of '%s' already in the archive." % (dsc_file));
            elif dsc_file.endswith(".orig.tar.gz"):
                # Check in the pool
                q = self.projectB.query("SELECT l.path, f.filename, l.type, f.id, l.id FROM files f, location l WHERE f.filename LIKE '%%%s%%' AND l.id = f.location" % (dsc_file));
                ql = q.getresult();
                # Strip out anything that isn't '%s' or '/%s$'
                for i in ql:
                    if i[1] != dsc_file and i[1][-(len(dsc_file)+1):] != '/'+dsc_file:
                        self.Logger.log(["check_dsc_against_db",i[1],dsc_file]);
                        ql.remove(i);

                if ql:
                    # Unfortunately, we make get more than one
                    # match here if, for example, the package was
                    # in potato but had a -sa upload in woody.  So
                    # we need to choose the right one.

                    x = ql[0]; # default to something sane in case we don't match any or have only one

                    if len(ql) > 1:
                        for i in ql:
                            old_file = i[0] + i[1];
                            actual_md5 = apt_pkg.md5sum(utils.open_file(old_file));
                            actual_size = os.stat(old_file)[stat.ST_SIZE];
                            if actual_md5 == dsc_files[dsc_file]["md5sum"] and actual_size == int(dsc_files[dsc_file]["size"]):
                                x = i;
                            else:
                                legacy_source_untouchable[i[3]] = "";

                    old_file = x[0] + x[1];
                    actual_md5 = apt_pkg.md5sum(utils.open_file(old_file));
                    actual_size = os.stat(old_file)[stat.ST_SIZE];
                    found = old_file;
                    suite_type = x[2];
                    dsc_files[dsc_file]["files id"] = x[3]; # need this for updating dsc_files in install()
                    # See install() in katie...
                    self.pkg.orig_tar_id = x[3];
                    if suite_type == "legacy" or suite_type == "legacy-mixed":
                        self.pkg.orig_tar_location = "legacy";
                    else:
                        self.pkg.orig_tar_location = x[4];
                else:
                    # Not there? Check the queue directories...

                    in_unchecked = os.path.join(self.Cnf["Dir::Queue::Unchecked"],dsc_file);
                    # See process_it() in jennifer for explanation of this
                    if os.path.exists(in_unchecked):
                        return (self.reject_message, in_unchecked);
                    else:
                        for dir in [ "Accepted", "New", "Byhand" ]:
                            in_otherdir = os.path.join(self.Cnf["Dir::Queue::%s" % (dir)],dsc_file);
                            if os.path.exists(in_otherdir):
                                actual_md5 = apt_pkg.md5sum(utils.open_file(in_otherdir));
                                actual_size = os.stat(in_otherdir)[stat.ST_SIZE];
                                found = in_otherdir;

                    if not found:
                        self.reject("%s refers to %s, but I can't find it in the queue or in the pool." % (file, dsc_file));
                        continue;
            else:
                self.reject("%s refers to %s, but I can't find it in the queue." % (file, dsc_file));
                continue;
            if actual_md5 != dsc_files[dsc_file]["md5sum"]:
                self.reject("md5sum for %s doesn't match %s." % (found, file));
            if actual_size != int(dsc_files[dsc_file]["size"]):
                self.reject("size for %s doesn't match %s." % (found, file));

        return (self.reject_message, orig_tar_gz);

    def do_query(self, q):
        sys.stderr.write("query: \"%s\" ... " % (q));
        before = time.time();
        r = self.projectB.query(q);
        time_diff = time.time()-before;
        sys.stderr.write("took %.3f seconds.\n" % (time_diff));
        return r;
