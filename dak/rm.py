#!/usr/bin/env python

# General purpose package removal tool for ftpmaster
# Copyright (C) 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>

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

# o OpenBSD team wants to get changes incorporated into IPF. Darren no
#    respond.
# o Ask again -> No respond. Darren coder supreme.
# o OpenBSD decide to make changes, but only in OpenBSD source
#    tree. Darren hears, gets angry! Decides: "LICENSE NO ALLOW!"
# o Insert Flame War.
# o OpenBSD team decide to switch to different packet filter under BSD
#    license. Because Project Goal: Every user should be able to make
#    changes to source tree. IPF license bad!!
# o Darren try get back: says, NetBSD, FreeBSD allowed! MUAHAHAHAH!!!
# o Theo say: no care, pf much better than ipf!
# o Darren changes mind: changes license. But OpenBSD will not change
#    back to ipf. Darren even much more bitter.
# o Darren so bitterbitter. Decides: I'LL GET BACK BY FORKING OPENBSD AND
#    RELEASING MY OWN VERSION. HEHEHEHEHE.

#                        http://slashdot.org/comments.pl?sid=26697&cid=2883271

################################################################################

import commands, os, pg, re, sys
import apt_pkg, apt_inst
from daklib import database
from daklib import utils
from daklib.dak_exceptions import *

################################################################################

re_strip_source_version = re.compile (r'\s+.*$')
re_build_dep_arch = re.compile(r"\[[^]]+\]")

################################################################################

Cnf = None
Options = None
projectB = None

################################################################################

def usage (exit_code=0):
    print """Usage: dak rm [OPTIONS] PACKAGE[...]
Remove PACKAGE(s) from suite(s).

  -a, --architecture=ARCH    only act on this architecture
  -b, --binary               remove binaries only
  -c, --component=COMPONENT  act on this component
  -C, --carbon-copy=EMAIL    send a CC of removal message to EMAIL
  -d, --done=BUG#            send removal message as closure to bug#
  -h, --help                 show this help and exit
  -m, --reason=MSG           reason for removal
  -n, --no-action            don't do anything
  -p, --partial              don't affect override files
  -R, --rdep-check           check reverse dependencies
  -s, --suite=SUITE          act on this suite
  -S, --source-only          remove source only

ARCH, BUG#, COMPONENT and SUITE can be comma (or space) separated lists, e.g.
    --architecture=m68k,i386"""

    sys.exit(exit_code)

################################################################################

# "Hudson: What that's great, that's just fucking great man, now what
#  the fuck are we supposed to do? We're in some real pretty shit now
#  man...That's it man, game over man, game over, man! Game over! What
#  the fuck are we gonna do now? What are we gonna do?"

def game_over():
    answer = utils.our_raw_input("Continue (y/N)? ").lower()
    if answer != "y":
        print "Aborted."
        sys.exit(1)

################################################################################

def reverse_depends_check(removals, suites, arches=None):
    print "Checking reverse dependencies..."
    components = Cnf.ValueList("Suite::%s::Components" % suites[0])
    dep_problem = 0
    p2c = {}
    all_broken = {}
    if arches:
        all_arches = set(arches)
    else:
        all_arches = set(Cnf.ValueList("Suite::%s::Architectures" % suites[0]))
    all_arches -= set(["source", "all"])
    for architecture in all_arches:
        deps = {}
        sources = {}
        virtual_packages = {}
        for component in components:
            filename = "%s/dists/%s/%s/binary-%s/Packages.gz" % (Cnf["Dir::Root"], suites[0], component, architecture)
            # apt_pkg.ParseTagFile needs a real file handle and can't handle a GzipFile instance...
            temp_filename = utils.temp_filename()
            (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
            if (result != 0):
                utils.fubar("Gunzip invocation failed!\n%s\n" % (output), result)
            packages = utils.open_file(temp_filename)
            Packages = apt_pkg.ParseTagFile(packages)
            while Packages.Step():
                package = Packages.Section.Find("Package")
                source = Packages.Section.Find("Source")
                if not source:
                    source = package
                elif ' ' in source:
                    source = source.split(' ', 1)[0]
                sources[package] = source
                depends = Packages.Section.Find("Depends")
                if depends:
                    deps[package] = depends
                provides = Packages.Section.Find("Provides")
                # Maintain a counter for each virtual package.  If a
                # Provides: exists, set the counter to 0 and count all
                # provides by a package not in the list for removal.
                # If the counter stays 0 at the end, we know that only
                # the to-be-removed packages provided this virtual
                # package.
                if provides:
                    for virtual_pkg in provides.split(","):
                        virtual_pkg = virtual_pkg.strip()
                        if virtual_pkg == package: continue
                        if not virtual_packages.has_key(virtual_pkg):
                            virtual_packages[virtual_pkg] = 0
                        if package not in removals:
                            virtual_packages[virtual_pkg] += 1
                p2c[package] = component
            packages.close()
            os.unlink(temp_filename)

        # If a virtual package is only provided by the to-be-removed
        # packages, treat the virtual package as to-be-removed too.
        for virtual_pkg in virtual_packages.keys():
            if virtual_packages[virtual_pkg] == 0:
                removals.append(virtual_pkg)

        # Check binary dependencies (Depends)
        for package in deps.keys():
            if package in removals: continue
            parsed_dep = []
            try:
                parsed_dep += apt_pkg.ParseDepends(deps[package])
            except ValueError, e:
                print "Error for package %s: %s" % (package, e)
            for dep in parsed_dep:
                # Check for partial breakage.  If a package has a ORed
                # dependency, there is only a dependency problem if all
                # packages in the ORed depends will be removed.
                unsat = 0
                for dep_package, _, _ in dep:
                    if dep_package in removals:
                        unsat += 1
                if unsat == len(dep):
                    component = p2c[package]
                    source = sources[package]
                    if component != "main":
                        source = "%s/%s" % (source, component)
                    all_broken.setdefault(source, {}).setdefault(package, set()).add(architecture)
                    dep_problem = 1

    if all_broken:
        print "# Broken Depends:"
        for source, bindict in sorted(all_broken.items()):
            lines = []
            for binary, arches in sorted(bindict.items()):
                if arches == all_arches:
                    lines.append(binary)
                else:
                    lines.append('%s [%s]' % (binary, ' '.join(sorted(arches))))
            print '%s: %s' % (source, lines[0])
            for line in lines[1:]:
                print ' ' * (len(source) + 2) + line
        print

    # Check source dependencies (Build-Depends and Build-Depends-Indep)
    all_broken.clear()
    for component in components:
        filename = "%s/dists/%s/%s/source/Sources.gz" % (Cnf["Dir::Root"], suites[0], component)
        # apt_pkg.ParseTagFile needs a real file handle and can't handle a GzipFile instance...
        temp_filename = utils.temp_filename()
        result, output = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
        if result != 0:
            sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
            sys.exit(result)
        sources = utils.open_file(temp_filename, "r")
        Sources = apt_pkg.ParseTagFile(sources)
        while Sources.Step():
            source = Sources.Section.Find("Package")
            if source in removals: continue
            parsed_dep = []
            for build_dep_type in ["Build-Depends", "Build-Depends-Indep"]:
                build_dep = Sources.Section.get(build_dep_type)
                if build_dep:
                    # Remove [arch] information since we want to see breakage on all arches
                    build_dep = re_build_dep_arch.sub("", build_dep)
                    try:
                        parsed_dep += apt_pkg.ParseDepends(build_dep)
                    except ValueError, e:
                        print "Error for source %s: %s" % (source, e)
            for dep in parsed_dep:
                unsat = 0
                for dep_package, _, _ in dep:
                    if dep_package in removals:
                        unsat += 1
                if unsat == len(dep):
                    if component != "main":
                        source = "%s/%s" % (source, component)
                    all_broken.setdefault(source, set()).add(utils.pp_deps(dep))
                    dep_problem = 1
        sources.close()
        os.unlink(temp_filename)

    if all_broken:
        print "# Broken Build-Depends:"
        for source, bdeps in sorted(all_broken.items()):
            bdeps = sorted(bdeps)
            print '%s: %s' % (source, bdeps[0])
            for bdep in bdeps[1:]:
                print ' ' * (len(source) + 2) + bdep
        print

    if dep_problem:
        print "Dependency problem found."
        if not Options["No-Action"]:
            game_over()
    else:
        print "No dependency problem found."
    print

################################################################################

def main ():
    global Cnf, Options, projectB

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Rm::Options::Help"),
                 ('a',"architecture","Rm::Options::Architecture", "HasArg"),
                 ('b',"binary", "Rm::Options::Binary-Only"),
                 ('c',"component", "Rm::Options::Component", "HasArg"),
                 ('C',"carbon-copy", "Rm::Options::Carbon-Copy", "HasArg"), # Bugs to Cc
                 ('d',"done","Rm::Options::Done", "HasArg"), # Bugs fixed
                 ('R',"rdep-check", "Rm::Options::Rdep-Check"),
                 ('m',"reason", "Rm::Options::Reason", "HasArg"), # Hysterical raisins; -m is old-dinstall option for rejection reason
                 ('n',"no-action","Rm::Options::No-Action"),
                 ('p',"partial", "Rm::Options::Partial"),
                 ('s',"suite","Rm::Options::Suite", "HasArg"),
                 ('S',"source-only", "Rm::Options::Source-Only"),
                 ]

    for i in [ "architecture", "binary-only", "carbon-copy", "component",
               "done", "help", "no-action", "partial", "rdep-check", "reason",
               "source-only" ]:
        if not Cnf.has_key("Rm::Options::%s" % (i)):
            Cnf["Rm::Options::%s" % (i)] = ""
    if not Cnf.has_key("Rm::Options::Suite"):
        Cnf["Rm::Options::Suite"] = "unstable"

    arguments = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Options = Cnf.SubTree("Rm::Options")

    if Options["Help"]:
        usage()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    # Sanity check options
    if not arguments:
        utils.fubar("need at least one package name as an argument.")
    if Options["Architecture"] and Options["Source-Only"]:
        utils.fubar("can't use -a/--architecture and -S/--source-only options simultaneously.")
    if Options["Binary-Only"] and Options["Source-Only"]:
        utils.fubar("can't use -b/--binary-only and -S/--source-only options simultaneously.")
    if Options.has_key("Carbon-Copy") and not Options.has_key("Done"):
        utils.fubar("can't use -C/--carbon-copy without also using -d/--done option.")
    if Options["Architecture"] and not Options["Partial"]:
        utils.warn("-a/--architecture implies -p/--partial.")
        Options["Partial"] = "true"

    # Force the admin to tell someone if we're not doing a 'dak
    # cruft-report' inspired removal (or closing a bug, which counts
    # as telling someone).
    if not Options["No-Action"] and not Options["Carbon-Copy"] \
           and not Options["Done"] and Options["Reason"].find("[auto-cruft]") == -1:
        utils.fubar("Need a -C/--carbon-copy if not closing a bug and not doing a cruft removal.")

    # Process -C/--carbon-copy
    #
    # Accept 3 types of arguments (space separated):
    #  1) a number - assumed to be a bug number, i.e. nnnnn@bugs.debian.org
    #  2) the keyword 'package' - cc's $package@packages.debian.org for every argument
    #  3) contains a '@' - assumed to be an email address, used unmofidied
    #
    carbon_copy = []
    for copy_to in utils.split_args(Options.get("Carbon-Copy")):
        if copy_to.isdigit():
            carbon_copy.append(copy_to + "@" + Cnf["Dinstall::BugServer"])
        elif copy_to == 'package':
            for package in arguments:
                carbon_copy.append(package + "@" + Cnf["Dinstall::PackagesServer"])
                if Cnf.has_key("Dinstall::TrackingServer"):
                    carbon_copy.append(package + "@" + Cnf["Dinstall::TrackingServer"])
        elif '@' in copy_to:
            carbon_copy.append(copy_to)
        else:
            utils.fubar("Invalid -C/--carbon-copy argument '%s'; not a bug number, 'package' or email address." % (copy_to))

    if Options["Binary-Only"]:
        field = "b.package"
    else:
        field = "s.source"
    con_packages = "AND %s IN (%s)" % (field, ", ".join([ repr(i) for i in arguments ]))

    (con_suites, con_architectures, con_components, check_source) = \
                 utils.parse_args(Options)

    # Additional suite checks
    suite_ids_list = []
    suites = utils.split_args(Options["Suite"])
    suites_list = utils.join_with_commas_and(suites)
    if not Options["No-Action"]:
        for suite in suites:
            suite_id = database.get_suite_id(suite)
            if suite_id != -1:
                suite_ids_list.append(suite_id)
            if suite == "stable":
                print "**WARNING** About to remove from the stable suite!"
                print "This should only be done just prior to a (point) release and not at"
                print "any other time."
                game_over()
            elif suite == "testing":
                print "**WARNING About to remove from the testing suite!"
                print "There's no need to do this normally as removals from unstable will"
                print "propogate to testing automagically."
                game_over()

    # Additional architecture checks
    if Options["Architecture"] and check_source:
        utils.warn("'source' in -a/--argument makes no sense and is ignored.")

    # Additional component processing
    over_con_components = con_components.replace("c.id", "component")

    print "Working...",
    sys.stdout.flush()
    to_remove = []
    maintainers = {}

    # We have 3 modes of package selection: binary-only, source-only
    # and source+binary.  The first two are trivial and obvious; the
    # latter is a nasty mess, but very nice from a UI perspective so
    # we try to support it.

    if Options["Binary-Only"]:
        # Binary-only
        q = projectB.query("SELECT b.package, b.version, a.arch_string, b.id, b.maintainer FROM binaries b, bin_associations ba, architecture a, suite su, files f, location l, component c WHERE ba.bin = b.id AND ba.suite = su.id AND b.architecture = a.id AND b.file = f.id AND f.location = l.id AND l.component = c.id %s %s %s %s" % (con_packages, con_suites, con_components, con_architectures))
        for i in q.getresult():
            to_remove.append(i)
    else:
        # Source-only
        source_packages = {}
        q = projectB.query("SELECT l.path, f.filename, s.source, s.version, 'source', s.id, s.maintainer FROM source s, src_associations sa, suite su, files f, location l, component c WHERE sa.source = s.id AND sa.suite = su.id AND s.file = f.id AND f.location = l.id AND l.component = c.id %s %s %s" % (con_packages, con_suites, con_components))
        for i in q.getresult():
            source_packages[i[2]] = i[:2]
            to_remove.append(i[2:])
        if not Options["Source-Only"]:
            # Source + Binary
            binary_packages = {}
            # First get a list of binary package names we suspect are linked to the source
            q = projectB.query("SELECT DISTINCT b.package FROM binaries b, source s, src_associations sa, suite su, files f, location l, component c WHERE b.source = s.id AND sa.source = s.id AND sa.suite = su.id AND s.file = f.id AND f.location = l.id AND l.component = c.id %s %s %s" % (con_packages, con_suites, con_components))
            for i in q.getresult():
                binary_packages[i[0]] = ""
            # Then parse each .dsc that we found earlier to see what binary packages it thinks it produces
            for i in source_packages.keys():
                filename = "/".join(source_packages[i])
                try:
                    dsc = utils.parse_changes(filename)
                except CantOpenError:
                    utils.warn("couldn't open '%s'." % (filename))
                    continue
                for package in dsc.get("binary").split(','):
                    package = package.strip()
                    binary_packages[package] = ""
            # Then for each binary package: find any version in
            # unstable, check the Source: field in the deb matches our
            # source package and if so add it to the list of packages
            # to be removed.
            for package in binary_packages.keys():
                q = projectB.query("SELECT l.path, f.filename, b.package, b.version, a.arch_string, b.id, b.maintainer FROM binaries b, bin_associations ba, architecture a, suite su, files f, location l, component c WHERE ba.bin = b.id AND ba.suite = su.id AND b.architecture = a.id AND b.file = f.id AND f.location = l.id AND l.component = c.id %s %s %s AND b.package = '%s'" % (con_suites, con_components, con_architectures, package))
                for i in q.getresult():
                    filename = "/".join(i[:2])
                    control = apt_pkg.ParseSection(apt_inst.debExtractControl(utils.open_file(filename)))
                    source = control.Find("Source", control.Find("Package"))
                    source = re_strip_source_version.sub('', source)
                    if source_packages.has_key(source):
                        to_remove.append(i[2:])
    print "done."

    if not to_remove:
        print "Nothing to do."
        sys.exit(0)

    # If we don't have a reason; spawn an editor so the user can add one
    # Write the rejection email out as the <foo>.reason file
    if not Options["Reason"] and not Options["No-Action"]:
        temp_filename = utils.temp_filename()
        editor = os.environ.get("EDITOR","vi")
        result = os.system("%s %s" % (editor, temp_filename))
        if result != 0:
            utils.fubar ("vi invocation failed for `%s'!" % (temp_filename), result)
        temp_file = utils.open_file(temp_filename)
        for line in temp_file.readlines():
            Options["Reason"] += line
        temp_file.close()
        os.unlink(temp_filename)

    # Generate the summary of what's to be removed
    d = {}
    for i in to_remove:
        package = i[0]
        version = i[1]
        architecture = i[2]
        maintainer = i[4]
        maintainers[maintainer] = ""
        if not d.has_key(package):
            d[package] = {}
        if not d[package].has_key(version):
            d[package][version] = []
        if architecture not in d[package][version]:
            d[package][version].append(architecture)

    maintainer_list = []
    for maintainer_id in maintainers.keys():
        maintainer_list.append(database.get_maintainer(maintainer_id))
    summary = ""
    removals = d.keys()
    removals.sort()
    for package in removals:
        versions = d[package].keys()
        versions.sort(apt_pkg.VersionCompare)
        for version in versions:
            d[package][version].sort(utils.arch_compare_sw)
            summary += "%10s | %10s | %s\n" % (package, version, ", ".join(d[package][version]))
    print "Will remove the following packages from %s:" % (suites_list)
    print
    print summary
    print "Maintainer: %s" % ", ".join(maintainer_list)
    if Options["Done"]:
        print "Will also close bugs: "+Options["Done"]
    if carbon_copy:
        print "Will also send CCs to: " + ", ".join(carbon_copy)
    print
    print "------------------- Reason -------------------"
    print Options["Reason"]
    print "----------------------------------------------"
    print

    if Options["Rdep-Check"]:
        arches = utils.split_args(Options["Architecture"])
        reverse_depends_check(removals, suites, arches)

    # If -n/--no-action, drop out here
    if Options["No-Action"]:
        sys.exit(0)

    print "Going to remove the packages now."
    game_over()

    whoami = utils.whoami()
    date = commands.getoutput('date -R')

    # Log first; if it all falls apart I want a record that we at least tried.
    logfile = utils.open_file(Cnf["Rm::LogFile"], 'a')
    logfile.write("=========================================================================\n")
    logfile.write("[Date: %s] [ftpmaster: %s]\n" % (date, whoami))
    logfile.write("Removed the following packages from %s:\n\n%s" % (suites_list, summary))
    if Options["Done"]:
        logfile.write("Closed bugs: %s\n" % (Options["Done"]))
    logfile.write("\n------------------- Reason -------------------\n%s\n" % (Options["Reason"]))
    logfile.write("----------------------------------------------\n")
    logfile.flush()

    dsc_type_id = database.get_override_type_id('dsc')
    deb_type_id = database.get_override_type_id('deb')

    # Do the actual deletion
    print "Deleting...",
    sys.stdout.flush()
    projectB.query("BEGIN WORK")
    for i in to_remove:
        package = i[0]
        architecture = i[2]
        package_id = i[3]
        for suite_id in suite_ids_list:
            if architecture == "source":
                projectB.query("DELETE FROM src_associations WHERE source = %s AND suite = %s" % (package_id, suite_id))
                #print "DELETE FROM src_associations WHERE source = %s AND suite = %s" % (package_id, suite_id)
            else:
                projectB.query("DELETE FROM bin_associations WHERE bin = %s AND suite = %s" % (package_id, suite_id))
                #print "DELETE FROM bin_associations WHERE bin = %s AND suite = %s" % (package_id, suite_id)
            # Delete from the override file
            if not Options["Partial"]:
                if architecture == "source":
                    type_id = dsc_type_id
                else:
                    type_id = deb_type_id
                projectB.query("DELETE FROM override WHERE package = '%s' AND type = %s AND suite = %s %s" % (package, type_id, suite_id, over_con_components))
    projectB.query("COMMIT WORK")
    print "done."

    # Send the bug closing messages
    if Options["Done"]:
        Subst = {}
        Subst["__RM_ADDRESS__"] = Cnf["Rm::MyEmailAddress"]
        Subst["__BUG_SERVER__"] = Cnf["Dinstall::BugServer"]
        bcc = []
        if Cnf.Find("Dinstall::Bcc") != "":
            bcc.append(Cnf["Dinstall::Bcc"])
        if Cnf.Find("Rm::Bcc") != "":
            bcc.append(Cnf["Rm::Bcc"])
        if bcc:
            Subst["__BCC__"] = "Bcc: " + ", ".join(bcc)
        else:
            Subst["__BCC__"] = "X-Filler: 42"
        Subst["__CC__"] = "X-DAK: dak rm\nX-Katie: melanie"
        if carbon_copy:
            Subst["__CC__"] += "\nCc: " + ", ".join(carbon_copy)
        Subst["__SUITE_LIST__"] = suites_list
        Subst["__SUMMARY__"] = summary
        Subst["__ADMIN_ADDRESS__"] = Cnf["Dinstall::MyAdminAddress"]
        Subst["__DISTRO__"] = Cnf["Dinstall::MyDistribution"]
        Subst["__WHOAMI__"] = whoami
        whereami = utils.where_am_i()
        Archive = Cnf.SubTree("Archive::%s" % (whereami))
        Subst["__MASTER_ARCHIVE__"] = Archive["OriginServer"]
        Subst["__PRIMARY_MIRROR__"] = Archive["PrimaryMirror"]
        for bug in utils.split_args(Options["Done"]):
            Subst["__BUG_NUMBER__"] = bug
            mail_message = utils.TemplateSubst(Subst,Cnf["Dir::Templates"]+"/rm.bug-close")
            utils.send_mail(mail_message)

    logfile.write("=========================================================================\n")
    logfile.close()

#######################################################################################

if __name__ == '__main__':
    main()
