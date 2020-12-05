#! /usr/bin/env python3

"""
Create all the Release files

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2011  Joerg Jaspert <joerg@debian.org>
@copyright: 2011  Mark Hymers <mhy@debian.org>
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

# <mhy> I wish they wouldnt leave biscuits out, thats just tempting. Damnit.

################################################################################

import sys
import os
import os.path
import time
import gzip
import bz2
import errno
import apt_pkg
import subprocess
from sqlalchemy.orm import object_session

import daklib.gpg
from daklib import utils, daklog
from daklib.regexes import re_gensubrelease, re_includeinrelease_byhash, re_includeinrelease_plain
from daklib.dbconn import *
from daklib.config import Config
from daklib.dakmultiprocessing import DakProcessPool, PROC_STATUS_SUCCESS

################################################################################
Logger = None                  #: Our logging object

################################################################################


def usage(exit_code=0):
    """ Usage information"""

    print("""Usage: dak generate-releases [OPTIONS]
Generate the Release files

  -a, --archive=ARCHIVE      process suites in ARCHIVE
  -s, --suite=SUITE(s)       process this suite
                             Default: All suites not marked 'untouchable'
  -f, --force                Allow processing of untouchable suites
                             CAREFUL: Only to be used at (point) release time!
  -h, --help                 show this help and exit
  -q, --quiet                Don't output progress

SUITE can be a space separated list, e.g.
   --suite=unstable testing
  """)
    sys.exit(exit_code)

########################################################################


def sign_release_dir(suite, dirname):
    cnf = Config()

    if 'Dinstall::SigningKeyring' in cnf or 'Dinstall::SigningHomedir' in cnf:
        args = {
            'keyids': suite.signingkeys or [],
            'pubring': cnf.get('Dinstall::SigningPubKeyring') or None,
            'secring': cnf.get('Dinstall::SigningKeyring') or None,
            'homedir': cnf.get('Dinstall::SigningHomedir') or None,
            'passphrase_file': cnf.get('Dinstall::SigningPassphraseFile') or None,
        }

        relname = os.path.join(dirname, 'Release')

        dest = os.path.join(dirname, 'Release.gpg')
        if os.path.exists(dest):
            os.unlink(dest)

        inlinedest = os.path.join(dirname, 'InRelease')
        if os.path.exists(inlinedest):
            os.unlink(inlinedest)

        with open(relname, 'r') as stdin:
            with open(dest, 'w') as stdout:
                daklib.gpg.sign(stdin, stdout, inline=False, **args)
            stdin.seek(0)
            with open(inlinedest, 'w') as stdout:
                daklib.gpg.sign(stdin, stdout, inline=True, **args)


class XzFile(object):
    def __init__(self, filename, mode='r'):
        self.filename = filename

    def read(self):
        with open(self.filename, 'rb') as stdin:
            return subprocess.check_output(['xz', '-d'], stdin=stdin)


class HashFunc(object):
    def __init__(self, release_field, func, db_name):
        self.release_field = release_field
        self.func = func
        self.db_name = db_name


RELEASE_HASHES = [
    HashFunc('MD5Sum', apt_pkg.md5sum, 'md5sum'),
    HashFunc('SHA1', apt_pkg.sha1sum, 'sha1'),
    HashFunc('SHA256', apt_pkg.sha256sum, 'sha256'),
]


class ReleaseWriter(object):
    def __init__(self, suite):
        self.suite = suite

    def suite_path(self):
        """
        Absolute path to the suite-specific files.
        """
        suite_suffix = utils.suite_suffix(self.suite.suite_name)

        return os.path.join(self.suite.archive.path, 'dists',
                            self.suite.suite_name, suite_suffix)

    def suite_release_path(self):
        """
        Absolute path where Release files are physically stored.
        This should be a path that sorts after the dists/ directory.
        """
        cnf = Config()
        suite_suffix = utils.suite_suffix(self.suite.suite_name)

        return os.path.join(self.suite.archive.path, 'zzz-dists',
                            self.suite.suite_name, suite_suffix)

    def create_release_symlinks(self):
        """
        Create symlinks for Release files.
        This creates the symlinks for Release files in the `suite_path`
        to the actual files in `suite_release_path`.
        """
        relpath = os.path.relpath(self.suite_release_path(), self.suite_path())
        for f in ("Release", "Release.gpg", "InRelease"):
            source = os.path.join(relpath, f)
            dest = os.path.join(self.suite_path(), f)
            if os.path.lexists(dest):
                if not os.path.islink(dest):
                    os.unlink(dest)
                elif os.readlink(dest) == source:
                    continue
                else:
                    os.unlink(dest)
            os.symlink(source, dest)

    def create_output_directories(self):
        for path in (self.suite_path(), self.suite_release_path()):
            try:
                os.makedirs(path)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

    def _update_hashfile_table(self, session, fileinfo, hashes):
        # Mark all by-hash files as obsolete.  We will undo that for the ones
        # we still reference later.
        query = """
            UPDATE hashfile SET unreferenced = CURRENT_TIMESTAMP
            WHERE suite_id = :id AND unreferenced IS NULL"""
        session.execute(query, {'id': self.suite.suite_id})

        query = "SELECT path FROM hashfile WHERE suite_id = :id"
        q = session.execute(query, {'id': self.suite.suite_id})
        known_hashfiles = set(row[0] for row in q)
        updated = set()
        new = set()

        # Update the hashfile table with new or updated files
        for filename in fileinfo:
            if not os.path.lexists(filename):
                # probably an uncompressed index we didn't generate
                continue
            byhashdir = os.path.join(os.path.dirname(filename), 'by-hash')
            for h in hashes:
                field = h.release_field
                hashfile = os.path.join(byhashdir, field, fileinfo[filename][field])
                if hashfile in known_hashfiles:
                    updated.add(hashfile)
                else:
                    new.add(hashfile)

        if updated:
            session.execute("""
                UPDATE hashfile SET unreferenced = NULL
                WHERE path = ANY(:p) AND suite_id = :id""",
                {'p': list(updated), 'id': self.suite.suite_id})
        if new:
            session.execute("""
                INSERT INTO hashfile (path, suite_id)
                VALUES (:p, :id)""",
                [{'p': hashfile, 'id': self.suite.suite_id} for hashfile in new])

        session.commit()

    def _make_byhash_links(self, fileinfo, hashes):
        # Create hardlinks in by-hash directories
        for filename in fileinfo:
            if not os.path.lexists(filename):
                # probably an uncompressed index we didn't generate
                continue

            for h in hashes:
                field = h.release_field
                hashfile = os.path.join(os.path.dirname(filename), 'by-hash', field, fileinfo[filename][field])
                try:
                    os.makedirs(os.path.dirname(hashfile))
                except OSError as exc:
                    if exc.errno != errno.EEXIST:
                        raise
                try:
                    os.link(filename, hashfile)
                except OSError as exc:
                    if exc.errno != errno.EEXIST:
                        raise

    def _make_byhash_base_symlink(self, fileinfo, hashes):
        # Create symlinks to files in by-hash directories
        for filename in fileinfo:
            if not os.path.lexists(filename):
                # probably an uncompressed index we didn't generate
                continue

            besthash = hashes[-1]
            field = besthash.release_field
            hashfilebase = os.path.join('by-hash', field, fileinfo[filename][field])
            hashfile = os.path.join(os.path.dirname(filename), hashfilebase)

            assert os.path.exists(hashfile), 'by-hash file {} is missing'.format(hashfile)

            os.unlink(filename)
            os.symlink(hashfilebase, filename)

    def generate_release_files(self):
        """
        Generate Release files for the given suite

        @type suite: string
        @param suite: Suite name
        """

        suite = self.suite
        session = object_session(suite)

        # Attribs contains a tuple of field names and the database names to use to
        # fill them in
        attribs = (('Origin',      'origin'),
                    ('Label',       'label'),
                    ('Suite',       'release_suite_output'),
                    ('Version',     'version'),
                    ('Codename',    'codename'),
                    ('Changelogs',  'changelog_url'),
                  )

        # A "Sub" Release file has slightly different fields
        subattribs = (('Archive',  'suite_name'),
                       ('Origin',   'origin'),
                       ('Label',    'label'),
                       ('Version',  'version'))

        # Boolean stuff. If we find it true in database, write out "yes" into the release file
        boolattrs = (('NotAutomatic',         'notautomatic'),
                      ('ButAutomaticUpgrades', 'butautomaticupgrades'),
                      ('Acquire-By-Hash',      'byhash'),
                    )

        cnf = Config()
        cnf_suite_suffix = cnf.get("Dinstall::SuiteSuffix", "").rstrip("/")

        suite_suffix = utils.suite_suffix(suite.suite_name)

        self.create_output_directories()
        self.create_release_symlinks()

        outfile = os.path.join(self.suite_release_path(), "Release")
        out = open(outfile + ".new", "w")

        for key, dbfield in attribs:
            # Hack to skip NULL Version fields as we used to do this
            # We should probably just always ignore anything which is None
            if key in ("Version", "Changelogs") and getattr(suite, dbfield) is None:
                continue

            out.write("%s: %s\n" % (key, getattr(suite, dbfield)))

        out.write("Date: %s\n" % (time.strftime("%a, %d %b %Y %H:%M:%S UTC", time.gmtime(time.time()))))

        if suite.validtime:
            validtime = float(suite.validtime)
            out.write("Valid-Until: %s\n" % (time.strftime("%a, %d %b %Y %H:%M:%S UTC", time.gmtime(time.time() + validtime))))

        for key, dbfield in boolattrs:
            if getattr(suite, dbfield, False):
                out.write("%s: yes\n" % (key))

        skip_arch_all = True
        if suite.separate_contents_architecture_all or suite.separate_packages_architecture_all:
            # According to the Repository format specification:
            #   https://wiki.debian.org/DebianRepository/Format#No-Support-for-Architecture-all
            #
            # Clients are not expected to support Packages-all without Contents-all.  At the
            # time of writing, it is not possible to set separate_packages_architecture_all.
            # However, we add this little assert to stop the bug early.
            #
            # If you are here because the assert failed, you probably want to see "update123.py"
            # and its advice on updating the CHECK constraint.
            assert suite.separate_contents_architecture_all
            skip_arch_all = False

            if not suite.separate_packages_architecture_all:
                out.write("No-Support-for-Architecture-all: Packages\n")

        architectures = get_suite_architectures(suite.suite_name, skipall=skip_arch_all, skipsrc=True, session=session)

        out.write("Architectures: %s\n" % (" ".join(a.arch_string for a in architectures)))

        components = [c.component_name for c in suite.components]

        out.write("Components: %s\n" % (" ".join(components)))

        # For exact compatibility with old g-r, write out Description here instead
        # of with the rest of the DB fields above
        if getattr(suite, 'description') is not None:
            out.write("Description: %s\n" % suite.description)

        for comp in components:
            for dirpath, dirnames, filenames in os.walk(os.path.join(self.suite_path(), comp), topdown=True):
                if not re_gensubrelease.match(dirpath):
                    continue

                subfile = os.path.join(dirpath, "Release")
                subrel = open(subfile + '.new', "w")

                for key, dbfield in subattribs:
                    if getattr(suite, dbfield) is not None:
                        subrel.write("%s: %s\n" % (key, getattr(suite, dbfield)))

                for key, dbfield in boolattrs:
                    if getattr(suite, dbfield, False):
                        subrel.write("%s: yes\n" % (key))

                subrel.write("Component: %s%s\n" % (suite_suffix, comp))

                # Urgh, but until we have all the suite/component/arch stuff in the DB,
                # this'll have to do
                arch = os.path.split(dirpath)[-1]
                if arch.startswith('binary-'):
                    arch = arch[7:]

                subrel.write("Architecture: %s\n" % (arch))
                subrel.close()

                os.rename(subfile + '.new', subfile)

        # Now that we have done the groundwork, we want to get off and add the files with
        # their checksums to the main Release file
        oldcwd = os.getcwd()

        os.chdir(self.suite_path())

        hashes = [x for x in RELEASE_HASHES if x.db_name in suite.checksums]

        fileinfo = {}
        fileinfo_byhash = {}

        uncompnotseen = {}

        for dirpath, dirnames, filenames in os.walk(".", followlinks=True, topdown=True):
            # SuiteSuffix deprecation:
            # components on security-master are updates/{main,contrib,non-free}, but
            # we want dists/${suite}/main.  Until we can rename the components,
            # we cheat by having an updates -> . symlink.  This should not be visited.
            if cnf_suite_suffix:
                path = os.path.join(dirpath, cnf_suite_suffix)
                try:
                    target = os.readlink(path)
                    if target == ".":
                        dirnames.remove(cnf_suite_suffix)
                except (OSError, ValueError):
                    pass
            for entry in filenames:
                if dirpath == '.' and entry in ["Release", "Release.gpg", "InRelease"]:
                    continue

                filename = os.path.join(dirpath.lstrip('./'), entry)

                if re_includeinrelease_byhash.match(entry):
                    fileinfo[filename] = fileinfo_byhash[filename] = {}
                elif re_includeinrelease_plain.match(entry):
                    fileinfo[filename] = {}
                # Skip things we don't want to include
                else:
                    continue

                with open(filename, 'rb') as fd:
                    contents = fd.read()

                # If we find a file for which we have a compressed version and
                # haven't yet seen the uncompressed one, store the possibility
                # for future use
                if entry.endswith(".gz") and filename[:-3] not in uncompnotseen:
                    uncompnotseen[filename[:-3]] = (gzip.GzipFile, filename)
                elif entry.endswith(".bz2") and filename[:-4] not in uncompnotseen:
                    uncompnotseen[filename[:-4]] = (bz2.BZ2File, filename)
                elif entry.endswith(".xz") and filename[:-3] not in uncompnotseen:
                    uncompnotseen[filename[:-3]] = (XzFile, filename)

                fileinfo[filename]['len'] = len(contents)

                for hf in hashes:
                    fileinfo[filename][hf.release_field] = hf.func(contents)

        for filename, comp in uncompnotseen.items():
            # If we've already seen the uncompressed file, we don't
            # need to do anything again
            if filename in fileinfo:
                continue

            fileinfo[filename] = {}

            # File handler is comp[0], filename of compressed file is comp[1]
            contents = comp[0](comp[1], 'r').read()

            fileinfo[filename]['len'] = len(contents)

            for hf in hashes:
                fileinfo[filename][hf.release_field] = hf.func(contents)

        for field in sorted(h.release_field for h in hashes):
            out.write('%s:\n' % field)
            for filename in sorted(fileinfo.keys()):
                out.write(" %s %8d %s\n" % (fileinfo[filename][field], fileinfo[filename]['len'], filename))

        out.close()
        os.rename(outfile + '.new', outfile)

        self._update_hashfile_table(session, fileinfo_byhash, hashes)
        self._make_byhash_links(fileinfo_byhash, hashes)
        self._make_byhash_base_symlink(fileinfo_byhash, hashes)

        sign_release_dir(suite, os.path.dirname(outfile))

        os.chdir(oldcwd)

        return


def main():
    global Logger

    cnf = Config()

    for i in ["Help", "Suite", "Force", "Quiet"]:
        key = "Generate-Releases::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    Arguments = [('h', "help", "Generate-Releases::Options::Help"),
                 ('a', 'archive', 'Generate-Releases::Options::Archive', 'HasArg'),
                 ('s', "suite", "Generate-Releases::Options::Suite"),
                 ('f', "force", "Generate-Releases::Options::Force"),
                 ('q', "quiet", "Generate-Releases::Options::Quiet"),
                 ('o', 'option', '', 'ArbItem')]

    suite_names = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Generate-Releases::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger('generate-releases')
    pool = DakProcessPool()

    session = DBConn().session()

    if Options["Suite"]:
        suites = []
        for s in suite_names:
            suite = get_suite(s.lower(), session)
            if suite:
                suites.append(suite)
            else:
                print("cannot find suite %s" % s)
                Logger.log(['cannot find suite %s' % s])
    else:
        query = session.query(Suite).filter(Suite.untouchable == False)  # noqa:E712
        if 'Archive' in Options:
            archive_names = utils.split_args(Options['Archive'])
            query = query.join(Suite.archive).filter(Archive.archive_name.in_(archive_names))
        suites = query.all()

    for s in suites:
        # Setup a multiprocessing Pool. As many workers as we have CPU cores.
        if s.untouchable and not Options["Force"]:
            print("Skipping %s (untouchable)" % s.suite_name)
            continue

        if not Options["Quiet"]:
            print("Processing %s" % s.suite_name)
        Logger.log(['Processing release file for Suite: %s' % (s.suite_name)])
        pool.apply_async(generate_helper, (s.suite_id, ))

    # No more work will be added to our pool, close it and then wait for all to finish
    pool.close()
    pool.join()

    retcode = pool.overall_status()

    if retcode > 0:
        # TODO: CENTRAL FUNCTION FOR THIS / IMPROVE LOGGING
        Logger.log(['Release file generation broken: %s' % (','.join([str(x[1]) for x in pool.results]))])

    Logger.close()

    sys.exit(retcode)


def generate_helper(suite_id):
    '''
    This function is called in a new subprocess.
    '''
    session = DBConn().session()
    suite = Suite.get(suite_id, session)

    # We allow the process handler to catch and deal with any exceptions
    rw = ReleaseWriter(suite)
    rw.generate_release_files()

    return (PROC_STATUS_SUCCESS, 'Release file written for %s' % suite.suite_name)

#######################################################################################


if __name__ == '__main__':
    main()
