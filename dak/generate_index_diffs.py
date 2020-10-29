#! /usr/bin/env python3

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

import asyncio
import os
import re
import sys
import time
import traceback

import apt_pkg

from daklib import utils, pdiff
from daklib.dbconn import Archive, Component, DBConn, Suite, get_suite, get_suite_architectures
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


async def smartlink(f, t):
    async def call_decompressor(cmd, inpath, outpath):
        with open(inpath, "rb") as rfd, open(outpath, "wb") as wfd:
            await pdiff.asyncio_check_call(
                *cmd,
                stdin=rfd,
                stdout=wfd,
            )

    if os.path.isfile(f):
        os.link(f, t)
    elif os.path.isfile("%s.gz" % (f)):
        await call_decompressor(['gzip', '-d'], '{}.gz'.format(f), t)
    elif os.path.isfile("%s.bz2" % (f)):
        await call_decompressor(['bzip2', '-d'], '{}.bz2'.format(f), t)
    elif os.path.isfile("%s.xz" % (f)):
        await call_decompressor(['xz', '-d'], '{}.xz'.format(f), t)
    else:
        print("missing: %s" % (f))
        raise IOError(f)


async def genchanges(Options, outdir, oldfile, origfile, maxdiffs=56, merged_pdiffs=False):
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
    # orig file with the (new) compression extension in case it changed
    old_full_path = oldfile + origext
    resolved_orig_path = os.path.realpath(origfile + origext)

    if not oldstat:
        print("%s: initial run" % origfile)
        # The target file might have been copying over the symlink as an accident
        # in a previous run.
        if os.path.islink(old_full_path):
            os.unlink(old_full_path)
        os.link(resolved_orig_path, old_full_path)
        return

    if oldstat[1:3] == origstat[1:3]:
        return

    upd = PDiffIndex(outdir, int(maxdiffs), merged_pdiffs)

    if "CanonicalPath" in Options:
        upd.can_path = Options["CanonicalPath"]

    # generate_and_add_patch_file needs an uncompressed file
    # The `newfile` variable is our uncompressed copy of 'oldfile` thanks to
    # smartlink
    newfile = oldfile + ".new"
    if os.path.exists(newfile):
        os.unlink(newfile)

    await smartlink(origfile, newfile)

    try:
        await upd.generate_and_add_patch_file(oldfile, newfile, patchname)
    finally:
        os.unlink(newfile)

    upd.prune_patch_history()

    for obsolete_patch in upd.find_obsolete_patches():
        tryunlink(obsolete_patch)

    upd.update_index()

    if oldfile + oldext != old_full_path and os.path.islink(old_full_path):
        # The target file might have been copying over the symlink as an accident
        # in a previous run.
        os.unlink(old_full_path)

    os.unlink(oldfile + oldext)
    os.link(resolved_orig_path, old_full_path)


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

    # can only be set via config at the moment
    max_parallel = int(Options.get("MaxParallel", "8"))

    if "PatchName" not in Options:
        format = "%Y-%m-%d-%H%M.%S"
        Options["PatchName"] = time.strftime(format)

    session = DBConn().session()
    pending_tasks = []

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

        merged_pdiffs = suiteobj.merged_pdiffs

        tree = os.path.join(suiteobj.archive.path, 'dists', longsuite)

        # See if there are Translations which might need a new pdiff
        cwd = os.getcwd()
        for component in components:
            workpath = os.path.join(tree, component, "i18n")
            if os.path.isdir(workpath):
                os.chdir(workpath)
                for dirpath, dirnames, filenames in os.walk(".", followlinks=True, topdown=True):
                    for entry in filenames:
                        if not re_includeinpdiff.match(entry):
                            continue
                        (fname, fext) = os.path.splitext(entry)
                        processfile = os.path.join(workpath, fname)
                        storename = "%s/%s_%s_%s" % (Options["TempDir"], suite, component, fname)
                        coroutine = genchanges(Options, processfile + ".diff", storename, processfile, maxdiffs, merged_pdiffs)
                        pending_tasks.append(coroutine)
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

                storename = "%s/%s_%s_contents_%s" % (Options["TempDir"], suite, component, architecture)
                coroutine = genchanges(Options, file + ".diff", storename, file, maxcontents, merged_pdiffs)
                pending_tasks.append(coroutine)

                file = "%s/%s/%s/%s" % (tree, component, longarch, packages)
                storename = "%s/%s_%s_%s" % (Options["TempDir"], suite, component, architecture)
                coroutine = genchanges(Options, file + ".diff", storename, file, maxsuite, merged_pdiffs)
                pending_tasks.append(coroutine)

    asyncio.run(process_pdiff_tasks(pending_tasks, max_parallel))


async def process_pdiff_tasks(pending_coroutines, limit):
    if limit is not None:
        # If there is a limit, wrap the tasks with a semaphore to handle the limit
        semaphore = asyncio.Semaphore(limit)

        async def bounded_task(task):
            async with semaphore:
                return await task

        pending_coroutines = [bounded_task(task) for task in pending_coroutines]

    print(f"Processing {len(pending_coroutines)} PDiff generation tasks (parallel limit {limit})")
    start = time.time()
    pending_tasks = [asyncio.create_task(coroutine) for coroutine in pending_coroutines]
    done, pending = await asyncio.wait(pending_tasks)
    duration = round(time.time() - start, 2)

    errors = False

    for task in done:
        try:
            task.result()
        except Exception:
            traceback.print_exc()
            errors = True

    if errors:
        print(f"Processing failed after {duration} seconds")
        sys.exit(1)

    print(f"Processing finished {duration} seconds")

################################################################################


if __name__ == '__main__':
    main()
