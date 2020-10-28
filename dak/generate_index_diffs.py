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
import tempfile
import time
import apt_pkg

import daklib.daksubprocess

from daklib import utils
from daklib.dbconn import Archive, Component, DBConn, Suite, get_suite, get_suite_architectures
#from daklib.regexes import re_includeinpdiff
import re
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
        return daklib.daksubprocess.check_call(
            cmd,
            stdin=open(inpath, "rb"),
            stdout=open(outpath, "wb"),
        )

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


def smartopen(file):
    def call_decompressor(cmd, inpath):
        fh = tempfile.TemporaryFile("w+t")
        daklib.daksubprocess.check_call(
            cmd,
            stdin=open(inpath, "rb"),
            stdout=fh,
        )
        fh.seek(0)
        return fh

    if os.path.isfile(file):
        return open(file, "r")
    elif os.path.isfile("%s.gz" % file):
        return call_decompressor(['zcat'], '{}.gz'.format(file))
    elif os.path.isfile("%s.bz2" % file):
        return call_decompressor(['bzcat'], '{}.bz2'.format(file))
    elif os.path.isfile("%s.xz" % file):
        return call_decompressor(['xzcat'], '{}.xz'.format(file))
    else:
        return None


class Updates:
    def __init__(self, readpath=None, max=56):
        self.can_path = None
        self.history = {}
        self.history_order = []
        self.max = max
        self.readpath = readpath
        self.filesizehashes = None

        if readpath:
            try:
                f = open(readpath + "/Index")
                x = f.readline()

                def read_hashs(ind, hashind, f, self, x=x):
                    while True:
                        x = f.readline()
                        if not x or x[0] != " ":
                            break
                        l = x.split()
                        fname = l[2]
                        if fname.endswith('.gz'):
                            fname = fname[:-3]
                        if fname not in self.history:
                            self.history[fname] = [None, None, None]
                            self.history_order.append(fname)
                        if not self.history[fname][ind]:
                            self.history[fname][ind] = (int(l[1]), None, None)
                        if hashind == 1:
                            self.history[fname][ind] = (int(self.history[fname][ind][0]), l[0], self.history[fname][ind][2])
                        else:
                            self.history[fname][ind] = (int(self.history[fname][ind][0]), self.history[fname][ind][1], l[0])
                    return x

                while x:
                    l = x.split()

                    if len(l) == 0:
                        x = f.readline()
                        continue

                    if l[0] == "SHA1-History:":
                        x = read_hashs(0, 1, f, self)
                        continue

                    if l[0] == "SHA256-History:":
                        x = read_hashs(0, 2, f, self)
                        continue

                    if l[0] == "SHA1-Patches:":
                        x = read_hashs(1, 1, f, self)
                        continue

                    if l[0] == "SHA256-Patches:":
                        x = read_hashs(1, 2, f, self)
                        continue

                    if l[0] == "SHA1-Download:":
                        x = read_hashs(2, 1, f, self)
                        continue

                    if l[0] == "SHA256-Download:":
                        x = read_hashs(2, 2, f, self)
                        continue

                    if l[0] == "Canonical-Name:" or l[0] == "Canonical-Path:":
                        self.can_path = l[1]

                    if l[0] == "SHA1-Current:" and len(l) == 3:
                        if not self.filesizehashes:
                            self.filesizehashes = (int(l[2]), None, None)
                        self.filesizehashes = (int(self.filesizehashes[0]), l[1], self.filesizehashes[2])

                    if l[0] == "SHA256-Current:" and len(l) == 3:
                        if not self.filesizehashes:
                            self.filesizehashes = (int(l[2]), None, None)
                        self.filesizehashes = (int(self.filesizehashes[0]), self.filesizehashes[2], l[1])

                    x = f.readline()

            except IOError:
                0

    def dump(self, out=sys.stdout):
        if self.can_path:
            out.write("Canonical-Path: %s\n" % (self.can_path))

        if self.filesizehashes:
            if self.filesizehashes[1]:
                out.write("SHA1-Current: %s %7d\n" % (self.filesizehashes[1], self.filesizehashes[0]))
            if self.filesizehashes[2]:
                out.write("SHA256-Current: %s %7d\n" % (self.filesizehashes[2], self.filesizehashes[0]))

        hs = self.history
        l = self.history_order[:]

        cnt = len(l)
        if cnt > self.max:
            for h in l[:cnt - self.max]:
                tryunlink("%s/%s.gz" % (self.readpath, h))
                del hs[h]
            l = l[cnt - self.max:]
            self.history_order = l[:]

        out.write("SHA1-History:\n")
        for h in l:
            if hs[h][0] and hs[h][0][1]:
                out.write(" %s %7d %s\n" % (hs[h][0][1], hs[h][0][0], h))
        out.write("SHA256-History:\n")
        for h in l:
            if hs[h][0] and hs[h][0][2]:
                out.write(" %s %7d %s\n" % (hs[h][0][2], hs[h][0][0], h))
        out.write("SHA1-Patches:\n")
        for h in l:
            if hs[h][1] and hs[h][1][1]:
                out.write(" %s %7d %s\n" % (hs[h][1][1], hs[h][1][0], h))
        out.write("SHA256-Patches:\n")
        for h in l:
            if hs[h][1] and hs[h][1][2]:
                out.write(" %s %7d %s\n" % (hs[h][1][2], hs[h][1][0], h))
        out.write("SHA1-Download:\n")
        for h in l:
            if hs[h][2] and hs[h][2][1]:
                out.write(" %s %7d %s.gz\n" % (hs[h][2][1], hs[h][2][0], h))
        out.write("SHA256-Download:\n")
        for h in l:
            if hs[h][2] and hs[h][2][2]:
                out.write(" %s %7d %s.gz\n" % (hs[h][2][2], hs[h][2][0], h))


def sizehashes(f):
    size = os.fstat(f.fileno())[6]
    f.seek(0)
    sha1sum = apt_pkg.sha1sum(f)
    f.seek(0)
    sha256sum = apt_pkg.sha256sum(f)
    return (size, sha1sum, sha256sum)


def genchanges(Options, outdir, oldfile, origfile, maxdiffs=56):
    if "NoAct" in Options:
        print("Not acting on: od: %s, oldf: %s, origf: %s, md: %s" % (outdir, oldfile, origfile, maxdiffs))
        return

    patchname = Options["PatchName"]

    # origfile = /path/to/Packages
    # oldfile  = ./Packages
    # newfile  = ./Packages.tmp
    # difffile = outdir/patchname
    # index   => outdir/Index

    # (outdir, oldfile, origfile) = argv

    newfile = oldfile + ".new"
    difffile = "%s/%s" % (outdir, patchname)

    upd = Updates(outdir, int(maxdiffs))
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
        #print "%s: hardlink unbroken, assuming unchanged" % (origfile)
        return

    oldf = smartopen(oldfile)
    oldsizehashes = sizehashes(oldf)

    # should probably early exit if either of these checks fail
    # alternatively (optionally?) could just trim the patch history

    #if upd.filesizesha1:
    #    if upd.filesizesha1 != oldsizesha1:
    #        print "info: old file " + oldfile + " changed! %s %s => %s %s" % (upd.filesizesha1 + oldsizesha1)

    if "CanonicalPath" in Options:
        upd.can_path = Options["CanonicalPath"]

    if os.path.exists(newfile):
        os.unlink(newfile)
    smartlink(origfile, newfile)
    newf = open(newfile, "r")
    newsizehashes = sizehashes(newf)
    newf.close()

    if newsizehashes == oldsizehashes:
        os.unlink(newfile)
        oldf.close()
        #print "%s: unchanged" % (origfile)
    else:
        if not os.path.isdir(outdir):
            os.mkdir(outdir)

        oldf.seek(0)
        with open("{}.gz".format(difffile), "wb") as fh:
            daklib.daksubprocess.check_call(
                "diff --ed - {} | gzip --rsyncable  --no-name -c -9".format(newfile), shell=True,
                stdin=oldf, stdout=fh
            )
        oldf.close()

        difff = smartopen(difffile)
        difsizehashes = sizehashes(difff)
        difff.close()

        difffgz = open(difffile + ".gz", "r")
        difgzsizehashes = sizehashes(difffgz)
        difffgz.close()

        upd.history[patchname] = (oldsizehashes, difsizehashes, difgzsizehashes)
        upd.history_order.append(patchname)

        upd.filesizehashes = newsizehashes

        os.unlink(oldfile + oldext)
        os.link(origfile + origext, oldfile + origext)
        os.unlink(newfile)

        with open(outdir + "/Index.new", "w") as f:
            upd.dump(f)
        os.rename(outdir + "/Index.new", outdir + "/Index")


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

            for component in components:
                if architecture == "source":
                    longarch = architecture
                    packages = "Sources"
                    maxsuite = maxsources
                else:
                    longarch = "binary-%s" % (architecture)
                    packages = "Packages"
                    maxsuite = maxpackages

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
