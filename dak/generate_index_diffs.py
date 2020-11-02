#!/usr/bin/env python

""" generates partial package updates list"""

###########################################################

# idea and basic implementation by Anthony, some changes by Andreas
# parts are stolen from 'dak generate-releases'
#
# Copyright (C) 2004, 2005, 2006  Anthony Towns <aj@azure.humbug.org.au>
# Copyright (C) 2004, 2005  Andreas Barth <aba@not.so.argh.org>

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


# < elmo> bah, don't bother me with annoying facts
# < elmo> I was on a roll


################################################################################

from __future__ import print_function

import sys
import os
import time
import apt_pkg

import daklib.daksubprocess

from daklib import utils
from daklib.dbconn import Archive, Component, DBConn, Suite, get_suite, get_suite_architectures

import re
from daklib.pdiff import PDiffIndex

re_includeinpdiff = re.compile(r"(Translation-[a-zA-Z_]+\.(?:bz2|xz))")

################################################################################

Cnf = None
Logger = None
Options = None

################################################################################


def usage(exit_code=0):
    print("""Usage: dak generate-index-diffs [OPTIONS] [suites]
Write out ed-style diffs to Packages/Source lists

  -h, --help            show this help and exit
  -a <archive>          generate diffs for suites in <archive>
  -c                    give the canonical path of the file
  -p                    name for the patch (defaults to current time)
  -d                    name for the hardlink farm for status
  -m                    how many diffs to generate
  -n                    take no action
  -v                    be verbose and list each file as we work on it
    """)
    sys.exit(exit_code)


def tryunlink(file):
    try:
        os.unlink(file)
    except OSError:
        print("warning: removing of %s denied" % (file))


def smartstat(file):
    for ext in ["", ".gz", ".bz2", ".xz"]:
        if os.path.isfile(file + ext):
            return (ext, os.stat(file + ext))
    return (None, None)


def smartlink(f, t):
    def call_decompressor(cmd, inpath, outpath):
        with open(inpath, "rb") as stdin, open(outpath, "wb") as stdout:
            return daklib.daksubprocess.check_call(cmd, stdin=stdin, stdout=stdout)

    if os.path.isfile(f):
        os.link(f, t)
    elif os.path.isfile("%s.gz" % (f)):
        call_decompressor(['gzip', '-d'], '{}.gz'.format(f), t)
    elif os.path.isfile("%s.bz2" % (f)):
        call_decompressor(['bzip2', '-d'], '{}.bz2'.format(f), t)
    elif os.path.isfile("%s.xz" % (f)):
        call_decompressor(['xz', '-d'], '{}.xz'.format(f), t)
    else:
        print("missing: %s" % (f))
        raise IOError(f)


def genchanges(Options, outdir, oldfile, origfile, maxdiffs=56):
    if "NoAct" in Options:
        print("Not acting on: od: %s, oldf: %s, origf: %s, md: %s" % (outdir, oldfile, origfile, maxdiffs))
        return

    patchname = Options["PatchName"]

    # origfile = /path/to/Packages
    # oldfile  = ./Packages
    # newfile  = ./Packages.tmp

    # (outdir, oldfile, origfile) = argv

    (oldext, oldstat) = smartstat(oldfile)
    (origext, origstat) = smartstat(origfile)
    if not origstat:
        print("%s: doesn't exist" % (origfile))
        return
    if not oldstat:
        print("%s: initial run" % (origfile))
        os.link(origfile + origext, oldfile + origext)
        return

    if oldstat[1:3] == origstat[1:3]:
        return

    upd = PDiffIndex(outdir, int(maxdiffs))

    if "CanonicalPath" in Options:
        upd.can_path = Options["CanonicalPath"]

    # generate_and_add_patch_file needs an uncompressed file
    # The `newfile` variable is our uncompressed copy of 'oldfile` thanks to
    # smartlink
    newfile = oldfile + ".new"
    if os.path.exists(newfile):
        os.unlink(newfile)
    smartlink(origfile, newfile)

    try:
        upd.generate_and_add_patch_file(oldfile, newfile, patchname)
    finally:
        os.unlink(newfile)

    upd.prune_patch_history()

    for obsolete_patch in upd.find_obsolete_patches():
        tryunlink(obsolete_patch)

    upd.update_index()

    os.unlink(oldfile + oldext)
    os.link(origfile + origext, oldfile + origext)


def main():
    global Cnf, Options, Logger

    os.umask(0o002)

    Cnf = utils.get_conf()
    Arguments = [('h', "help", "Generate-Index-Diffs::Options::Help"),
                  ('a', 'archive', 'Generate-Index-Diffs::Options::Archive', 'hasArg'),
                  ('c', None, "Generate-Index-Diffs::Options::CanonicalPath", "hasArg"),
                  ('p', "patchname", "Generate-Index-Diffs::Options::PatchName", "hasArg"),
                  ('d', "tmpdir", "Generate-Index-Diffs::Options::TempDir", "hasArg"),
                  ('m', "maxdiffs", "Generate-Index-Diffs::Options::MaxDiffs", "hasArg"),
                  ('n', "no-act", "Generate-Index-Diffs::Options::NoAct"),
                  ('v', "verbose", "Generate-Index-Diffs::Options::Verbose"),
                ]
    suites = apt_pkg.parse_commandline(Cnf, Arguments, sys.argv)
    Options = Cnf.subtree("Generate-Index-Diffs::Options")
    if "Help" in Options:
        usage()

    maxdiffs = Options.get("MaxDiffs::Default", "56")
    maxpackages = Options.get("MaxDiffs::Packages", maxdiffs)
    maxcontents = Options.get("MaxDiffs::Contents", maxdiffs)
    maxsources = Options.get("MaxDiffs::Sources", maxdiffs)

    if "PatchName" not in Options:
        format = "%Y-%m-%d-%H%M.%S"
        Options["PatchName"] = time.strftime(format)

    session = DBConn().session()

    if not suites:
        query = session.query(Suite.suite_name)
        if Options.get('Archive'):
            archives = utils.split_args(Options['Archive'])
            query = query.join(Suite.archive).filter(Archive.archive_name.in_(archives))
        suites = [s.suite_name for s in query]

    for suitename in suites:
        print("Processing: " + suitename)

        suiteobj = get_suite(suitename.lower(), session=session)

        # Use the canonical version of the suite name
        suite = suiteobj.suite_name

        if suiteobj.untouchable:
            print("Skipping: " + suite + " (untouchable)")
            continue

        skip_all = True
        if suiteobj.separate_contents_architecture_all or suiteobj.separate_packages_architecture_all:
            skip_all = False

        architectures = get_suite_architectures(suite, skipall=skip_all, session=session)
        components = [c.component_name for c in session.query(Component.component_name)]

        suite_suffix = utils.suite_suffix(suitename)
        if components and suite_suffix:
            longsuite = suite + "/" + suite_suffix
        else:
            longsuite = suite

        tree = os.path.join(suiteobj.archive.path, 'dists', longsuite)

        # See if there are Translations which might need a new pdiff
        cwd = os.getcwd()
        for component in components:
            #print "DEBUG: Working on %s" % (component)
            workpath = os.path.join(tree, component, "i18n")
            if os.path.isdir(workpath):
                os.chdir(workpath)
                for dirpath, dirnames, filenames in os.walk(".", followlinks=True, topdown=True):
                    for entry in filenames:
                        if not re_includeinpdiff.match(entry):
                            #print "EXCLUDING %s" % (entry)
                            continue
                        (fname, fext) = os.path.splitext(entry)
                        processfile = os.path.join(workpath, fname)
                        #print "Working: %s" % (processfile)
                        storename = "%s/%s_%s_%s" % (Options["TempDir"], suite, component, fname)
                        #print "Storefile: %s" % (storename)
                        genchanges(Options, processfile + ".diff", storename, processfile, maxdiffs)
        os.chdir(cwd)

        for archobj in architectures:
            architecture = archobj.arch_string

            if architecture == "source":
                longarch = architecture
                packages = "Sources"
                maxsuite = maxsources
            else:
                longarch = "binary-%s" % architecture
                packages = "Packages"
                maxsuite = maxpackages

            for component in components:
                # Process Contents
                file = "%s/%s/Contents-%s" % (tree, component, architecture)
                if "Verbose" in Options:
                    print(file)
                storename = "%s/%s_%s_contents_%s" % (Options["TempDir"], suite, component, architecture)
                genchanges(Options, file + ".diff", storename, file, maxcontents)

                file = "%s/%s/%s/%s" % (tree, component, longarch, packages)
                if "Verbose" in Options:
                    print(file)
                storename = "%s/%s_%s_%s" % (Options["TempDir"], suite, component, architecture)
                genchanges(Options, file + ".diff", storename, file, maxsuite)

################################################################################


if __name__ == '__main__':
    main()
