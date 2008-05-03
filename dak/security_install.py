#!/usr/bin/env python

# Wrapper for Debian Security team
# Copyright (C) 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA

################################################################################

# <aj> neuro: <usual question>?
# <neuro> aj: PPG: the movie!  july 3!
# <aj> _PHWOAR_!!!!!
# <aj> (you think you can distract me, and you're right)
# <aj> urls?!
# <aj> promo videos?!
# <aj> where, where!?

################################################################################

import commands, os, pwd, re, sys, time
import apt_pkg
import daklib.queue as queue
import daklib.utils

################################################################################

Cnf = None
Options = None
Upload = None

re_taint_free = re.compile(r"^['/;\-\+\.\s\w]+$")

################################################################################

def usage (exit_code=0):
    print """Usage: dak security-install ADV_NUMBER CHANGES_FILE[...]
Install CHANGES_FILE(s) as security advisory ADV_NUMBER

  -h, --help                 show this help and exit
  -n, --no-action            don't do anything

"""
    sys.exit(exit_code)

################################################################################

def do_upload(changes_files):
    file_list = ""
    suites = {}
    component_mapping = {}
    for component in Cnf.SubTree("Security-Install::ComponentMappings").List():
        component_mapping[component] = Cnf["Security-Install::ComponentMappings::%s" % (component)]
    uploads = {}; # uploads[uri] = file_list
    changesfiles = {}; # changesfiles[uri] = file_list
    package_list = {} # package_list[source_name][version]
    changes_files.sort(daklib.utils.changes_compare)
    for changes_file in changes_files:
        changes_file = daklib.utils.validate_changes_file_arg(changes_file)
        # Reset variables
        components = {}
        upload_uris = {}
        file_list = []
        Upload.init_vars()
        # Parse the .dak file for the .changes file
        Upload.pkg.changes_file = changes_file
        Upload.update_vars()
        files = Upload.pkg.files
        changes = Upload.pkg.changes
        dsc = Upload.pkg.dsc
        # We have the changes, now return if its amd64, to not upload them to ftp-master
        if changes["architecture"].has_key("amd64"):
            print "Not uploading amd64 part to ftp-master\n"
            continue
        # Build the file list for this .changes file
        for f in files.keys():
            poolname = os.path.join(Cnf["Dir::Root"], Cnf["Dir::PoolRoot"],
                                    daklib.utils.poolify(changes["source"], files[f]["component"]),
                                    f)
            file_list.append(poolname)
            orig_component = files[f].get("original component", files[f]["component"])
            components[orig_component] = ""
        # Determine the upload uri for this .changes file
        for component in components.keys():
            upload_uri = component_mapping.get(component)
            if upload_uri:
                upload_uris[upload_uri] = ""
        num_upload_uris = len(upload_uris.keys())
        if num_upload_uris == 0:
            daklib.utils.fubar("%s: No valid upload URI found from components (%s)."
                        % (changes_file, ", ".join(components.keys())))
        elif num_upload_uris > 1:
            daklib.utils.fubar("%s: more than one upload URI (%s) from components (%s)."
                        % (changes_file, ", ".join(upload_uris.keys()),
                           ", ".join(components.keys())))
        upload_uri = upload_uris.keys()[0]
        # Update the file list for the upload uri
        if not uploads.has_key(upload_uri):
            uploads[upload_uri] = []
        uploads[upload_uri].extend(file_list)
        # Update the changes list for the upload uri
        if not changesfiles.has_key(upload_uri):
            changesfiles[upload_uri] = []
        changesfiles[upload_uri].append(changes_file)
        # Remember the suites and source name/version
        for suite in changes["distribution"].keys():
            suites[suite] = ""
        # Remember the source name and version
        if changes["architecture"].has_key("source") and \
           changes["distribution"].has_key("testing"):
            if not package_list.has_key(dsc["source"]):
                package_list[dsc["source"]] = {}
            package_list[dsc["source"]][dsc["version"]] = ""

    if not Options["No-Action"]:
        answer = yes_no("Upload to files to main archive (Y/n)?")
        if answer != "y":
            return

    for uri in uploads.keys():
        uploads[uri].extend(changesfiles[uri])
        (host, path) = uri.split(":")
        file_list = " ".join(uploads[uri])
        print "Uploading files to %s..." % (host)
        spawn("lftp -c 'open %s; cd %s; put %s'" % (host, path, file_list))

    if not Options["No-Action"]:
        filename = "%s/testing-processed" % (Cnf["Dir::Log"])
        f = daklib.utils.open_file(filename, 'a')
        for source in package_list.keys():
            for version in package_list[source].keys():
                f.write(" ".join([source, version])+'\n')
        f.close()

######################################################################
# This function was originally written by aj and NIHishly merged into
# 'dak security-install' by me.

def make_advisory(advisory_nr, changes_files):
    adv_packages = []
    updated_pkgs = {};  # updated_pkgs[distro][arch][file] = {path,md5,size}

    for arg in changes_files:
        arg = daklib.utils.validate_changes_file_arg(arg)
        Upload.pkg.changes_file = arg
        Upload.init_vars()
        Upload.update_vars()

        src = Upload.pkg.changes["source"]
        if src not in adv_packages:
            adv_packages += [src]

        suites = Upload.pkg.changes["distribution"].keys()
        for suite in suites:
            if not updated_pkgs.has_key(suite):
                updated_pkgs[suite] = {}

        files = Upload.pkg.files
        for f in files.keys():
            arch = files[f]["architecture"]
            md5 = files[f]["md5sum"]
            size = files[f]["size"]
            poolname = Cnf["Dir::PoolRoot"] + \
                daklib.utils.poolify(src, files[f]["component"])
            if arch == "source" and f.endswith(".dsc"):
                dscpoolname = poolname
            for suite in suites:
                if not updated_pkgs[suite].has_key(arch):
                    updated_pkgs[suite][arch] = {}
                updated_pkgs[suite][arch][f] = {
                    "md5": md5, "size": size,
                    "poolname": poolname }

        dsc_files = Upload.pkg.dsc_files
        for f in dsc_files.keys():
            arch = "source"
            if not dsc_files[f].has_key("files id"):
                continue

            # otherwise, it's already in the pool and needs to be
            # listed specially
            md5 = dsc_files[f]["md5sum"]
            size = dsc_files[f]["size"]
            for suite in suites:
                if not updated_pkgs[suite].has_key(arch):
                    updated_pkgs[suite][arch] = {}
                updated_pkgs[suite][arch][f] = {
                    "md5": md5, "size": size,
                    "poolname": dscpoolname }

    if os.environ.has_key("SUDO_UID"):
        whoami = long(os.environ["SUDO_UID"])
    else:
        whoami = os.getuid()
    whoamifull = pwd.getpwuid(whoami)
    username = whoamifull[4].split(",")[0]

    Subst = {
        "__ADVISORY__": advisory_nr,
        "__WHOAMI__": username,
        "__DATE__": time.strftime("%B %d, %Y", time.gmtime(time.time())),
        "__PACKAGE__": ", ".join(adv_packages),
        "__DAK_ADDRESS__": Cnf["Dinstall::MyEmailAddress"]
        }

    if Cnf.has_key("Dinstall::Bcc"):
        Subst["__BCC__"] = "Bcc: %s" % (Cnf["Dinstall::Bcc"])

    adv = ""
    archive = Cnf["Archive::%s::PrimaryMirror" % (daklib.utils.where_am_i())]
    for suite in updated_pkgs.keys():
        suite_header = "%s %s (%s)" % (Cnf["Dinstall::MyDistribution"],
                                       Cnf["Suite::%s::Version" % suite], suite)
        adv += "%s\n%s\n\n" % (suite_header, "-"*len(suite_header))

        arches = Cnf.ValueList("Suite::%s::Architectures" % suite)
        if "source" in arches:
            arches.remove("source")
        if "all" in arches:
            arches.remove("all")
        arches.sort()

        adv += "  %s was released for %s.\n\n" % (
                suite.capitalize(), daklib.utils.join_with_commas_and(arches))

        for a in ["source", "all"] + arches:
            if not updated_pkgs[suite].has_key(a):
                continue

            if a == "source":
                adv += "  Source archives:\n\n"
            elif a == "all":
                adv += "  Architecture independent packages:\n\n"
            else:
                adv += "  %s architecture (%s)\n\n" % (a,
                        Cnf["Architectures::%s" % a])

            for f in updated_pkgs[suite][a].keys():
                adv += "    http://%s/%s%s\n" % (
                                archive, updated_pkgs[suite][a][f]["poolname"], f)
                adv += "      Size/MD5 checksum: %8s %s\n" % (
                        updated_pkgs[suite][a][f]["size"],
                        updated_pkgs[suite][a][f]["md5"])
            adv += "\n"
    adv = adv.rstrip()

    Subst["__ADVISORY_TEXT__"] = adv

    adv = daklib.utils.TemplateSubst(Subst, Cnf["Dir::Templates"]+"/security-install.advisory")
    if not Options["No-Action"]:
        daklib.utils.send_mail (adv)
    else:
        print "[<Would send template advisory mail>]"

######################################################################

def init():
    global Cnf, Upload, Options

    apt_pkg.init()
    Cnf = daklib.utils.get_conf()

    Arguments = [('h', "help", "Security-Install::Options::Help"),
                 ('n', "no-action", "Security-Install::Options::No-Action")]

    for i in [ "help", "no-action" ]:
        Cnf["Security-Install::Options::%s" % (i)] = ""

    arguments = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Security-Install::Options")
    Upload = queue.Upload(Cnf)

    if Options["Help"]:
        usage(0)

    if not arguments:
        usage(1)

    advisory_number = arguments[0]
    changes_files = arguments[1:]
    if advisory_number.endswith(".changes"):
        daklib.utils.warn("first argument must be the advisory number.")
        usage(1)
    for f in changes_files:
        f = daklib.utils.validate_changes_file_arg(f)
    return (advisory_number, changes_files)

######################################################################

def yes_no(prompt):
    while 1:
        answer = daklib.utils.our_raw_input(prompt+" ").lower()
        if answer == "y" or answer == "n":
            break
        else:
            print "Invalid answer; please try again."
    return answer

######################################################################

def spawn(command):
    if not re_taint_free.match(command):
        daklib.utils.fubar("Invalid character in \"%s\"." % (command))

    if Options["No-Action"]:
        print "[%s]" % (command)
    else:
        (result, output) = commands.getstatusoutput(command)
        if (result != 0):
            daklib.utils.fubar("Invocation of '%s' failed:\n%s\n" % (command, output), result)

######################################################################


def main():
    print "Disabled. See your team@security email, and/or contact aj on OFTC."
    sys.exit(1)

    (advisory_number, changes_files) = init()

    if not Options["No-Action"]:
        print "About to install the following files: "
        for f in changes_files:
            print "  %s" % (f)
        answer = yes_no("Continue (Y/n)?")
        if answer == "n":
            sys.exit(0)

    os.chdir(Cnf["Dir::Queue::Accepted"])
    print "Installing packages into the archive..."
    spawn("dak process-accepted -pa %s" % (" ".join(changes_files)))
    os.chdir(Cnf["Dir::Dak"])
    print "Updating file lists for apt-ftparchive..."
    spawn("dak make-suite-file-list")
    print "Updating Packages and Sources files..."
    spawn("apt-ftparchive generate %s" % (daklib.utils.which_apt_conf_file()))
    print "Updating Release files..."
    spawn("dak generate-releases")

    if not Options["No-Action"]:
        os.chdir(Cnf["Dir::Queue::Done"])
    else:
        os.chdir(Cnf["Dir::Queue::Accepted"])
    print "Generating template advisory..."
    make_advisory(advisory_number, changes_files)

    # Trigger security mirrors
    spawn("sudo -u archvsync /home/archvsync/signal_security")

    do_upload(changes_files)

################################################################################

if __name__ == '__main__':
    main()

################################################################################
