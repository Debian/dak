#!/usr/bin/env python

# Checks Debian packages from Incoming
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>

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

# Originally based on dinstall by Guy Maor <maor@debian.org>

################################################################################

# Computer games don't affect kids. I mean if Pacman affected our generation as
# kids, we'd all run around in a darkened room munching pills and listening to
# repetitive music.
#         -- Unknown

################################################################################

import commands, errno, fcntl, os, re, shutil, stat, sys, time, tempfile, traceback
import apt_inst, apt_pkg
import daklib.database
import daklib.logging
import daklib.queue 
import daklib.utils

from types import *

################################################################################

re_valid_version = re.compile(r"^([0-9]+:)?[0-9A-Za-z\.\-\+:~]+$")
re_valid_pkg_name = re.compile(r"^[\dA-Za-z][\dA-Za-z\+\-\.]+$")
re_changelog_versions = re.compile(r"^\w[-+0-9a-z.]+ \([^\(\) \t]+\)")
re_strip_revision = re.compile(r"-([^-]+)$")
re_strip_srcver = re.compile(r"\s+\(\S+\)$")

################################################################################

# Globals
Cnf = None
Options = None
Logger = None
Upload = None

reprocess = 0
in_holding = {}

# Aliases to the real vars in the Upload class; hysterical raisins.
reject_message = ""
changes = {}
dsc = {}
dsc_files = {}
files = {}
pkg = {}

###############################################################################

def init():
    global Cnf, Options, Upload, changes, dsc, dsc_files, files, pkg

    apt_pkg.init()

    Cnf = apt_pkg.newConfiguration()
    apt_pkg.ReadConfigFileISC(Cnf,daklib.utils.which_conf_file())

    Arguments = [('a',"automatic","Dinstall::Options::Automatic"),
                 ('h',"help","Dinstall::Options::Help"),
                 ('n',"no-action","Dinstall::Options::No-Action"),
                 ('p',"no-lock", "Dinstall::Options::No-Lock"),
                 ('s',"no-mail", "Dinstall::Options::No-Mail")]

    for i in ["automatic", "help", "no-action", "no-lock", "no-mail",
              "override-distribution", "version"]:
        Cnf["Dinstall::Options::%s" % (i)] = ""

    changes_files = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Dinstall::Options")

    if Options["Help"]:
        usage()

    Upload = daklib.queue.Upload(Cnf)

    changes = Upload.pkg.changes
    dsc = Upload.pkg.dsc
    dsc_files = Upload.pkg.dsc_files
    files = Upload.pkg.files
    pkg = Upload.pkg

    return changes_files

################################################################################

def usage (exit_code=0):
    print """Usage: dinstall [OPTION]... [CHANGES]...
  -a, --automatic           automatic run
  -h, --help                show this help and exit.
  -n, --no-action           don't do anything
  -p, --no-lock             don't check lockfile !! for cron.daily only !!
  -s, --no-mail             don't send any mail
  -V, --version             display the version number and exit"""
    sys.exit(exit_code)

################################################################################

def reject (str, prefix="Rejected: "):
    global reject_message
    if str:
        reject_message += prefix + str + "\n"

################################################################################

def copy_to_holding(filename):
    global in_holding

    base_filename = os.path.basename(filename)

    dest = Cnf["Dir::Queue::Holding"] + '/' + base_filename
    try:
        fd = os.open(dest, os.O_RDWR|os.O_CREAT|os.O_EXCL, 0640)
        os.close(fd)
    except OSError, e:
        # Shouldn't happen, but will if, for example, someone lists a
        # file twice in the .changes.
        if errno.errorcode[e.errno] == 'EEXIST':
            reject("%s: already exists in holding area; can not overwrite." % (base_filename))
            return
        raise

    try:
        shutil.copy(filename, dest)
    except IOError, e:
        # In either case (ENOENT or EACCES) we want to remove the
        # O_CREAT | O_EXCLed ghost file, so add the file to the list
        # of 'in holding' even if it's not the real file.
        if errno.errorcode[e.errno] == 'ENOENT':
            reject("%s: can not copy to holding area: file not found." % (base_filename))
            os.unlink(dest)
            return
        elif errno.errorcode[e.errno] == 'EACCES':
            reject("%s: can not copy to holding area: read permission denied." % (base_filename))
            os.unlink(dest)
            return
        raise

    in_holding[base_filename] = ""

################################################################################

def clean_holding():
    global in_holding

    cwd = os.getcwd()
    os.chdir(Cnf["Dir::Queue::Holding"])
    for file in in_holding.keys():
        if os.path.exists(file):
            if file.find('/') != -1:
                daklib.utils.fubar("WTF? clean_holding() got a file ('%s') with / in it!" % (file))
            else:
                os.unlink(file)
    in_holding = {}
    os.chdir(cwd)

################################################################################

def check_changes():
    filename = pkg.changes_file

    # Parse the .changes field into a dictionary
    try:
        changes.update(daklib.utils.parse_changes(filename))
    except daklib.utils.cant_open_exc:
        reject("%s: can't read file." % (filename))
        return 0
    except daklib.utils.changes_parse_error_exc, line:
        reject("%s: parse error, can't grok: %s." % (filename, line))
        return 0

    # Parse the Files field from the .changes into another dictionary
    try:
        files.update(daklib.utils.build_file_list(changes))
    except daklib.utils.changes_parse_error_exc, line:
        reject("%s: parse error, can't grok: %s." % (filename, line))
    except daklib.utils.nk_format_exc, format:
        reject("%s: unknown format '%s'." % (filename, format))
        return 0

    # Check for mandatory fields
    for i in ("source", "binary", "architecture", "version", "distribution",
              "maintainer", "files", "changes", "description"):
        if not changes.has_key(i):
            reject("%s: Missing mandatory field `%s'." % (filename, i))
            return 0    # Avoid <undef> errors during later tests

    # Strip a source version in brackets from the source field
    if re_strip_srcver.search(changes["source"]):
	changes["source"] = re_strip_srcver.sub('', changes["source"])

    # Ensure the source field is a valid package name.
    if not re_valid_pkg_name.match(changes["source"]):
        reject("%s: invalid source name '%s'." % (filename, changes["source"]))

    # Split multi-value fields into a lower-level dictionary
    for i in ("architecture", "distribution", "binary", "closes"):
        o = changes.get(i, "")
        if o != "":
            del changes[i]
        changes[i] = {}
        for j in o.split():
            changes[i][j] = 1

    # Fix the Maintainer: field to be RFC822/2047 compatible
    try:
        (changes["maintainer822"], changes["maintainer2047"],
         changes["maintainername"], changes["maintaineremail"]) = \
         daklib.utils.fix_maintainer (changes["maintainer"])
    except daklib.utils.ParseMaintError, msg:
        reject("%s: Maintainer field ('%s') failed to parse: %s" \
               % (filename, changes["maintainer"], msg))

    # ...likewise for the Changed-By: field if it exists.
    try:
        (changes["changedby822"], changes["changedby2047"],
         changes["changedbyname"], changes["changedbyemail"]) = \
         daklib.utils.fix_maintainer (changes.get("changed-by", ""))
    except daklib.utils.ParseMaintError, msg:
        (changes["changedby822"], changes["changedby2047"],
         changes["changedbyname"], changes["changedbyemail"]) = \
	 ("", "", "", "")
        reject("%s: Changed-By field ('%s') failed to parse: %s" \
               % (filename, changes["changed-by"], msg))

    # Ensure all the values in Closes: are numbers
    if changes.has_key("closes"):
        for i in changes["closes"].keys():
            if daklib.queue.re_isanum.match (i) == None:
                reject("%s: `%s' from Closes field isn't a number." % (filename, i))


    # chopversion = no epoch; chopversion2 = no epoch and no revision (e.g. for .orig.tar.gz comparison)
    changes["chopversion"] = daklib.utils.re_no_epoch.sub('', changes["version"])
    changes["chopversion2"] = daklib.utils.re_no_revision.sub('', changes["chopversion"])

    # Check there isn't already a changes file of the same name in one
    # of the queue directories.
    base_filename = os.path.basename(filename)
    for dir in [ "Accepted", "Byhand", "Done", "New", "ProposedUpdates", "OldProposedUpdates" ]:
        if os.path.exists(Cnf["Dir::Queue::%s" % (dir) ]+'/'+base_filename):
            reject("%s: a file with this name already exists in the %s directory." % (base_filename, dir))

    # Check the .changes is non-empty
    if not files:
        reject("%s: nothing to do (Files field is empty)." % (base_filename))
        return 0

    return 1

################################################################################

def check_distributions():
    "Check and map the Distribution field of a .changes file."

    # Handle suite mappings
    for map in Cnf.ValueList("SuiteMappings"):
        args = map.split()
        type = args[0]
        if type == "map" or type == "silent-map":
            (source, dest) = args[1:3]
            if changes["distribution"].has_key(source):
                del changes["distribution"][source]
                changes["distribution"][dest] = 1
                if type != "silent-map":
                    reject("Mapping %s to %s." % (source, dest),"")
            if changes.has_key("distribution-version"):
                if changes["distribution-version"].has_key(source):
                    changes["distribution-version"][source]=dest
        elif type == "map-unreleased":
            (source, dest) = args[1:3]
            if changes["distribution"].has_key(source):
                for arch in changes["architecture"].keys():
                    if arch not in Cnf.ValueList("Suite::%s::Architectures" % (source)):
                        reject("Mapping %s to %s for unreleased architecture %s." % (source, dest, arch),"")
                        del changes["distribution"][source]
                        changes["distribution"][dest] = 1
                        break
        elif type == "ignore":
            suite = args[1]
            if changes["distribution"].has_key(suite):
                del changes["distribution"][suite]
                reject("Ignoring %s as a target suite." % (suite), "Warning: ")
        elif type == "reject":
            suite = args[1]
            if changes["distribution"].has_key(suite):
                reject("Uploads to %s are not accepted." % (suite))
        elif type == "propup-version":
            # give these as "uploaded-to(non-mapped) suites-to-add-when-upload-obsoletes"
            #
            # changes["distribution-version"] looks like: {'testing': 'testing-proposed-updates'}
            if changes["distribution"].has_key(args[1]):
                changes.setdefault("distribution-version", {})
                for suite in args[2:]: changes["distribution-version"][suite]=suite

    # Ensure there is (still) a target distribution
    if changes["distribution"].keys() == []:
        reject("no valid distribution.")

    # Ensure target distributions exist
    for suite in changes["distribution"].keys():
        if not Cnf.has_key("Suite::%s" % (suite)):
            reject("Unknown distribution `%s'." % (suite))

################################################################################

def check_deb_ar(filename, control):
    """Sanity check the ar of a .deb, i.e. that there is:

 o debian-binary
 o control.tar.gz
 o data.tar.gz or data.tar.bz2

in that order, and nothing else."""
    cmd = "ar t %s" % (filename)
    (result, output) = commands.getstatusoutput(cmd)
    if result != 0:
        reject("%s: 'ar t' invocation failed." % (filename))
        reject(daklib.utils.prefix_multi_line_string(output, " [ar output:] "), "")
    chunks = output.split('\n')
    if len(chunks) != 3:
        reject("%s: found %d chunks, expected 3." % (filename, len(chunks)))
    if chunks[0] != "debian-binary":
        reject("%s: first chunk is '%s', expected 'debian-binary'." % (filename, chunks[0]))
    if chunks[1] != "control.tar.gz":
        reject("%s: second chunk is '%s', expected 'control.tar.gz'." % (filename, chunks[1]))
    if chunks[2] not in [ "data.tar.bz2", "data.tar.gz" ]:
        reject("%s: third chunk is '%s', expected 'data.tar.gz' or 'data.tar.bz2'." % (filename, chunks[2]))

################################################################################

def check_files():
    global reprocess

    archive = daklib.utils.where_am_i()
    file_keys = files.keys()

    # if reprocess is 2 we've already done this and we're checking
    # things again for the new .orig.tar.gz.
    # [Yes, I'm fully aware of how disgusting this is]
    if not Options["No-Action"] and reprocess < 2:
        cwd = os.getcwd()
        os.chdir(pkg.directory)
        for file in file_keys:
            copy_to_holding(file)
        os.chdir(cwd)

    # Check there isn't already a .changes or .dak file of the same name in
    # the proposed-updates "CopyChanges" or "CopyDotDak" storage directories.
    # [NB: this check must be done post-suite mapping]
    base_filename = os.path.basename(pkg.changes_file)
    dot_dak_filename = base_filename[:-8]+".dak"
    for suite in changes["distribution"].keys():
        copychanges = "Suite::%s::CopyChanges" % (suite)
        if Cnf.has_key(copychanges) and \
               os.path.exists(Cnf[copychanges]+"/"+base_filename):
            reject("%s: a file with this name already exists in %s" \
                   % (base_filename, Cnf[copychanges]))

        copy_dot_dak = "Suite::%s::CopyDotDak" % (suite)
        if Cnf.has_key(copy_dot_dak) and \
               os.path.exists(Cnf[copy_dot_dak]+"/"+dot_dak_filename):
            reject("%s: a file with this name already exists in %s" \
                   % (dot_dak_filename, Cnf[copy_dot_dak]))

    reprocess = 0
    has_binaries = 0
    has_source = 0

    for file in file_keys:
        # Ensure the file does not already exist in one of the accepted directories
        for dir in [ "Accepted", "Byhand", "New", "ProposedUpdates", "OldProposedUpdates", "Embargoed", "Unembargoed" ]:
	    if not Cnf.has_key("Dir::Queue::%s" % (dir)): continue
            if os.path.exists(Cnf["Dir::Queue::%s" % (dir) ]+'/'+file):
                reject("%s file already exists in the %s directory." % (file, dir))
        if not daklib.utils.re_taint_free.match(file):
            reject("!!WARNING!! tainted filename: '%s'." % (file))
        # Check the file is readable
        if os.access(file,os.R_OK) == 0:
            # When running in -n, copy_to_holding() won't have
            # generated the reject_message, so we need to.
            if Options["No-Action"]:
                if os.path.exists(file):
                    reject("Can't read `%s'. [permission denied]" % (file))
                else:
                    reject("Can't read `%s'. [file not found]" % (file))
            files[file]["type"] = "unreadable"
            continue
        # If it's byhand skip remaining checks
        if files[file]["section"] == "byhand" or files[file]["section"][4:] == "raw-":
            files[file]["byhand"] = 1
            files[file]["type"] = "byhand"
        # Checks for a binary package...
        elif daklib.utils.re_isadeb.match(file):
            has_binaries = 1
            files[file]["type"] = "deb"

            # Extract package control information
            deb_file = daklib.utils.open_file(file)
            try:
                control = apt_pkg.ParseSection(apt_inst.debExtractControl(deb_file))
            except:
                reject("%s: debExtractControl() raised %s." % (file, sys.exc_type))
                deb_file.close()
                # Can't continue, none of the checks on control would work.
                continue
            deb_file.close()

            # Check for mandatory fields
            for field in [ "Package", "Architecture", "Version" ]:
                if control.Find(field) == None:
                    reject("%s: No %s field in control." % (file, field))
                    # Can't continue
                    continue

            # Ensure the package name matches the one give in the .changes
            if not changes["binary"].has_key(control.Find("Package", "")):
                reject("%s: control file lists name as `%s', which isn't in changes file." % (file, control.Find("Package", "")))

            # Validate the package field
            package = control.Find("Package")
            if not re_valid_pkg_name.match(package):
                reject("%s: invalid package name '%s'." % (file, package))

            # Validate the version field
            version = control.Find("Version")
            if not re_valid_version.match(version):
                reject("%s: invalid version number '%s'." % (file, version))

            # Ensure the architecture of the .deb is one we know about.
            default_suite = Cnf.get("Dinstall::DefaultSuite", "Unstable")
            architecture = control.Find("Architecture")
            if architecture not in Cnf.ValueList("Suite::%s::Architectures" % (default_suite)):
                reject("Unknown architecture '%s'." % (architecture))

            # Ensure the architecture of the .deb is one of the ones
            # listed in the .changes.
            if not changes["architecture"].has_key(architecture):
                reject("%s: control file lists arch as `%s', which isn't in changes file." % (file, architecture))

            # Sanity-check the Depends field
            depends = control.Find("Depends")
            if depends == '':
                reject("%s: Depends field is empty." % (file))

            # Check the section & priority match those given in the .changes (non-fatal)
            if control.Find("Section") and files[file]["section"] != "" and files[file]["section"] != control.Find("Section"):
                reject("%s control file lists section as `%s', but changes file has `%s'." % (file, control.Find("Section", ""), files[file]["section"]), "Warning: ")
            if control.Find("Priority") and files[file]["priority"] != "" and files[file]["priority"] != control.Find("Priority"):
                reject("%s control file lists priority as `%s', but changes file has `%s'." % (file, control.Find("Priority", ""), files[file]["priority"]),"Warning: ")

            files[file]["package"] = package
            files[file]["architecture"] = architecture
            files[file]["version"] = version
            files[file]["maintainer"] = control.Find("Maintainer", "")
            if file.endswith(".udeb"):
                files[file]["dbtype"] = "udeb"
            elif file.endswith(".deb"):
                files[file]["dbtype"] = "deb"
            else:
                reject("%s is neither a .deb or a .udeb." % (file))
            files[file]["source"] = control.Find("Source", files[file]["package"])
            # Get the source version
            source = files[file]["source"]
            source_version = ""
            if source.find("(") != -1:
                m = daklib.utils.re_extract_src_version.match(source)
                source = m.group(1)
                source_version = m.group(2)
            if not source_version:
                source_version = files[file]["version"]
            files[file]["source package"] = source
            files[file]["source version"] = source_version

            # Ensure the filename matches the contents of the .deb
            m = daklib.utils.re_isadeb.match(file)
            #  package name
            file_package = m.group(1)
            if files[file]["package"] != file_package:
                reject("%s: package part of filename (%s) does not match package name in the %s (%s)." % (file, file_package, files[file]["dbtype"], files[file]["package"]))
            epochless_version = daklib.utils.re_no_epoch.sub('', control.Find("Version"))
            #  version
            file_version = m.group(2)
            if epochless_version != file_version:
                reject("%s: version part of filename (%s) does not match package version in the %s (%s)." % (file, file_version, files[file]["dbtype"], epochless_version))
            #  architecture
            file_architecture = m.group(3)
            if files[file]["architecture"] != file_architecture:
                reject("%s: architecture part of filename (%s) does not match package architecture in the %s (%s)." % (file, file_architecture, files[file]["dbtype"], files[file]["architecture"]))

            # Check for existent source
            source_version = files[file]["source version"]
            source_package = files[file]["source package"]
            if changes["architecture"].has_key("source"):
                if source_version != changes["version"]:
                    reject("source version (%s) for %s doesn't match changes version %s." % (source_version, file, changes["version"]))
            else:
                # Check in the SQL database
                if not Upload.source_exists(source_package, source_version, changes["distribution"].keys()):
                    # Check in one of the other directories
                    source_epochless_version = daklib.utils.re_no_epoch.sub('', source_version)
                    dsc_filename = "%s_%s.dsc" % (source_package, source_epochless_version)
                    if os.path.exists(Cnf["Dir::Queue::Byhand"] + '/' + dsc_filename):
                        files[file]["byhand"] = 1
                    elif os.path.exists(Cnf["Dir::Queue::New"] + '/' + dsc_filename):
                        files[file]["new"] = 1
                    else:
		        dsc_file_exists = 0
                        for myq in ["Accepted", "Embargoed", "Unembargoed", "ProposedUpdates", "OldProposedUpdates"]:
			    if Cnf.has_key("Dir::Queue::%s" % (myq)):
				if os.path.exists(Cnf["Dir::Queue::"+myq] + '/' + dsc_filename):
				    dsc_file_exists = 1
				    break
			if not dsc_file_exists:
                            reject("no source found for %s %s (%s)." % (source_package, source_version, file))
            # Check the version and for file overwrites
            reject(Upload.check_binary_against_db(file),"")

            check_deb_ar(file, control)

        # Checks for a source package...
        else:
            m = daklib.utils.re_issource.match(file)
            if m:
                has_source = 1
                files[file]["package"] = m.group(1)
                files[file]["version"] = m.group(2)
                files[file]["type"] = m.group(3)

                # Ensure the source package name matches the Source filed in the .changes
                if changes["source"] != files[file]["package"]:
                    reject("%s: changes file doesn't say %s for Source" % (file, files[file]["package"]))

                # Ensure the source version matches the version in the .changes file
                if files[file]["type"] == "orig.tar.gz":
                    changes_version = changes["chopversion2"]
                else:
                    changes_version = changes["chopversion"]
                if changes_version != files[file]["version"]:
                    reject("%s: should be %s according to changes file." % (file, changes_version))

                # Ensure the .changes lists source in the Architecture field
                if not changes["architecture"].has_key("source"):
                    reject("%s: changes file doesn't list `source' in Architecture field." % (file))

                # Check the signature of a .dsc file
                if files[file]["type"] == "dsc":
                    dsc["fingerprint"] = daklib.utils.check_signature(file, reject)

                files[file]["architecture"] = "source"

            # Not a binary or source package?  Assume byhand...
            else:
                files[file]["byhand"] = 1
                files[file]["type"] = "byhand"

        # Per-suite file checks
        files[file]["oldfiles"] = {}
        for suite in changes["distribution"].keys():
            # Skip byhand
            if files[file].has_key("byhand"):
                continue

            # Handle component mappings
            for map in Cnf.ValueList("ComponentMappings"):
                (source, dest) = map.split()
                if files[file]["component"] == source:
                    files[file]["original component"] = source
                    files[file]["component"] = dest

            # Ensure the component is valid for the target suite
            if Cnf.has_key("Suite:%s::Components" % (suite)) and \
               files[file]["component"] not in Cnf.ValueList("Suite::%s::Components" % (suite)):
                reject("unknown component `%s' for suite `%s'." % (files[file]["component"], suite))
                continue

            # Validate the component
            component = files[file]["component"]
            component_id = daklib.database.get_component_id(component)
            if component_id == -1:
                reject("file '%s' has unknown component '%s'." % (file, component))
                continue

            # See if the package is NEW
            if not Upload.in_override_p(files[file]["package"], files[file]["component"], suite, files[file].get("dbtype",""), file):
                files[file]["new"] = 1

            # Validate the priority
            if files[file]["priority"].find('/') != -1:
                reject("file '%s' has invalid priority '%s' [contains '/']." % (file, files[file]["priority"]))

            # Determine the location
            location = Cnf["Dir::Pool"]
            location_id = daklib.database.get_location_id (location, component, archive)
            if location_id == -1:
                reject("[INTERNAL ERROR] couldn't determine location (Component: %s, Archive: %s)" % (component, archive))
            files[file]["location id"] = location_id

            # Check the md5sum & size against existing files (if any)
            files[file]["pool name"] = daklib.utils.poolify (changes["source"], files[file]["component"])
            files_id = daklib.database.get_files_id(files[file]["pool name"] + file, files[file]["size"], files[file]["md5sum"], files[file]["location id"])
            if files_id == -1:
                reject("INTERNAL ERROR, get_files_id() returned multiple matches for %s." % (file))
            elif files_id == -2:
                reject("md5sum and/or size mismatch on existing copy of %s." % (file))
            files[file]["files id"] = files_id

            # Check for packages that have moved from one component to another
            q = Upload.projectB.query("""
SELECT c.name FROM binaries b, bin_associations ba, suite s, location l,
                   component c, architecture a, files f
 WHERE b.package = '%s' AND s.suite_name = '%s'
   AND (a.arch_string = '%s' OR a.arch_string = 'all')
   AND ba.bin = b.id AND ba.suite = s.id AND b.architecture = a.id
   AND f.location = l.id AND l.component = c.id AND b.file = f.id"""
                               % (files[file]["package"], suite,
                                  files[file]["architecture"]))
            ql = q.getresult()
            if ql:
                files[file]["othercomponents"] = ql[0][0]

    # If the .changes file says it has source, it must have source.
    if changes["architecture"].has_key("source"):
        if not has_source:
            reject("no source found and Architecture line in changes mention source.")

        if not has_binaries and Cnf.FindB("Dinstall::Reject::NoSourceOnly"):
            reject("source only uploads are not supported.")

###############################################################################

def check_dsc():
    global reprocess

    # Ensure there is source to check
    if not changes["architecture"].has_key("source"):
        return 1

    # Find the .dsc
    dsc_filename = None
    for file in files.keys():
        if files[file]["type"] == "dsc":
            if dsc_filename:
                reject("can not process a .changes file with multiple .dsc's.")
                return 0
            else:
                dsc_filename = file

    # If there isn't one, we have nothing to do. (We have reject()ed the upload already)
    if not dsc_filename:
        reject("source uploads must contain a dsc file")
        return 0

    # Parse the .dsc file
    try:
        dsc.update(daklib.utils.parse_changes(dsc_filename, signing_rules=1))
    except daklib.utils.cant_open_exc:
        # if not -n copy_to_holding() will have done this for us...
        if Options["No-Action"]:
            reject("%s: can't read file." % (dsc_filename))
    except daklib.utils.changes_parse_error_exc, line:
        reject("%s: parse error, can't grok: %s." % (dsc_filename, line))
    except daklib.utils.invalid_dsc_format_exc, line:
        reject("%s: syntax error on line %s." % (dsc_filename, line))
    # Build up the file list of files mentioned by the .dsc
    try:
        dsc_files.update(daklib.utils.build_file_list(dsc, is_a_dsc=1))
    except daklib.utils.no_files_exc:
        reject("%s: no Files: field." % (dsc_filename))
        return 0
    except daklib.utils.changes_parse_error_exc, line:
        reject("%s: parse error, can't grok: %s." % (dsc_filename, line))
        return 0

    # Enforce mandatory fields
    for i in ("format", "source", "version", "binary", "maintainer", "architecture", "files"):
        if not dsc.has_key(i):
            reject("%s: missing mandatory field `%s'." % (dsc_filename, i))
            return 0

    # Validate the source and version fields
    if not re_valid_pkg_name.match(dsc["source"]):
        reject("%s: invalid source name '%s'." % (dsc_filename, dsc["source"]))
    if not re_valid_version.match(dsc["version"]):
        reject("%s: invalid version number '%s'." % (dsc_filename, dsc["version"]))

    # Bumping the version number of the .dsc breaks extraction by stable's
    # dpkg-source.  So let's not do that...
    if dsc["format"] != "1.0":
        reject("%s: incompatible 'Format' version produced by a broken version of dpkg-dev 1.9.1{3,4}." % (dsc_filename))

    # Validate the Maintainer field
    try:
        daklib.utils.fix_maintainer (dsc["maintainer"])
    except daklib.utils.ParseMaintError, msg:
        reject("%s: Maintainer field ('%s') failed to parse: %s" \
               % (dsc_filename, dsc["maintainer"], msg))

    # Validate the build-depends field(s)
    for field_name in [ "build-depends", "build-depends-indep" ]:
        field = dsc.get(field_name)
        if field:
            # Check for broken dpkg-dev lossage...
            if field.startswith("ARRAY"):
                reject("%s: invalid %s field produced by a broken version of dpkg-dev (1.10.11)" % (dsc_filename, field_name.title()))

            # Have apt try to parse them...
            try:
                apt_pkg.ParseSrcDepends(field)
            except:
                reject("%s: invalid %s field (can not be parsed by apt)." % (dsc_filename, field_name.title()))
                pass

    # Ensure the version number in the .dsc matches the version number in the .changes
    epochless_dsc_version = daklib.utils.re_no_epoch.sub('', dsc["version"])
    changes_version = files[dsc_filename]["version"]
    if epochless_dsc_version != files[dsc_filename]["version"]:
        reject("version ('%s') in .dsc does not match version ('%s') in .changes." % (epochless_dsc_version, changes_version))

    # Ensure there is a .tar.gz in the .dsc file
    has_tar = 0
    for f in dsc_files.keys():
        m = daklib.utils.re_issource.match(f)
        if not m:
            reject("%s: %s in Files field not recognised as source." % (dsc_filename, f))
	    continue
        type = m.group(3)
        if type == "orig.tar.gz" or type == "tar.gz":
            has_tar = 1
    if not has_tar:
        reject("%s: no .tar.gz or .orig.tar.gz in 'Files' field." % (dsc_filename))

    # Ensure source is newer than existing source in target suites
    reject(Upload.check_source_against_db(dsc_filename),"")

    (reject_msg, is_in_incoming) = Upload.check_dsc_against_db(dsc_filename)
    reject(reject_msg, "")
    if is_in_incoming:
        if not Options["No-Action"]:
            copy_to_holding(is_in_incoming)
        orig_tar_gz = os.path.basename(is_in_incoming)
        files[orig_tar_gz] = {}
        files[orig_tar_gz]["size"] = os.stat(orig_tar_gz)[stat.ST_SIZE]
        files[orig_tar_gz]["md5sum"] = dsc_files[orig_tar_gz]["md5sum"]
        files[orig_tar_gz]["section"] = files[dsc_filename]["section"]
        files[orig_tar_gz]["priority"] = files[dsc_filename]["priority"]
        files[orig_tar_gz]["component"] = files[dsc_filename]["component"]
        files[orig_tar_gz]["type"] = "orig.tar.gz"
        reprocess = 2

    return 1

################################################################################

def get_changelog_versions(source_dir):
    """Extracts a the source package and (optionally) grabs the
    version history out of debian/changelog for the BTS."""

    # Find the .dsc (again)
    dsc_filename = None
    for file in files.keys():
        if files[file]["type"] == "dsc":
            dsc_filename = file

    # If there isn't one, we have nothing to do. (We have reject()ed the upload already)
    if not dsc_filename:
        return

    # Create a symlink mirror of the source files in our temporary directory
    for f in files.keys():
        m = daklib.utils.re_issource.match(f)
        if m:
            src = os.path.join(source_dir, f)
            # If a file is missing for whatever reason, give up.
            if not os.path.exists(src):
                return
            type = m.group(3)
            if type == "orig.tar.gz" and pkg.orig_tar_gz:
                continue
            dest = os.path.join(os.getcwd(), f)
            os.symlink(src, dest)

    # If the orig.tar.gz is not a part of the upload, create a symlink to the
    # existing copy.
    if pkg.orig_tar_gz:
        dest = os.path.join(os.getcwd(), os.path.basename(pkg.orig_tar_gz))
        os.symlink(pkg.orig_tar_gz, dest)

    # Extract the source
    cmd = "dpkg-source -sn -x %s" % (dsc_filename)
    (result, output) = commands.getstatusoutput(cmd)
    if (result != 0):
        reject("'dpkg-source -x' failed for %s [return code: %s]." % (dsc_filename, result))
        reject(daklib.utils.prefix_multi_line_string(output, " [dpkg-source output:] "), "")
        return

    if not Cnf.Find("Dir::Queue::BTSVersionTrack"):
        return

    # Get the upstream version
    upstr_version = daklib.utils.re_no_epoch.sub('', dsc["version"])
    if re_strip_revision.search(upstr_version):
        upstr_version = re_strip_revision.sub('', upstr_version)

    # Ensure the changelog file exists
    changelog_filename = "%s-%s/debian/changelog" % (dsc["source"], upstr_version)
    if not os.path.exists(changelog_filename):
        reject("%s: debian/changelog not found in extracted source." % (dsc_filename))
        return

    # Parse the changelog
    dsc["bts changelog"] = ""
    changelog_file = daklib.utils.open_file(changelog_filename)
    for line in changelog_file.readlines():
        m = re_changelog_versions.match(line)
        if m:
            dsc["bts changelog"] += line
    changelog_file.close()

    # Check we found at least one revision in the changelog
    if not dsc["bts changelog"]:
        reject("%s: changelog format not recognised (empty version tree)." % (dsc_filename))

########################################

def check_source():
    # Bail out if:
    #    a) there's no source 
    # or b) reprocess is 2 - we will do this check next time when orig.tar.gz is in 'files'
    # or c) the orig.tar.gz is MIA
    if not changes["architecture"].has_key("source") or reprocess == 2 \
       or pkg.orig_tar_gz == -1:
        return

    # Create a temporary directory to extract the source into
    if Options["No-Action"]:
        tmpdir = tempfile.mktemp()
    else:
        # We're in queue/holding and can create a random directory.
        tmpdir = "%s" % (os.getpid())
    os.mkdir(tmpdir)

    # Move into the temporary directory
    cwd = os.getcwd()
    os.chdir(tmpdir)

    # Get the changelog version history
    get_changelog_versions(cwd)

    # Move back and cleanup the temporary tree
    os.chdir(cwd)
    try:
        shutil.rmtree(tmpdir)
    except OSError, e:
        if errno.errorcode[e.errno] != 'EACCES':
            daklib.utils.fubar("%s: couldn't remove tmp dir for source tree." % (dsc["source"]))

        reject("%s: source tree could not be cleanly removed." % (dsc["source"]))
        # We probably have u-r or u-w directories so chmod everything
        # and try again.
        cmd = "chmod -R u+rwx %s" % (tmpdir)
        result = os.system(cmd)
        if result != 0:
            daklib.utils.fubar("'%s' failed with result %s." % (cmd, result))
        shutil.rmtree(tmpdir)
    except:
        daklib.utils.fubar("%s: couldn't remove tmp dir for source tree." % (dsc["source"]))

################################################################################

# FIXME: should be a debian specific check called from a hook

def check_urgency ():
    if changes["architecture"].has_key("source"):
        if not changes.has_key("urgency"):
            changes["urgency"] = Cnf["Urgency::Default"]
        if changes["urgency"] not in Cnf.ValueList("Urgency::Valid"):
            reject("%s is not a valid urgency; it will be treated as %s by testing." % (changes["urgency"], Cnf["Urgency::Default"]), "Warning: ")
            changes["urgency"] = Cnf["Urgency::Default"]
        changes["urgency"] = changes["urgency"].lower()

################################################################################

def check_md5sums ():
    for file in files.keys():
        try:
            file_handle = daklib.utils.open_file(file)
        except daklib.utils.cant_open_exc:
            continue

        # Check md5sum
        if apt_pkg.md5sum(file_handle) != files[file]["md5sum"]:
            reject("%s: md5sum check failed." % (file))
        file_handle.close()
        # Check size
        actual_size = os.stat(file)[stat.ST_SIZE]
        size = int(files[file]["size"])
        if size != actual_size:
            reject("%s: actual file size (%s) does not match size (%s) in .changes"
                   % (file, actual_size, size))

    for file in dsc_files.keys():
        try:
            file_handle = daklib.utils.open_file(file)
        except daklib.utils.cant_open_exc:
            continue

        # Check md5sum
        if apt_pkg.md5sum(file_handle) != dsc_files[file]["md5sum"]:
            reject("%s: md5sum check failed." % (file))
        file_handle.close()
        # Check size
        actual_size = os.stat(file)[stat.ST_SIZE]
        size = int(dsc_files[file]["size"])
        if size != actual_size:
            reject("%s: actual file size (%s) does not match size (%s) in .dsc"
                   % (file, actual_size, size))

################################################################################

# Sanity check the time stamps of files inside debs.
# [Files in the near future cause ugly warnings and extreme time
#  travel can cause errors on extraction]

def check_timestamps():
    class Tar:
        def __init__(self, future_cutoff, past_cutoff):
            self.reset()
            self.future_cutoff = future_cutoff
            self.past_cutoff = past_cutoff

        def reset(self):
            self.future_files = {}
            self.ancient_files = {}

        def callback(self, Kind,Name,Link,Mode,UID,GID,Size,MTime,Major,Minor):
            if MTime > self.future_cutoff:
                self.future_files[Name] = MTime
            if MTime < self.past_cutoff:
                self.ancient_files[Name] = MTime
    ####

    future_cutoff = time.time() + int(Cnf["Dinstall::FutureTimeTravelGrace"])
    past_cutoff = time.mktime(time.strptime(Cnf["Dinstall::PastCutoffYear"],"%Y"))
    tar = Tar(future_cutoff, past_cutoff)
    for filename in files.keys():
        if files[filename]["type"] == "deb":
            tar.reset()
            try:
                deb_file = daklib.utils.open_file(filename)
                apt_inst.debExtract(deb_file,tar.callback,"control.tar.gz")
                deb_file.seek(0)
                try:
                    apt_inst.debExtract(deb_file,tar.callback,"data.tar.gz")
                except SystemError, e:
                    # If we can't find a data.tar.gz, look for data.tar.bz2 instead.
                    if not re.search(r"Cannot f[ui]nd chunk data.tar.gz$", str(e)):
                        raise
                    deb_file.seek(0)
                    apt_inst.debExtract(deb_file,tar.callback,"data.tar.bz2")
                deb_file.close()
                #
                future_files = tar.future_files.keys()
                if future_files:
                    num_future_files = len(future_files)
                    future_file = future_files[0]
                    future_date = tar.future_files[future_file]
                    reject("%s: has %s file(s) with a time stamp too far into the future (e.g. %s [%s])."
                           % (filename, num_future_files, future_file,
                              time.ctime(future_date)))
                #
                ancient_files = tar.ancient_files.keys()
                if ancient_files:
                    num_ancient_files = len(ancient_files)
                    ancient_file = ancient_files[0]
                    ancient_date = tar.ancient_files[ancient_file]
                    reject("%s: has %s file(s) with a time stamp too ancient (e.g. %s [%s])."
                           % (filename, num_ancient_files, ancient_file,
                              time.ctime(ancient_date)))
            except:
                reject("%s: deb contents timestamp check failed [%s: %s]" % (filename, sys.exc_type, sys.exc_value))

################################################################################

def lookup_uid_from_fingerprint(fpr):
    q = Upload.projectB.query("SELECT u.uid, u.name FROM fingerprint f, uid u WHERE f.uid = u.id AND f.fingerprint = '%s'" % (fpr))
    qs = q.getresult()
    if len(qs) == 0:
        return (None, None)
    else:
        return qs[0]

def check_signed_by_key():
    """Ensure the .changes is signed by an authorized uploader."""

    (uid, uid_name) = lookup_uid_from_fingerprint(changes["fingerprint"])
    if uid_name == None:
        uid_name = ""

    # match claimed name with actual name:
    if uid == None:
        uid, uid_email = changes["fingerprint"], uid
        may_nmu, may_sponsor = 1, 1
	# XXX by default new dds don't have a fingerprint/uid in the db atm,
	#     and can't get one in there if we don't allow nmu/sponsorship
    elif uid[:3] == "dm:":
        uid_email = uid[3:]
        may_nmu, may_sponsor = 0, 0
    else:
        uid_email = "%s@debian.org" % (uid)
        may_nmu, may_sponsor = 1, 1

    if uid_email in [changes["maintaineremail"], changes["changedbyemail"]]:
        sponsored = 0
    elif uid_name in [changes["maintainername"], changes["changedbyname"]]:
        sponsored = 0
        if uid_name == "": sponsored = 1
    else:
        sponsored = 1

    if sponsored and not may_sponsor: 
        reject("%s is not authorised to sponsor uploads" % (uid))

    if not sponsored and not may_nmu:
        source_ids = []
	check_suites = changes["distribution"].keys()
	if "unstable" not in check_suites: check_suites.append("unstable")
        for suite in check_suites:
            suite_id = daklib.database.get_suite_id(suite)
            q = Upload.projectB.query("SELECT s.id FROM source s JOIN src_associations sa ON (s.id = sa.source) WHERE s.source = '%s' AND sa.suite = %d" % (changes["source"], suite_id))
            for si in q.getresult():
                if si[0] not in source_ids: source_ids.append(si[0])

        print "source_ids: %s" % (",".join([str(x) for x in source_ids]))

        is_nmu = 1
        for si in source_ids:
            is_nmu = 1
            q = Upload.projectB.query("SELECT m.name FROM maintainer m WHERE m.id IN (SELECT maintainer FROM src_uploaders WHERE src_uploaders.source = %s)" % (si))
            for m in q.getresult():
                (rfc822, rfc2047, name, email) = daklib.utils.fix_maintainer(m[0])
                if email == uid_email or name == uid_name:
                    is_nmu=0
                    break
        if is_nmu:
            reject("%s may not upload/NMU source package %s" % (uid, changes["source"]))

        for b in changes["binary"].keys():
            for suite in changes["distribution"].keys():
                suite_id = daklib.database.get_suite_id(suite)
	        q = Upload.projectB.query("SELECT DISTINCT s.source FROM source s JOIN binaries b ON (s.id = b.source) JOIN bin_associations ba On (b.id = ba.bin) WHERE b.package = '%s' AND ba.suite = %s" % (b, suite_id))
		for s in q.getresult():
                    if s[0] != changes["source"]:
                        reject("%s may not hijack %s from source package %s in suite %s" % (uid, b, s, suite))

        for file in files.keys():
            if files[file].has_key("byhand"): 
                reject("%s may not upload BYHAND file %s" % (uid, file))
            if files[file].has_key("new"):
                reject("%s may not upload NEW file %s" % (uid, file))

    # The remaining checks only apply to binary-only uploads right now
    if changes["architecture"].has_key("source"):
        return

    if not Cnf.Exists("Binary-Upload-Restrictions"):
        return

    restrictions = Cnf.SubTree("Binary-Upload-Restrictions")

    # If the restrictions only apply to certain components make sure
    # that the upload is actual targeted there.
    if restrictions.Exists("Components"):
        restricted_components = restrictions.SubTree("Components").ValueList()
        is_restricted = False
        for file in files:
            if files[file]["component"] in restricted_components:
                is_restricted = True
                break
        if not is_restricted:
            return

    # Assuming binary only upload restrictions are in place we then
    # iterate over suite and architecture checking the key is in the
    # allowed list.  If no allowed list exists for a given suite or
    # architecture it's assumed to be open to anyone.
    for suite in changes["distribution"].keys():
        if not restrictions.Exists(suite):
            continue
        for arch in changes["architecture"].keys():
            if not restrictions.SubTree(suite).Exists(arch):
                continue
            allowed_keys = restrictions.SubTree("%s::%s" % (suite, arch)).ValueList()
            if changes["fingerprint"] not in allowed_keys:
                base_filename = os.path.basename(pkg.changes_file)
                reject("%s: not signed by authorised uploader for %s/%s"
                       % (base_filename, suite, arch))

################################################################################
################################################################################

# If any file of an upload has a recent mtime then chances are good
# the file is still being uploaded.

def upload_too_new():
    too_new = 0
    # Move back to the original directory to get accurate time stamps
    cwd = os.getcwd()
    os.chdir(pkg.directory)
    file_list = pkg.files.keys()
    file_list.extend(pkg.dsc_files.keys())
    file_list.append(pkg.changes_file)
    for file in file_list:
        try:
            last_modified = time.time()-os.path.getmtime(file)
            if last_modified < int(Cnf["Dinstall::SkipTime"]):
                too_new = 1
                break
        except:
            pass
    os.chdir(cwd)
    return too_new

################################################################################

def action ():
    # changes["distribution"] may not exist in corner cases
    # (e.g. unreadable changes files)
    if not changes.has_key("distribution") or not isinstance(changes["distribution"], DictType):
        changes["distribution"] = {}

    (summary, short_summary) = Upload.build_summaries()

    # q-unapproved hax0ring
    queue_info = {
         "New": { "is": is_new, "process": acknowledge_new },
	 "Autobyhand" : { "is" : is_autobyhand, "process": do_autobyhand },
         "Byhand" : { "is": is_byhand, "process": do_byhand },
         "OldStableUpdate" : { "is": is_oldstableupdate, 
	 			"process": do_oldstableupdate },
         "StableUpdate" : { "is": is_stableupdate, "process": do_stableupdate },
         "Unembargo" : { "is": is_unembargo, "process": queue_unembargo },
         "Embargo" : { "is": is_embargo, "process": queue_embargo },
    }
    queues = [ "New", "Autobyhand", "Byhand" ]
    if Cnf.FindB("Dinstall::SecurityQueueHandling"):
        queues += [ "Unembargo", "Embargo" ]
    else:
        queues += [ "OldStableUpdate", "StableUpdate" ]

    (prompt, answer) = ("", "XXX")
    if Options["No-Action"] or Options["Automatic"]:
        answer = 'S'

    queuekey = ''

    if reject_message.find("Rejected") != -1:
        if upload_too_new():
            print "SKIP (too new)\n" + reject_message,
            prompt = "[S]kip, Quit ?"
        else:
            print "REJECT\n" + reject_message,
            prompt = "[R]eject, Skip, Quit ?"
            if Options["Automatic"]:
                answer = 'R'
    else:
        queue = None
        for q in queues:
            if queue_info[q]["is"]():
                queue = q
                break
        if queue:
            print "%s for %s\n%s%s" % (
                queue.upper(), ", ".join(changes["distribution"].keys()), 
                reject_message, summary),
            queuekey = queue[0].upper()
            if queuekey in "RQSA":
                queuekey = "D"
                prompt = "[D]ivert, Skip, Quit ?"
            else:
                prompt = "[%s]%s, Skip, Quit ?" % (queuekey, queue[1:].lower())
            if Options["Automatic"]:
                answer = queuekey
        else:
            print "ACCEPT\n" + reject_message + summary,
            prompt = "[A]ccept, Skip, Quit ?"
            if Options["Automatic"]:
                answer = 'A'

    while prompt.find(answer) == -1:
        answer = daklib.utils.our_raw_input(prompt)
        m = daklib.queue.re_default_answer.match(prompt)
        if answer == "":
            answer = m.group(1)
        answer = answer[:1].upper()

    if answer == 'R':
        os.chdir (pkg.directory)
        Upload.do_reject(0, reject_message)
    elif answer == 'A':
        accept(summary, short_summary)
        remove_from_unchecked()
    elif answer == queuekey:
        queue_info[queue]["process"](summary, short_summary)
        remove_from_unchecked()
    elif answer == 'Q':
        sys.exit(0)

def remove_from_unchecked():
    os.chdir (pkg.directory)
    for file in files.keys():
        os.unlink(file)
    os.unlink(pkg.changes_file)

################################################################################

def accept (summary, short_summary):
    Upload.accept(summary, short_summary)
    Upload.check_override()

################################################################################

def move_to_dir (dest, perms=0660, changesperms=0664):
    daklib.utils.move (pkg.changes_file, dest, perms=changesperms)
    file_keys = files.keys()
    for file in file_keys:
        daklib.utils.move (file, dest, perms=perms)

################################################################################

def is_unembargo ():
    q = Upload.projectB.query(
      "SELECT package FROM disembargo WHERE package = '%s' AND version = '%s'" % 
      (changes["source"], changes["version"]))
    ql = q.getresult()
    if ql:
        return 1

    oldcwd = os.getcwd()
    os.chdir(Cnf["Dir::Queue::Disembargo"])
    disdir = os.getcwd()
    os.chdir(oldcwd)

    if pkg.directory == disdir:
        if changes["architecture"].has_key("source"):
            if Options["No-Action"]: return 1

            Upload.projectB.query(
              "INSERT INTO disembargo (package, version) VALUES ('%s', '%s')" % 
              (changes["source"], changes["version"]))
            return 1

    return 0

def queue_unembargo (summary, short_summary):
    print "Moving to UNEMBARGOED holding area."
    Logger.log(["Moving to unembargoed", pkg.changes_file])

    Upload.dump_vars(Cnf["Dir::Queue::Unembargoed"])
    move_to_dir(Cnf["Dir::Queue::Unembargoed"])
    Upload.queue_build("unembargoed", Cnf["Dir::Queue::Unembargoed"])

    # Check for override disparities
    Upload.Subst["__SUMMARY__"] = summary
    Upload.check_override()

################################################################################

def is_embargo ():
    # if embargoed queues are enabled always embargo
    return 1

def queue_embargo (summary, short_summary):
    print "Moving to EMBARGOED holding area."
    Logger.log(["Moving to embargoed", pkg.changes_file])

    Upload.dump_vars(Cnf["Dir::Queue::Embargoed"])
    move_to_dir(Cnf["Dir::Queue::Embargoed"])
    Upload.queue_build("embargoed", Cnf["Dir::Queue::Embargoed"])

    # Check for override disparities
    Upload.Subst["__SUMMARY__"] = summary
    Upload.check_override()

################################################################################

def is_stableupdate ():
    if not changes["distribution"].has_key("proposed-updates"):
	return 0

    if not changes["architecture"].has_key("source"):
        pusuite = daklib.database.get_suite_id("proposed-updates")
        q = Upload.projectB.query(
          "SELECT S.source FROM source s JOIN src_associations sa ON (s.id = sa.source) WHERE s.source = '%s' AND s.version = '%s' AND sa.suite = %d" % 
          (changes["source"], changes["version"], pusuite))
        ql = q.getresult()
        if ql:
            # source is already in proposed-updates so no need to hold
            return 0

    return 1

def do_stableupdate (summary, short_summary):
    print "Moving to PROPOSED-UPDATES holding area."
    Logger.log(["Moving to proposed-updates", pkg.changes_file]);

    Upload.dump_vars(Cnf["Dir::Queue::ProposedUpdates"]);
    move_to_dir(Cnf["Dir::Queue::ProposedUpdates"])

    # Check for override disparities
    Upload.Subst["__SUMMARY__"] = summary;
    Upload.check_override();

################################################################################

def is_oldstableupdate ():
    if not changes["distribution"].has_key("oldstable-proposed-updates"):
	return 0

    if not changes["architecture"].has_key("source"):
        pusuite = daklib.database.get_suite_id("oldstable-proposed-updates")
        q = Upload.projectB.query(
          "SELECT S.source FROM source s JOIN src_associations sa ON (s.id = sa.source) WHERE s.source = '%s' AND s.version = '%s' AND sa.suite = %d" % 
          (changes["source"], changes["version"], pusuite))
        ql = q.getresult()
        if ql:
            # source is already in oldstable-proposed-updates so no need to hold
            return 0

    return 1

def do_oldstableupdate (summary, short_summary):
    print "Moving to OLDSTABLE-PROPOSED-UPDATES holding area."
    Logger.log(["Moving to oldstable-proposed-updates", pkg.changes_file]);

    Upload.dump_vars(Cnf["Dir::Queue::OldProposedUpdates"]);
    move_to_dir(Cnf["Dir::Queue::OldProposedUpdates"])

    # Check for override disparities
    Upload.Subst["__SUMMARY__"] = summary;
    Upload.check_override();

################################################################################

def is_autobyhand ():
    all_auto = 1
    any_auto = 0
    for file in files.keys():
        if files[file].has_key("byhand"):
	    any_auto = 1

	    # filename is of form "PKG_VER_ARCH.EXT" where PKG, VER and ARCH
	    # don't contain underscores, and ARCH doesn't contain dots.
	    # further VER matches the .changes Version:, and ARCH should be in
	    # the .changes Architecture: list.
	    if file.count("_") < 2:
	    	all_auto = 0
		continue
	
	    (pkg, ver, archext) = file.split("_", 2)
	    if archext.count(".") < 1 or changes["version"] != ver:
	    	all_auto = 0
		continue

	    ABH = Cnf.SubTree("AutomaticByHandPackages")
	    if not ABH.has_key(pkg) or \
	      ABH["%s::Source" % (pkg)] != changes["source"]:
	        print "not match %s %s" % (pkg, changes["source"])
	        all_auto = 0
		continue

	    (arch, ext) = archext.split(".", 1)
	    if arch not in changes["architecture"]:
	        all_auto = 0
		continue

	    files[file]["byhand-arch"] = arch
	    files[file]["byhand-script"] = ABH["%s::Script" % (pkg)]

    return any_auto and all_auto

def do_autobyhand (summary, short_summary):
    print "Attempting AUTOBYHAND."
    byhandleft = 0
    for file in files.keys():
        byhandfile = file
        if not files[file].has_key("byhand"):
            continue
        if not files[file].has_key("byhand-script"):
            byhandleft = 1
            continue

        os.system("ls -l %s" % byhandfile)
        result = os.system("%s %s %s %s %s" % (
                files[file]["byhand-script"], byhandfile, 
                changes["version"], files[file]["byhand-arch"],
                os.path.abspath(pkg.changes_file)))
        if result == 0:
            os.unlink(byhandfile)
            del files[file]
        else:
            print "Error processing %s, left as byhand." % (file)
            byhandleft = 1

    if byhandleft:
        do_byhand(summary, short_summary)
    else:
        accept(summary, short_summary)

################################################################################

def is_byhand ():
    for file in files.keys():
        if files[file].has_key("byhand"):
            return 1
    return 0

def do_byhand (summary, short_summary):
    print "Moving to BYHAND holding area."
    Logger.log(["Moving to byhand", pkg.changes_file])

    Upload.dump_vars(Cnf["Dir::Queue::Byhand"])
    move_to_dir(Cnf["Dir::Queue::Byhand"])

    # Check for override disparities
    Upload.Subst["__SUMMARY__"] = summary
    Upload.check_override()

################################################################################

def is_new ():
    for file in files.keys():
        if files[file].has_key("new"):
            return 1
    return 0

def acknowledge_new (summary, short_summary):
    Subst = Upload.Subst

    print "Moving to NEW holding area."
    Logger.log(["Moving to new", pkg.changes_file])

    Upload.dump_vars(Cnf["Dir::Queue::New"])
    move_to_dir(Cnf["Dir::Queue::New"])

    if not Options["No-Mail"]:
        print "Sending new ack."
        Subst["__SUMMARY__"] = summary
        new_ack_message = daklib.utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/process-unchecked.new")
        daklib.utils.send_mail(new_ack_message)

################################################################################

# reprocess is necessary for the case of foo_1.2-1 and foo_1.2-2 in
# Incoming. -1 will reference the .orig.tar.gz, but -2 will not.
# Upload.check_dsc_against_db() can find the .orig.tar.gz but it will
# not have processed it during it's checks of -2.  If -1 has been
# deleted or otherwise not checked by 'dak process-unchecked', the
# .orig.tar.gz will not have been checked at all.  To get round this,
# we force the .orig.tar.gz into the .changes structure and reprocess
# the .changes file.

def process_it (changes_file):
    global reprocess, reject_message

    # Reset some globals
    reprocess = 1
    Upload.init_vars()
    # Some defaults in case we can't fully process the .changes file
    changes["maintainer2047"] = Cnf["Dinstall::MyEmailAddress"]
    changes["changedby2047"] = Cnf["Dinstall::MyEmailAddress"]
    reject_message = ""

    # Absolutize the filename to avoid the requirement of being in the
    # same directory as the .changes file.
    pkg.changes_file = os.path.abspath(changes_file)

    # Remember where we are so we can come back after cd-ing into the
    # holding directory.
    pkg.directory = os.getcwd()

    try:
        # If this is the Real Thing(tm), copy things into a private
        # holding directory first to avoid replacable file races.
        if not Options["No-Action"]:
            os.chdir(Cnf["Dir::Queue::Holding"])
            copy_to_holding(pkg.changes_file)
            # Relativize the filename so we use the copy in holding
            # rather than the original...
            pkg.changes_file = os.path.basename(pkg.changes_file)
        changes["fingerprint"] = daklib.utils.check_signature(pkg.changes_file, reject)
        if changes["fingerprint"]:
            valid_changes_p = check_changes()
        else:
            valid_changes_p = 0
        if valid_changes_p:
            while reprocess:
                check_distributions()
                check_files()
                valid_dsc_p = check_dsc()
                if valid_dsc_p:
                    check_source()
                check_md5sums()
                check_urgency()
                check_timestamps()
                check_signed_by_key()
        Upload.update_subst(reject_message)
        action()
    except SystemExit:
        raise
    except:
        print "ERROR"
	traceback.print_exc(file=sys.stderr)
        pass

    # Restore previous WD
    os.chdir(pkg.directory)

###############################################################################

def main():
    global Cnf, Options, Logger

    changes_files = init()

    # -n/--dry-run invalidates some other options which would involve things happening
    if Options["No-Action"]:
        Options["Automatic"] = ""

    # Ensure all the arguments we were given are .changes files
    for file in changes_files:
        if not file.endswith(".changes"):
            daklib.utils.warn("Ignoring '%s' because it's not a .changes file." % (file))
            changes_files.remove(file)

    if changes_files == []:
        daklib.utils.fubar("Need at least one .changes file as an argument.")

    # Check that we aren't going to clash with the daily cron job

    if not Options["No-Action"] and os.path.exists("%s/daily.lock" % (Cnf["Dir::Lock"])) and not Options["No-Lock"]:
        daklib.utils.fubar("Archive maintenance in progress.  Try again later.")

    # Obtain lock if not in no-action mode and initialize the log

    if not Options["No-Action"]:
        lock_fd = os.open(Cnf["Dinstall::LockFile"], os.O_RDWR | os.O_CREAT)
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError, e:
            if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EAGAIN':
                daklib.utils.fubar("Couldn't obtain lock; assuming another 'dak process-unchecked' is already running.")
            else:
                raise
        Logger = Upload.Logger = daklib.logging.Logger(Cnf, "process-unchecked")

    # debian-{devel-,}-changes@lists.debian.org toggles writes access based on this header
    bcc = "X-DAK: dak process-unchecked\nX-Katie: $Revision: 1.65 $"
    if Cnf.has_key("Dinstall::Bcc"):
        Upload.Subst["__BCC__"] = bcc + "\nBcc: %s" % (Cnf["Dinstall::Bcc"])
    else:
        Upload.Subst["__BCC__"] = bcc


    # Sort the .changes files so that we process sourceful ones first
    changes_files.sort(daklib.utils.changes_compare)

    # Process the changes files
    for changes_file in changes_files:
        print "\n" + changes_file
        try:
            process_it (changes_file)
        finally:
            if not Options["No-Action"]:
                clean_holding()

    accept_count = Upload.accept_count
    accept_bytes = Upload.accept_bytes
    if accept_count:
        sets = "set"
        if accept_count > 1:
            sets = "sets"
        print "Accepted %d package %s, %s." % (accept_count, sets, daklib.utils.size_type(int(accept_bytes)))
        Logger.log(["total",accept_count,accept_bytes])

    if not Options["No-Action"]:
        Logger.close()

################################################################################

if __name__ == '__main__':
    main()

