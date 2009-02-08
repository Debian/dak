#!/usr/bin/env python

""" Various different sanity checks

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: (C) 2000, 2001, 2002, 2003, 2004, 2006  James Troup <james@nocrew.org>
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

################################################################################

#   And, lo, a great and menacing voice rose from the depths, and with
#   great wrath and vehemence it's voice boomed across the
#   land... ``hehehehehehe... that *tickles*''
#                                                       -- aj on IRC

################################################################################

import commands
import os
import pg
import stat
import sys
import time
import apt_pkg
import apt_inst
from daklib import database
from daklib import utils
from daklib.regexes import re_issource

################################################################################

Cnf = None                     #: Configuration, apt_pkg.Configuration
projectB = None                #: database connection, pgobject
db_files = {}                  #: Cache of filenames as known by the database
waste = 0.0                    #: How many bytes are "wasted" by files not referenced in database
excluded = {}                  #: List of files which are excluded from files check
current_file = None
future_files = {}
current_time = time.time()     #: now()

################################################################################

def usage(exit_code=0):
    print """Usage: dak check-archive MODE
Run various sanity checks of the archive and/or database.

  -h, --help                show this help and exit.

The following MODEs are available:

  checksums          - validate the checksums stored in the database
  files              - check files in the database against what's in the archive
  dsc-syntax         - validate the syntax of .dsc files in the archive
  missing-overrides  - check for missing overrides
  source-in-one-dir  - ensure the source for each package is in one directory
  timestamps         - check for future timestamps in .deb's
  tar-gz-in-dsc      - ensure each .dsc lists a .tar.gz file
  validate-indices   - ensure files mentioned in Packages & Sources exist
  files-not-symlinks - check files in the database aren't symlinks
  validate-builddeps - validate build-dependencies of .dsc files in the archive
"""
    sys.exit(exit_code)

################################################################################

def process_dir (unused, dirname, filenames):
    """
    Process a directory and output every files name which is not listed already
    in the C{filenames} or global C{excluded} dictionaries.

    @type dirname: string
    @param dirname: the directory to look at

    @type filename: dict
    @param filename: Known filenames to ignore
    """
    global waste, db_files, excluded

    if dirname.find('/disks-') != -1 or dirname.find('upgrade-') != -1:
        return
    # hack; can't handle .changes files
    if dirname.find('proposed-updates') != -1:
        return
    for name in filenames:
        filename = os.path.abspath(dirname+'/'+name)
        filename = filename.replace('potato-proposed-updates', 'proposed-updates')
        if os.path.isfile(filename) and not os.path.islink(filename) and not db_files.has_key(filename) and not excluded.has_key(filename):
            waste += os.stat(filename)[stat.ST_SIZE]
            print "%s" % (filename)

################################################################################

def check_files():
    """
    Prepare the dictionary of existing filenames, then walk through the archive
    pool/ directory to compare it.
    """
    global db_files

    print "Building list of database files..."
    q = projectB.query("SELECT l.path, f.filename, f.last_used FROM files f, location l WHERE f.location = l.id ORDER BY l.path, f.filename")
    ql = q.getresult()

    print "Missing files:"
    db_files.clear()
    for i in ql:
        filename = os.path.abspath(i[0] + i[1])
        db_files[filename] = ""
        if os.access(filename, os.R_OK) == 0:
            if i[2]:
                print "(last used: %s) %s" % (i[2], filename)
            else:
                print "%s" % (filename)


    filename = Cnf["Dir::Override"]+'override.unreferenced'
    if os.path.exists(filename):
        f = utils.open_file(filename)
        for filename in f.readlines():
            filename = filename[:-1]
            excluded[filename] = ""

    print "Existent files not in db:"

    os.path.walk(Cnf["Dir::Root"]+'pool/', process_dir, None)

    print
    print "%s wasted..." % (utils.size_type(waste))

################################################################################

def check_dscs():
    """
    Parse every .dsc file in the archive and check for it's validity.
    """
    count = 0
    suite = 'unstable'
    for component in Cnf.SubTree("Component").List():
        if component == "mixed":
            continue
        component = component.lower()
        list_filename = '%s%s_%s_source.list' % (Cnf["Dir::Lists"], suite, component)
        list_file = utils.open_file(list_filename)
        for line in list_file.readlines():
            f = line[:-1]
            try:
                utils.parse_changes(f, signing_rules=1)
            except InvalidDscError, line:
                utils.warn("syntax error in .dsc file '%s', line %s." % (f, line))
                count += 1

    if count:
        utils.warn("Found %s invalid .dsc files." % (count))

################################################################################

def check_override():
    """
    Check for missing overrides in stable and unstable.
    """
    for suite in [ "stable", "unstable" ]:
        print suite
        print "-"*len(suite)
        print
        suite_id = database.get_suite_id(suite)
        q = projectB.query("""
SELECT DISTINCT b.package FROM binaries b, bin_associations ba
 WHERE b.id = ba.bin AND ba.suite = %s AND NOT EXISTS
       (SELECT 1 FROM override o WHERE o.suite = %s AND o.package = b.package)"""
                           % (suite_id, suite_id))
        print q
        q = projectB.query("""
SELECT DISTINCT s.source FROM source s, src_associations sa
  WHERE s.id = sa.source AND sa.suite = %s AND NOT EXISTS
       (SELECT 1 FROM override o WHERE o.suite = %s and o.package = s.source)"""
                           % (suite_id, suite_id))
        print q

################################################################################


def check_source_in_one_dir():
    """
    Ensure that the source files for any given package is all in one
    directory so that 'apt-get source' works...
    """

    # Not the most enterprising method, but hey...
    broken_count = 0
    q = projectB.query("SELECT id FROM source;")
    for i in q.getresult():
        source_id = i[0]
        q2 = projectB.query("""
SELECT l.path, f.filename FROM files f, dsc_files df, location l WHERE df.source = %s AND f.id = df.file AND l.id = f.location"""
                            % (source_id))
        first_path = ""
        first_filename = ""
        broken = 0
        for j in q2.getresult():
            filename = j[0] + j[1]
            path = os.path.dirname(filename)
            if first_path == "":
                first_path = path
                first_filename = filename
            elif first_path != path:
                symlink = path + '/' + os.path.basename(first_filename)
                if not os.path.exists(symlink):
                    broken = 1
                    print "WOAH, we got a live one here... %s [%s] {%s}" % (filename, source_id, symlink)
        if broken:
            broken_count += 1
    print "Found %d source packages where the source is not all in one directory." % (broken_count)

################################################################################

def check_checksums():
    """
    Validate all files
    """
    print "Getting file information from database..."
    q = projectB.query("SELECT l.path, f.filename, f.md5sum, f.sha1sum, f.sha256sum, f.size FROM files f, location l WHERE f.location = l.id")
    ql = q.getresult()

    print "Checking file checksums & sizes..."
    for i in ql:
        filename = os.path.abspath(i[0] + i[1])
        db_md5sum = i[2]
        db_sha1sum = i[3]
        db_sha256sum = i[4]
        db_size = int(i[5])
        try:
            f = utils.open_file(filename)
        except:
            utils.warn("can't open '%s'." % (filename))
            continue
        md5sum = apt_pkg.md5sum(f)
        size = os.stat(filename)[stat.ST_SIZE]
        if md5sum != db_md5sum:
            utils.warn("**WARNING** md5sum mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, md5sum, db_md5sum))
        if size != db_size:
            utils.warn("**WARNING** size mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, size, db_size))
        f.seek(0)
        sha1sum = apt_pkg.sha1sum(f)
        if sha1sum != db_sha1sum:
            utils.warn("**WARNING** sha1sum mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, sha1sum, db_sha1sum))

        f.seek(0)
        sha256sum = apt_pkg.sha256sum(f)
        if sha256sum != db_sha256sum:
            utils.warn("**WARNING** sha256sum mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, sha256sum, db_sha256sum))

    print "Done."

################################################################################
#

def Ent(Kind,Name,Link,Mode,UID,GID,Size,MTime,Major,Minor):
    global future_files

    if MTime > current_time:
        future_files[current_file] = MTime
        print "%s: %s '%s','%s',%u,%u,%u,%u,%u,%u,%u" % (current_file, Kind,Name,Link,Mode,UID,GID,Size, MTime, Major, Minor)

def check_timestamps():
    """
    Check all files for timestamps in the future; common from hardware
    (e.g. alpha) which have far-future dates as their default dates.
    """

    global current_file

    q = projectB.query("SELECT l.path, f.filename FROM files f, location l WHERE f.location = l.id AND f.filename ~ '.deb$'")
    ql = q.getresult()
    db_files.clear()
    count = 0
    for i in ql:
        filename = os.path.abspath(i[0] + i[1])
        if os.access(filename, os.R_OK):
            f = utils.open_file(filename)
            current_file = filename
            sys.stderr.write("Processing %s.\n" % (filename))
            apt_inst.debExtract(f, Ent, "control.tar.gz")
            f.seek(0)
            apt_inst.debExtract(f, Ent, "data.tar.gz")
            count += 1
    print "Checked %d files (out of %d)." % (count, len(db_files.keys()))

################################################################################

def check_missing_tar_gz_in_dsc():
    """
    Ensure each .dsc lists a .tar.gz file
    """
    count = 0

    print "Building list of database files..."
    q = projectB.query("SELECT l.path, f.filename FROM files f, location l WHERE f.location = l.id AND f.filename ~ '.dsc$'")
    ql = q.getresult()
    if ql:
        print "Checking %d files..." % len(ql)
    else:
        print "No files to check."
    for i in ql:
        filename = os.path.abspath(i[0] + i[1])
        try:
            # NB: don't enforce .dsc syntax
            dsc = utils.parse_changes(filename)
        except:
            utils.fubar("error parsing .dsc file '%s'." % (filename))
        dsc_files = utils.build_file_list(dsc, is_a_dsc=1)
        has_tar = 0
        for f in dsc_files.keys():
            m = re_issource.match(f)
            if not m:
                utils.fubar("%s not recognised as source." % (f))
            ftype = m.group(3)
            if ftype == "orig.tar.gz" or ftype == "tar.gz":
                has_tar = 1
        if not has_tar:
            utils.warn("%s has no .tar.gz in the .dsc file." % (f))
            count += 1

    if count:
        utils.warn("Found %s invalid .dsc files." % (count))


################################################################################

def validate_sources(suite, component):
    """
    Ensure files mentioned in Sources exist
    """
    filename = "%s/dists/%s/%s/source/Sources.gz" % (Cnf["Dir::Root"], suite, component)
    print "Processing %s..." % (filename)
    # apt_pkg.ParseTagFile needs a real file handle and can't handle a GzipFile instance...
    (fd, temp_filename) = utils.temp_filename()
    (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
    if (result != 0):
        sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
        sys.exit(result)
    sources = utils.open_file(temp_filename)
    Sources = apt_pkg.ParseTagFile(sources)
    while Sources.Step():
        source = Sources.Section.Find('Package')
        directory = Sources.Section.Find('Directory')
        files = Sources.Section.Find('Files')
        for i in files.split('\n'):
            (md5, size, name) = i.split()
            filename = "%s/%s/%s" % (Cnf["Dir::Root"], directory, name)
            if not os.path.exists(filename):
                if directory.find("potato") == -1:
                    print "W: %s missing." % (filename)
                else:
                    pool_location = utils.poolify (source, component)
                    pool_filename = "%s/%s/%s" % (Cnf["Dir::Pool"], pool_location, name)
                    if not os.path.exists(pool_filename):
                        print "E: %s missing (%s)." % (filename, pool_filename)
                    else:
                        # Create symlink
                        pool_filename = os.path.normpath(pool_filename)
                        filename = os.path.normpath(filename)
                        src = utils.clean_symlink(pool_filename, filename, Cnf["Dir::Root"])
                        print "Symlinking: %s -> %s" % (filename, src)
                        #os.symlink(src, filename)
    sources.close()
    os.unlink(temp_filename)

########################################

def validate_packages(suite, component, architecture):
    """
    Ensure files mentioned in Packages exist
    """
    filename = "%s/dists/%s/%s/binary-%s/Packages.gz" \
               % (Cnf["Dir::Root"], suite, component, architecture)
    print "Processing %s..." % (filename)
    # apt_pkg.ParseTagFile needs a real file handle and can't handle a GzipFile instance...
    (fd, temp_filename) = utils.temp_filename()
    (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
    if (result != 0):
        sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
        sys.exit(result)
    packages = utils.open_file(temp_filename)
    Packages = apt_pkg.ParseTagFile(packages)
    while Packages.Step():
        filename = "%s/%s" % (Cnf["Dir::Root"], Packages.Section.Find('Filename'))
        if not os.path.exists(filename):
            print "W: %s missing." % (filename)
    packages.close()
    os.unlink(temp_filename)

########################################

def check_indices_files_exist():
    """
    Ensure files mentioned in Packages & Sources exist
    """
    for suite in [ "stable", "testing", "unstable" ]:
        for component in Cnf.ValueList("Suite::%s::Components" % (suite)):
            architectures = Cnf.ValueList("Suite::%s::Architectures" % (suite))
            for arch in [ i.lower() for i in architectures ]:
                if arch == "source":
                    validate_sources(suite, component)
                elif arch == "all":
                    continue
                else:
                    validate_packages(suite, component, arch)

################################################################################

def check_files_not_symlinks():
    """
    Check files in the database aren't symlinks
    """
    print "Building list of database files... ",
    before = time.time()
    q = projectB.query("SELECT l.path, f.filename, f.id FROM files f, location l WHERE f.location = l.id")
    print "done. (%d seconds)" % (int(time.time()-before))
    q_files = q.getresult()

    for i in q_files:
        filename = os.path.normpath(i[0] + i[1])
        if os.access(filename, os.R_OK) == 0:
            utils.warn("%s: doesn't exist." % (filename))
        else:
            if os.path.islink(filename):
                utils.warn("%s: is a symlink." % (filename))

################################################################################

def chk_bd_process_dir (unused, dirname, filenames):
    for name in filenames:
        if not name.endswith(".dsc"):
            continue
        filename = os.path.abspath(dirname+'/'+name)
        dsc = utils.parse_changes(filename)
        for field_name in [ "build-depends", "build-depends-indep" ]:
            field = dsc.get(field_name)
            if field:
                try:
                    apt_pkg.ParseSrcDepends(field)
                except:
                    print "E: [%s] %s: %s" % (filename, field_name, field)
                    pass

################################################################################

def check_build_depends():
    """ Validate build-dependencies of .dsc files in the archive """
    os.path.walk(Cnf["Dir::Root"], chk_bd_process_dir, None)

################################################################################

def main ():
    global Cnf, projectB, db_files, waste, excluded

    Cnf = utils.get_conf()
    Arguments = [('h',"help","Check-Archive::Options::Help")]
    for i in [ "help" ]:
        if not Cnf.has_key("Check-Archive::Options::%s" % (i)):
            Cnf["Check-Archive::Options::%s" % (i)] = ""

    args = apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Check-Archive::Options")
    if Options["Help"]:
        usage()

    if len(args) < 1:
        utils.warn("dak check-archive requires at least one argument")
        usage(1)
    elif len(args) > 1:
        utils.warn("dak check-archive accepts only one argument")
        usage(1)
    mode = args[0].lower()

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    database.init(Cnf, projectB)

    if mode == "checksums":
        check_checksums()
    elif mode == "files":
        check_files()
    elif mode == "dsc-syntax":
        check_dscs()
    elif mode == "missing-overrides":
        check_override()
    elif mode == "source-in-one-dir":
        check_source_in_one_dir()
    elif mode == "timestamps":
        check_timestamps()
    elif mode == "tar-gz-in-dsc":
        check_missing_tar_gz_in_dsc()
    elif mode == "validate-indices":
        check_indices_files_exist()
    elif mode == "files-not-symlinks":
        check_files_not_symlinks()
    elif mode == "validate-builddeps":
        check_build_depends()
    else:
        utils.warn("unknown mode '%s'" % (mode))
        usage(1)

################################################################################

if __name__ == '__main__':
    main()
