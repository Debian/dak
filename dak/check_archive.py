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
import stat
import sys
import time
import apt_pkg
import apt_inst

from daklib.dbconn import *
from daklib import utils
from daklib.config import Config
from daklib.dak_exceptions import InvalidDscError, ChangesUnicodeError, CantOpenError

################################################################################

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
  files-in-dsc       - ensure each .dsc references appropriate Files
  validate-indices   - ensure files mentioned in Packages & Sources exist
  files-not-symlinks - check files in the database aren't symlinks
  validate-builddeps - validate build-dependencies of .dsc files in the archive
  add-missing-source-checksums - add missing checksums for source packages
"""
    sys.exit(exit_code)

################################################################################

def process_dir (unused, dirname, filenames):
    """
    Process a directory and output every files name which is not listed already
    in the C{filenames} or global C{excluded} dictionaries.

    @type dirname: string
    @param dirname: the directory to look at

    @type filenames: dict
    @param filenames: Known filenames to ignore
    """
    global waste, db_files, excluded

    if dirname.find('/disks-') != -1 or dirname.find('upgrade-') != -1:
        return
    # hack; can't handle .changes files
    if dirname.find('proposed-updates') != -1:
        return
    for name in filenames:
        filename = os.path.abspath(os.path.join(dirname,name))
        if os.path.isfile(filename) and not os.path.islink(filename) and not db_files.has_key(filename) and not excluded.has_key(filename):
            waste += os.stat(filename)[stat.ST_SIZE]
            print "%s" % (filename)

################################################################################

def check_files():
    """
    Prepare the dictionary of existing filenames, then walk through the archive
    pool/ directory to compare it.
    """
    cnf = Config()
    session = DBConn().session()

    query = """
        SELECT archive.name, suite.suite_name, f.filename
          FROM binaries b
          JOIN bin_associations ba ON b.id = ba.bin
          JOIN suite ON ba.suite = suite.id
          JOIN archive ON suite.archive_id = archive.id
          JOIN files f ON b.file = f.id
         WHERE NOT EXISTS (SELECT 1 FROM files_archive_map af
                            WHERE af.archive_id = suite.archive_id
                              AND af.file_id = b.file)
         ORDER BY archive.name, suite.suite_name, f.filename
        """
    for row in session.execute(query):
        print "MISSING-ARCHIVE-FILE {0} {1} {2}".vformat(row)

    query = """
        SELECT archive.name, suite.suite_name, f.filename
          FROM source s
          JOIN src_associations sa ON s.id = sa.source
          JOIN suite ON sa.suite = suite.id
          JOIN archive ON suite.archive_id = archive.id
          JOIN dsc_files df ON s.id = df.source
          JOIN files f ON df.file = f.id
         WHERE NOT EXISTS (SELECT 1 FROM files_archive_map af
                            WHERE af.archive_id = suite.archive_id
                              AND af.file_id = df.file)
         ORDER BY archive.name, suite.suite_name, f.filename
        """
    for row in session.execute(query):
        print "MISSING-ARCHIVE-FILE {0} {1} {2}".vformat(row)

    archive_files = session.query(ArchiveFile) \
        .join(ArchiveFile.archive).join(ArchiveFile.file) \
        .order_by(Archive.archive_name, PoolFile.filename)

    expected_files = set()
    for af in archive_files:
        path = af.path
        expected_files.add(af.path)
        if not os.path.exists(path):
            print "MISSING-FILE {0} {1} {2}".format(af.archive.archive_name, af.file.filename, path)

    archives = session.query(Archive).order_by(Archive.archive_name)

    for a in archives:
        top = os.path.join(a.path, 'pool')
        for dirpath, dirnames, filenames in os.walk(top):
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                if path in expected_files:
                    continue
                print "UNEXPECTED-FILE {0} {1}".format(a.archive_name, path)

################################################################################

def check_dscs():
    """
    Parse every .dsc file in the archive and check for it's validity.
    """

    count = 0

    for src in DBConn().session().query(DBSource).order_by(DBSource.source, DBSource.version):
        f = src.poolfile.fullpath
        try:
            utils.parse_changes(f, signing_rules=1, dsc_file=1)
        except InvalidDscError:
            utils.warn("syntax error in .dsc file %s" % f)
            count += 1
        except ChangesUnicodeError:
            utils.warn("found invalid dsc file (%s), not properly utf-8 encoded" % f)
            count += 1
        except CantOpenError:
            utils.warn("missing dsc file (%s)" % f)
            count += 1
        except Exception as e:
            utils.warn("miscellaneous error parsing dsc file (%s): %s" % (f, str(e)))
            count += 1

    if count:
        utils.warn("Found %s invalid .dsc files." % (count))

################################################################################

def check_override():
    """
    Check for missing overrides in stable and unstable.
    """
    session = DBConn().session()

    for suite_name in [ "stable", "unstable" ]:
        print suite_name
        print "-" * len(suite_name)
        print
        suite = get_suite(suite_name)
        q = session.execute("""
SELECT DISTINCT b.package FROM binaries b, bin_associations ba
 WHERE b.id = ba.bin AND ba.suite = :suiteid AND NOT EXISTS
       (SELECT 1 FROM override o WHERE o.suite = :suiteid AND o.package = b.package)"""
                          % {'suiteid': suite.suite_id})

        for j in q.fetchall():
            print j[0]

        q = session.execute("""
SELECT DISTINCT s.source FROM source s, src_associations sa
  WHERE s.id = sa.source AND sa.suite = :suiteid AND NOT EXISTS
       (SELECT 1 FROM override o WHERE o.suite = :suiteid and o.package = s.source)"""
                          % {'suiteid': suite.suite_id})
        for j in q.fetchall():
            print j[0]

################################################################################


def check_source_in_one_dir():
    """
    Ensure that the source files for any given package is all in one
    directory so that 'apt-get source' works...
    """

    # Not the most enterprising method, but hey...
    broken_count = 0

    session = DBConn().session()

    q = session.query(DBSource)
    for s in q.all():
        first_path = ""
        first_filename = ""
        broken = False

        qf = session.query(PoolFile).join(Location).join(DSCFile).filter_by(source_id=s.source_id)
        for f in qf.all():
            # 0: path
            # 1: filename
            filename = os.path.join(f.location.path, f.filename)
            path = os.path.dirname(filename)

            if first_path == "":
                first_path = path
                first_filename = filename
            elif first_path != path:
                symlink = path + '/' + os.path.basename(first_filename)
                if not os.path.exists(symlink):
                    broken = True
                    print "WOAH, we got a live one here... %s [%s] {%s}" % (filename, s.source_id, symlink)
        if broken:
            broken_count += 1

    print "Found %d source packages where the source is not all in one directory." % (broken_count)

################################################################################
def check_checksums():
    """
    Validate all files
    """
    print "Getting file information from database..."
    q = DBConn().session().query(PoolFile)

    print "Checking file checksums & sizes..."
    for f in q:
        filename = f.fullpath

        try:
            fi = utils.open_file(filename)
        except:
            utils.warn("can't open '%s'." % (filename))
            continue

        size = os.stat(filename)[stat.ST_SIZE]
        if size != f.filesize:
            utils.warn("**WARNING** size mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, size, f.filesize))

        md5sum = apt_pkg.md5sum(fi)
        if md5sum != f.md5sum:
            utils.warn("**WARNING** md5sum mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, md5sum, f.md5sum))

        fi.seek(0)
        sha1sum = apt_pkg.sha1sum(fi)
        if sha1sum != f.sha1sum:
            utils.warn("**WARNING** sha1sum mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, sha1sum, f.sha1sum))

        fi.seek(0)
        sha256sum = apt_pkg.sha256sum(fi)
        if sha256sum != f.sha256sum:
            utils.warn("**WARNING** sha256sum mismatch for '%s' ('%s' [current] vs. '%s' [db])." % (filename, sha256sum, f.sha256sum))

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

    q = DBConn().session().query(PoolFile).filter(PoolFile.filename.like('.deb$'))

    db_files.clear()
    count = 0

    for pf in q.all():
        filename = os.path.abspath(os.path.join(pf.location.path, pf.filename))
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

def check_files_in_dsc():
    """
    Ensure each .dsc lists appropriate files in its Files field (according
    to the format announced in its Format field).
    """
    count = 0

    print "Building list of database files..."
    q = DBConn().session().query(PoolFile).filter(PoolFile.filename.like('.dsc$'))

    if q.count() > 0:
        print "Checking %d files..." % len(ql)
    else:
        print "No files to check."

    for pf in q.all():
        filename = os.path.abspath(os.path.join(pf.location.path + pf.filename))

        try:
            # NB: don't enforce .dsc syntax
            dsc = utils.parse_changes(filename, dsc_file=1)
        except:
            utils.fubar("error parsing .dsc file '%s'." % (filename))

        reasons = utils.check_dsc_files(filename, dsc)
        for r in reasons:
            utils.warn(r)

        if len(reasons) > 0:
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
    # apt_pkg.TagFile needs a real file handle and can't handle a GzipFile instance...
    (fd, temp_filename) = utils.temp_filename()
    (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
    if (result != 0):
        sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
        sys.exit(result)
    sources = utils.open_file(temp_filename)
    Sources = apt_pkg.TagFile(sources)
    while Sources.step():
        source = Sources.section.find('Package')
        directory = Sources.section.find('Directory')
        files = Sources.section.find('Files')
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
    # apt_pkg.TagFile needs a real file handle and can't handle a GzipFile instance...
    (fd, temp_filename) = utils.temp_filename()
    (result, output) = commands.getstatusoutput("gunzip -c %s > %s" % (filename, temp_filename))
    if (result != 0):
        sys.stderr.write("Gunzip invocation failed!\n%s\n" % (output))
        sys.exit(result)
    packages = utils.open_file(temp_filename)
    Packages = apt_pkg.TagFile(packages)
    while Packages.step():
        filename = "%s/%s" % (Cnf["Dir::Root"], Packages.section.find('Filename'))
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
        for component in get_component_names():
            architectures = get_suite_architectures(suite)
            for arch in [ i.arch_string.lower() for i in architectures ]:
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
    q = DBConn().session().query(PoolFile).filter(PoolFile.filename.like('.dsc$'))

    for pf in q.all():
        filename = os.path.abspath(os.path.join(pf.location.path, pf.filename))
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
        dsc = utils.parse_changes(filename, dsc_file=1)
        for field_name in [ "build-depends", "build-depends-indep" ]:
            field = dsc.get(field_name)
            if field:
                try:
                    apt_pkg.parse_src_depends(field)
                except:
                    print "E: [%s] %s: %s" % (filename, field_name, field)
                    pass

################################################################################

def check_build_depends():
    """ Validate build-dependencies of .dsc files in the archive """
    cnf = Config()
    os.path.walk(cnf["Dir::Root"], chk_bd_process_dir, None)

################################################################################

_add_missing_source_checksums_query = R"""
INSERT INTO source_metadata
  (src_id, key_id, value)
SELECT
  s.id,
  :checksum_key,
  E'\n' ||
    (SELECT STRING_AGG(' ' || tmp.checksum || ' ' || tmp.size || ' ' || tmp.basename, E'\n' ORDER BY tmp.basename)
     FROM
       (SELECT
            CASE :checksum_type
              WHEN 'Files' THEN f.md5sum
              WHEN 'Checksums-Sha1' THEN f.sha1sum
              WHEN 'Checksums-Sha256' THEN f.sha256sum
            END AS checksum,
            f.size,
            SUBSTRING(f.filename FROM E'/([^/]*)\\Z') AS basename
          FROM files f JOIN dsc_files ON f.id = dsc_files.file
          WHERE dsc_files.source = s.id AND f.id != s.file
       ) AS tmp
    )

  FROM
    source s
  WHERE NOT EXISTS (SELECT 1 FROM source_metadata md WHERE md.src_id=s.id AND md.key_id = :checksum_key);
"""

def add_missing_source_checksums():
    """ Add missing source checksums to source_metadata """
    session = DBConn().session()
    for checksum in ['Files', 'Checksums-Sha1', 'Checksums-Sha256']:
        checksum_key = get_or_set_metadatakey(checksum, session).key_id
        rows = session.execute(_add_missing_source_checksums_query,
            {'checksum_key': checksum_key, 'checksum_type': checksum}).rowcount
        if rows > 0:
            print "Added {0} missing entries for {1}".format(rows, checksum)
    session.commit()

################################################################################

def main ():
    global db_files, waste, excluded

    cnf = Config()

    Arguments = [('h',"help","Check-Archive::Options::Help")]
    for i in [ "help" ]:
        if not cnf.has_key("Check-Archive::Options::%s" % (i)):
            cnf["Check-Archive::Options::%s" % (i)] = ""

    args = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)

    Options = cnf.subtree("Check-Archive::Options")
    if Options["Help"]:
        usage()

    if len(args) < 1:
        utils.warn("dak check-archive requires at least one argument")
        usage(1)
    elif len(args) > 1:
        utils.warn("dak check-archive accepts only one argument")
        usage(1)
    mode = args[0].lower()

    # Initialize DB
    DBConn()

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
    elif mode == "files-in-dsc":
        check_files_in_dsc()
    elif mode == "validate-indices":
        check_indices_files_exist()
    elif mode == "files-not-symlinks":
        check_files_not_symlinks()
    elif mode == "validate-builddeps":
        check_build_depends()
    elif mode == "add-missing-source-checksums":
        add_missing_source_checksums()
    else:
        utils.warn("unknown mode '%s'" % (mode))
        usage(1)

################################################################################

if __name__ == '__main__':
    main()
