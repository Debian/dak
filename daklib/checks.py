# Copyright (C) 2012, Ansgar Burchardt <ansgar@debian.org>
#
# Parts based on code that is
# Copyright (C) 2001-2006, James Troup <james@nocrew.org>
# Copyright (C) 2009-2010, Joerg Jaspert <joerg@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""module provided pre-acceptance tests

Please read the documentation for the `Check` class for the interface.
"""

from daklib.config import Config
from .dbconn import *
import daklib.dbconn as dbconn
from .regexes import *
from .textutils import fix_maintainer, ParseMaintError
import daklib.lintian as lintian
import daklib.utils as utils

import apt_inst
import apt_pkg
from apt_pkg import version_compare
import os
import time
import yaml

# TODO: replace by subprocess
import commands

class Reject(Exception):
    """exception raised by failing checks"""
    pass

class Check(object):
    """base class for checks

    checks are called by daklib.archive.ArchiveUpload.  Failing tests should
    raise a `daklib.checks.Reject` exception including a human-readable
    description why the upload should be rejected.
    """
    def check(self, upload):
        """do checks

        Args:
           upload (daklib.archive.ArchiveUpload): upload to check

        Raises:
           daklib.checks.Reject
        """
        raise NotImplemented
    def per_suite_check(self, upload, suite):
        """do per-suite checks

        Args:
           upload (daklib.archive.ArchiveUpload): upload to check
           suite (daklib.dbconn.Suite): suite to check

        Raises:
           daklib.checks.Reject
        """
        raise NotImplemented
    @property
    def forcable(self):
        """allow to force ignore failing test

        True if it is acceptable to force ignoring a failing test,
        False otherwise
        """
        return False

class SignatureCheck(Check):
    """Check signature of changes and dsc file (if included in upload)

    Make sure the signature is valid and done by a known user.
    """
    def check(self, upload):
        changes = upload.changes
        if not changes.valid_signature:
            raise Reject("Signature for .changes not valid.")
        if changes.source is not None:
            if not changes.source.valid_signature:
                raise Reject("Signature for .dsc not valid.")
            if changes.source.primary_fingerprint != changes.primary_fingerprint:
                raise Reject(".changes and .dsc not signed by the same key.")
        if upload.fingerprint is None or upload.fingerprint.uid is None:
            raise Reject(".changes signed by unknown key.")

class ChangesCheck(Check):
    """Check changes file for syntax errors."""
    def check(self, upload):
        changes = upload.changes
        control = changes.changes
        fn = changes.filename

        for field in ('Distribution', 'Source', 'Binary', 'Architecture', 'Version', 'Maintainer', 'Files', 'Changes', 'Description'):
            if field not in control:
                raise Reject('{0}: misses mandatory field {1}'.format(fn, field))

        source_match = re_field_source.match(control['Source'])
        if not source_match:
            raise Reject('{0}: Invalid Source field'.format(fn))
        version_match = re_field_version.match(control['Version'])
        if not version_match:
            raise Reject('{0}: Invalid Version field'.format(fn))
        version_without_epoch = version_match.group('without_epoch')

        match = re_file_changes.match(fn)
        if not match:
            raise Reject('{0}: Does not match re_file_changes'.format(fn))
        if match.group('package') != source_match.group('package'):
            raise Reject('{0}: Filename does not match Source field'.format(fn))
        if match.group('version') != version_without_epoch:
            raise Reject('{0}: Filename does not match Version field'.format(fn))

        for bn in changes.binary_names:
            if not re_field_package.match(bn):
                raise Reject('{0}: Invalid binary package name {1}'.format(fn, bn))

        if 'source' in changes.architectures and changes.source is None:
            raise Reject("Changes has architecture source, but no source found.")
        if changes.source is not None and 'source' not in changes.architectures:
            raise Reject("Upload includes source, but changes does not say so.")

        try:
            fix_maintainer(changes.changes['Maintainer'])
        except ParseMaintError as e:
            raise Reject('{0}: Failed to parse Maintainer field: {1}'.format(changes.filename, e))

        try:
            changed_by = changes.changes.get('Changed-By')
            if changed_by is not None:
                fix_maintainer(changed_by)
        except ParseMaintError as e:
            raise Reject('{0}: Failed to parse Changed-By field: {1}'.format(changes.filename, e))

        if len(changes.files) == 0:
            raise Reject("Changes includes no files.")

        for bugnum in changes.closed_bugs:
            if not re_isanum.match(bugnum):
                raise Reject('{0}: "{1}" in Closes field is not a number'.format(changes.filename, bugnum))

        return True

class HashesCheck(Check):
    """Check hashes in .changes and .dsc are valid."""
    def check(self, upload):
        changes = upload.changes
        for f in changes.files.itervalues():
            f.check(upload.directory)
            source = changes.source
        if source is not None:
            for f in source.files.itervalues():
                f.check(upload.directory)

class BinaryCheck(Check):
    """Check binary packages for syntax errors."""
    def check(self, upload):
        for binary in upload.changes.binaries:
            self.check_binary(upload, binary)

        binary_names = set([ binary.control['Package'] for binary in upload.changes.binaries ])
        for bn in binary_names:
            if bn not in upload.changes.binary_names:
                raise Reject('Package {0} is not mentioned in Binary field in changes'.format(bn))

        return True

    def check_binary(self, upload, binary):
        fn = binary.hashed_file.filename
        control = binary.control

        for field in ('Package', 'Architecture', 'Version', 'Description'):
            if field not in control:
                raise Reject('{0}: Missing mandatory field {0}.'.format(fn, field))

        # check fields

        package = control['Package']
        if not re_field_package.match(package):
            raise Reject('{0}: Invalid Package field'.format(fn))

        version = control['Version']
        version_match = re_field_version.match(version)
        if not version_match:
            raise Reject('{0}: Invalid Version field'.format(fn))
        version_without_epoch = version_match.group('without_epoch')

        architecture = control['Architecture']
        if architecture not in upload.changes.architectures:
            raise Reject('{0}: Architecture not in Architecture field in changes file'.format(fn))
        if architecture == 'source':
            raise Reject('{0}: Architecture "source" invalid for binary packages'.format(fn))

        source = control.get('Source')
        if source is not None and not re_field_source.match(source):
            raise Reject('{0}: Invalid Source field'.format(fn))

        # check filename

        match = re_file_binary.match(fn)
        if package != match.group('package'):
            raise Reject('{0}: filename does not match Package field'.format(fn))
        if version_without_epoch != match.group('version'):
            raise Reject('{0}: filename does not match Version field'.format(fn))
        if architecture != match.group('architecture'):
            raise Reject('{0}: filename does not match Architecture field'.format(fn))

        # check dependency field syntax

        for field in ('Breaks', 'Conflicts', 'Depends', 'Enhances', 'Pre-Depends',
                      'Provides', 'Recommends', 'Replaces', 'Suggests'):
            value = control.get(field)
            if value is not None:
                if value.strip() == '':
                    raise Reject('{0}: empty {1} field'.format(fn, field))
                try:
                    apt_pkg.parse_depends(value)
                except:
                    raise Reject('{0}: APT could not parse {1} field'.format(fn, field))

        for field in ('Built-Using',):
            value = control.get(field)
            if value is not None:
                if value.strip() == '':
                    raise Reject('{0}: empty {1} field'.format(fn, field))
                try:
                    apt_pkg.parse_src_depends(value)
                except:
                    raise Reject('{0}: APT could not parse {1} field'.format(fn, field))

class BinaryTimestampCheck(Check):
    """check timestamps of files in binary packages

    Files in the near future cause ugly warnings and extreme time travel
    can cause errors on extraction.
    """
    def check(self, upload):
        cnf = Config()
        future_cutoff = time.time() + cnf.find_i('Dinstall::FutureTimeTravelGrace', 24*3600)
        past_cutoff = time.mktime(time.strptime(cnf.find('Dinstall::PastCutoffYear', '1984'), '%Y'))

        class TarTime(object):
            def __init__(self):
                self.future_files = dict()
                self.past_files = dict()
            def callback(self, member, data):
                if member.mtime > future_cutoff:
                    future_files[member.name] = member.mtime
                elif member.mtime < past_cutoff:
                    past_files[member.name] = member.mtime

        def format_reason(filename, direction, files):
            reason = "{0}: has {1} file(s) with a timestamp too far in the {2}:\n".format(filename, len(files), direction)
            for fn, ts in files.iteritems():
                reason += "  {0} ({1})".format(fn, time.ctime(ts))
            return reason

        for binary in upload.changes.binaries:
            filename = binary.hashed_file.filename
            path = os.path.join(upload.directory, filename)
            deb = apt_inst.DebFile(path)
            tar = TarTime()
            deb.control.go(tar.callback)
            if tar.future_files:
                raise Reject(format_reason(filename, 'future', tar.future_files))
            if tar.past_files:
                raise Reject(format_reason(filename, 'past', tar.past_files))

class SourceCheck(Check):
    """Check source package for syntax errors."""
    def check_filename(self, control, filename, regex):
        # In case we have an .orig.tar.*, we have to strip the Debian revison
        # from the version number. So handle this special case first.
        is_orig = True
        match = re_file_orig.match(filename)
        if not match:
            is_orig = False
            match = regex.match(filename)

        if not match:
            raise Reject('{0}: does not match regular expression for source filenames'.format(filename))
        if match.group('package') != control['Source']:
            raise Reject('{0}: filename does not match Source field'.format(filename))

        version = control['Version']
        if is_orig:
            version = re_field_version_upstream.match(version).group('upstream')
        version_match =  re_field_version.match(version)
        version_without_epoch = version_match.group('without_epoch')
        if match.group('version') != version_without_epoch:
            raise Reject('{0}: filename does not match Version field'.format(filename))

    def check(self, upload):
        if upload.changes.source is None:
            return True

        changes = upload.changes.changes
        source = upload.changes.source
        control = source.dsc
        dsc_fn = source._dsc_file.filename

        # check fields
        if not re_field_package.match(control['Source']):
            raise Reject('{0}: Invalid Source field'.format(dsc_fn))
        if control['Source'] != changes['Source']:
            raise Reject('{0}: Source field does not match Source field in changes'.format(dsc_fn))
        if control['Version'] != changes['Version']:
            raise Reject('{0}: Version field does not match Version field in changes'.format(dsc_fn))

        # check filenames
        self.check_filename(control, dsc_fn, re_file_dsc)
        for f in source.files.itervalues():
            self.check_filename(control, f.filename, re_file_source)

        # check dependency field syntax
        for field in ('Build-Conflicts', 'Build-Conflicts-Indep', 'Build-Depends', 'Build-Depends-Arch', 'Build-Depends-Indep'):
            value = control.get(field)
            if value is not None:
                if value.strip() == '':
                    raise Reject('{0}: empty {1} field'.format(dsc_fn, field))
                try:
                    apt_pkg.parse_src_depends(value)
                except Exception as e:
                    raise Reject('{0}: APT could not parse {1} field: {2}'.format(dsc_fn, field, e))

        # TODO: check all expected files for given source format are included

class SingleDistributionCheck(Check):
    """Check that the .changes targets only a single distribution."""
    def check(self, upload):
        if len(upload.changes.distributions) != 1:
            raise Reject("Only uploads to a single distribution are allowed.")

class ACLCheck(Check):
    """Check the uploader is allowed to upload the packages in .changes"""
    def _check_dm(self, upload):
        # This code is not very nice, but hopefully works until we can replace
        # DM-Upload-Allowed, cf. https://lists.debian.org/debian-project/2012/06/msg00029.html
        session = upload.session

        if 'source' not in upload.changes.architectures:
            raise Reject('DM uploads must include source')
        for f in upload.changes.files.itervalues():
            if f.section == 'byhand' or f.section[:4] == "raw-":
                raise Reject("Uploading byhand packages is not allowed for DMs.")

        # Reject NEW packages
        distributions = upload.changes.distributions
        assert len(distributions) == 1
        suite = session.query(Suite).filter_by(suite_name=distributions[0]).one()
        overridesuite = suite
        if suite.overridesuite is not None:
            overridesuite = session.query(Suite).filter_by(suite_name=suite.overridesuite).one()
        if upload._check_new(overridesuite):
            raise Reject('Uploading NEW packages is not allowed for DMs.')

        # Check DM-Upload-Allowed
        last_suites = ['unstable', 'experimental']
        if suite.suite_name.endswith('-backports'):
            last_suites = [suite.suite_name]
        last = session.query(DBSource).filter_by(source=upload.changes.changes['Source']) \
            .join(DBSource.suites).filter(Suite.suite_name.in_(last_suites)) \
            .order_by(DBSource.version.desc()).limit(1).first()
        if last is None:
            raise Reject('No existing source found in {0}'.format(' or '.join(last_suites)))
        if not last.dm_upload_allowed:
            raise Reject('DM-Upload-Allowed is not set in {0}={1}'.format(last.source, last.version))

        # check current Changed-by is in last Maintainer or Uploaders
        uploader_names = [ u.name for u in last.uploaders ]
        changed_by_field = upload.changes.changes.get('Changed-By', upload.changes.changes['Maintainer'])
        if changed_by_field not in uploader_names:
            raise Reject('{0} is not an uploader for {1}={2}'.format(changed_by_field, last.source, last.version))

        # check Changed-by is the DM
        changed_by = fix_maintainer(changed_by_field)
        uid = upload.fingerprint.uid
        if uid is None:
            raise Reject('Unknown uid for fingerprint {0}'.format(upload.fingerprint.fingerprint))
        if uid.uid != changed_by[3] and uid.name != changed_by[2]:
            raise Reject('DMs are not allowed to sponsor uploads (expected {0} <{1}> as maintainer, but got {2})'.format(uid.name, uid.uid, changed_by_field))

        # Try to catch hijacks.
        # This doesn't work correctly. Uploads to experimental can still
        # "hijack" binaries from unstable. Also one can hijack packages
        # via buildds (but people who try this should not be DMs).
        for binary_name in upload.changes.binary_names:
            binaries = session.query(DBBinary).join(DBBinary.source) \
                .join(DBBinary.suites).filter(Suite.suite_name.in_(upload.changes.distributions)) \
                .filter(DBBinary.package == binary_name)
            for binary in binaries:
                if binary.source.source != upload.changes.changes['Source']:
                    raise Reject('DMs must not hijack binaries (binary={0}, other-source={1})'.format(binary_name, binary.source.source))

        return True

    def check(self, upload):
        fingerprint = upload.fingerprint
        source_acl = fingerprint.source_acl
        if source_acl is None:
            if 'source' in upload.changes.architectures:
                raise Reject('Fingerprint {0} must not upload source'.format(fingerprint.fingerprint))
        elif source_acl.access_level == 'dm':
            self._check_dm(upload)
        elif source_acl.access_level != 'full':
            raise Reject('Unknown source_acl access level {0} for fingerprint {1}'.format(source_acl.access_level, fingerprint.fingerprint))

        bin_architectures = set(upload.changes.architectures)
        bin_architectures.discard('source')
        binary_acl = fingerprint.binary_acl
        if binary_acl is None:
            if len(bin_architectures) > 0:
                raise Reject('Fingerprint {0} must not upload binary packages'.format(fingerprint.fingerprint))
        elif binary_acl.access_level == 'map':
            query = upload.session.query(BinaryACLMap).filter_by(fingerprint=fingerprint)
            allowed_architectures = [ m.architecture.arch_string for m in query ]

            for arch in upload.changes.architectures:
                if arch not in allowed_architectures:
                    raise Reject('Fingerprint {0} must not  upload binaries for architecture {1}'.format(fingerprint.fingerprint, arch))
        elif binary_acl.access_level != 'full':
            raise Reject('Unknown binary_acl access level {0} for fingerprint {1}'.format(binary_acl.access_level, fingerprint.fingerprint))

        return True

class UploadBlockCheck(Check):
    """check for upload blocks"""
    def check(self, upload):
        session = upload.session
        control = upload.changes.changes

        source = re_field_source.match(control['Source']).group('package')
        version = control['Version']
        blocks = session.query(UploadBlock).filter_by(source=source) \
                        .filter((UploadBlock.version == version) | (UploadBlock.version == None))

        for block in blocks:
            if block.fingerprint == upload.fingerprint:
                raise Reject('Manual upload block in place for package {0} and fingerprint {1}:\n{2}'.format(source, upload.fingerprint.fingerprint, block.reason))
            if block.uid == upload.fingerprint.uid:
                raise Reject('Manual upload block in place for package {0} and uid {1}:\n{2}'.format(source, block.uid.uid, block.reason))

        return True

class TransitionCheck(Check):
    """check for a transition"""
    def check(self, upload):
        if 'source' not in upload.changes.architectures:
            return True

        transitions = self.get_transitions()
        if transitions is None:
            return True

        source = re_field_source.match(control['Source']).group('package')

        for trans in transitions:
            t = transitions[trans]
            source = t["source"]
            expected = t["new"]

            # Will be None if nothing is in testing.
            current = get_source_in_suite(source, "testing", session)
            if current is not None:
                compare = apt_pkg.version_compare(current.version, expected)

            if current is None or compare < 0:
                # This is still valid, the current version in testing is older than
                # the new version we wait for, or there is none in testing yet

                # Check if the source we look at is affected by this.
                if source in t['packages']:
                    # The source is affected, lets reject it.

                    rejectmsg = "{0}: part of the {1} transition.\n\n".format(source, trans)

                    if current is not None:
                        currentlymsg = "at version {0}".format(current.version)
                    else:
                        currentlymsg = "not present in testing"

                    rejectmsg += "Transition description: {0}\n\n".format(t["reason"])

                    rejectmsg += "\n".join(textwrap.wrap("""Your package
is part of a testing transition designed to get {0} migrated (it is
currently {1}, we need version {2}).  This transition is managed by the
Release Team, and {3} is the Release-Team member responsible for it.
Please mail debian-release@lists.debian.org or contact {3} directly if you
need further assistance.  You might want to upload to experimental until this
transition is done.""".format(source, currentlymsg, expected,t["rm"])))

                    raise Reject(rejectmsg)

        return True

    def get_transitions(self):
        cnf = Config()
        path = cnf.get('Dinstall::ReleaseTransitions', '')
        if path == '' or not os.path.exists(path):
            return None

        contents = file(path, 'r').read()
        try:
            transitions = yaml.load(contents)
            return transitions
        except yaml.YAMLError as msg:
            utils.warn('Not checking transitions, the transitions file is broken: {0}'.format(msg))

        return None

class NoSourceOnlyCheck(Check):
    """Check for source-only upload

    Source-only uploads are only allowed if Dinstall::AllowSourceOnlyUploads is
    set. Otherwise they are rejected.
    """
    def check(self, upload):
        if Config().find_b("Dinstall::AllowSourceOnlyUploads"):
            return True
        changes = upload.changes
        if changes.source is not None and len(changes.binaries) == 0:
            raise Reject('Source-only uploads are not allowed.')
        return True

class LintianCheck(Check):
    """Check package using lintian"""
    def check(self, upload):
        changes = upload.changes

        # Only check sourceful uploads.
        if changes.source is None:
            return True
        # Only check uploads to unstable or experimental.
        if 'unstable' not in changes.distributions and 'experimental' not in changes.distributions:
            return True

        cnf = Config()
        if 'Dinstall::LintianTags' not in cnf:
            return True
        tagfile = cnf['Dinstall::LintianTags']

        with open(tagfile, 'r') as sourcefile:
            sourcecontent = sourcefile.read()
        try:
            lintiantags = yaml.load(sourcecontent)['lintian']
        except yaml.YAMLError as msg:
            raise Exception('Could not read lintian tags file {0}, YAML error: {1}'.format(tagfile, msg))

        fd, temp_filename = utils.temp_filename()
        temptagfile = os.fdopen(fd, 'w')
        for tags in lintiantags.itervalues():
            for tag in tags:
                print >>temptagfile, tag
        temptagfile.close()

        changespath = os.path.join(upload.directory, changes.filename)
        try:
            # FIXME: no shell
            cmd = "lintian --show-overrides --tags-from-file {0} {1}".format(temp_filename, changespath)
            result, output = commands.getstatusoutput(cmd)
        finally:
            os.unlink(temp_filename)

        if result == 2:
            utils.warn("lintian failed for %s [return code: %s]." % \
                (changespath, result))
            utils.warn(utils.prefix_multi_line_string(output, \
                " [possible output:] "))

        parsed_tags = lintian.parse_lintian_output(output)
        rejects = list(lintian.generate_reject_messages(parsed_tags, lintiantags))
        if len(rejects) != 0:
            raise Reject('\n'.join(rejects))

        return True

class SourceFormatCheck(Check):
    """Check source format is allowed in the target suite"""
    def per_suite_check(self, upload, suite):
        source = upload.changes.source
        session = upload.session
        if source is None:
            return True

        source_format = source.dsc['Format']
        query = session.query(SrcFormat).filter_by(format_name=source_format).filter(SrcFormat.suites.contains(suite))
        if query.first() is None:
            raise Reject('source format {0} is not allowed in suite {1}'.format(source_format, suite.suite_name))

class SuiteArchitectureCheck(Check):
    def per_suite_check(self, upload, suite):
        session = upload.session
        for arch in upload.changes.architectures:
            query = session.query(Architecture).filter_by(arch_string=arch).filter(Architecture.suites.contains(suite))
            if query.first() is None:
                raise Reject('Architecture {0} is not allowed in suite {2}'.format(arch, suite.suite_name))

        return True

class VersionCheck(Check):
    """Check version constraints"""
    def _highest_source_version(self, session, source_name, suite):
        db_source = session.query(DBSource).filter_by(source=source_name) \
            .filter(DBSource.suites.contains(suite)).order_by(DBSource.version.desc()).first()
        if db_source is None:
            return None
        else:
            return db_source.version

    def _highest_binary_version(self, session, binary_name, suite, architecture):
        db_binary = session.query(DBBinary).filter_by(package=binary_name) \
            .filter(DBBinary.suites.contains(suite)) \
            .join(DBBinary.architecture) \
            .filter(Architecture.arch_string.in_(['all', architecture])) \
            .order_by(DBBinary.version.desc()).first()
        if db_binary is None:
            return None
        else:
            return db_binary.version

    def _version_checks(self, upload, suite, op):
        session = upload.session

        if upload.changes.source is not None:
            source_name = upload.changes.source.dsc['Source']
            source_version = upload.changes.source.dsc['Version']
            v = self._highest_source_version(session, source_name, suite)
            if v is not None and not op(version_compare(source_version, v)):
                raise Reject('Version check failed (source={0}, version={1}, other-version={2}, suite={3})'.format(source_name, source_version, v, suite.suite_name))

        for binary in upload.changes.binaries:
            binary_name = binary.control['Package']
            binary_version = binary.control['Version']
            architecture = binary.control['Architecture']
            v = self._highest_binary_version(session, binary_name, suite, architecture)
            if v is not None and not op(version_compare(binary_version, v)):
                raise Reject('Version check failed (binary={0}, version={1}, other-version={2}, suite={3})'.format(binary_name, binary_version, v, suite.suite_name))

    def per_suite_check(self, upload, suite):
        session = upload.session

        vc_newer = session.query(dbconn.VersionCheck).filter_by(suite=suite) \
            .filter(dbconn.VersionCheck.check.in_(['MustBeNewerThan', 'Enhances']))
        must_be_newer_than = [ vc.reference for vc in vc_newer ]
        # Must be newer than old versions in `suite`
        must_be_newer_than.append(suite)

        for s in must_be_newer_than:
            self._version_checks(upload, s, lambda result: result > 0)

        vc_older = session.query(dbconn.VersionCheck).filter_by(suite=suite, check='MustBeOlderThan')
        must_be_older_than = [ vc.reference for vc in vc_older ]

        for s in must_be_older_than:
            self._version_checks(upload, s, lambda result: result < 0)

        return True

    @property
    def forcable(self):
        return True
