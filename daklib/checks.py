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

Please read the documentation for the L{Check} class for the interface.
"""

from daklib.config import Config
from daklib.dbconn import *
import daklib.dbconn as dbconn
from daklib.regexes import *
from daklib.textutils import fix_maintainer, ParseMaintError
import daklib.lintian as lintian
import daklib.utils as utils
import daklib.upload

import apt_inst
import apt_pkg
from apt_pkg import version_compare
import datetime
import os
import six
import subprocess
import tempfile
import textwrap
import time
import yaml


def check_fields_for_valid_utf8(filename, control):
    """Check all fields of a control file for valid UTF-8"""
    for field in control.keys():
        try:
            six.ensure_text(field)
            six.ensure_text(control[field])
        except UnicodeDecodeError:
            raise Reject('{0}: The {1} field is not valid UTF-8'.format(filename, field))


class Reject(Exception):
    """exception raised by failing checks"""
    pass


class RejectExternalFilesMismatch(Reject):
    """exception raised by failing the external hashes check"""

    def __str__(self):
        return "'%s' has mismatching %s from the external files db ('%s' [current] vs '%s' [external])" % self.args[:4]


class RejectACL(Reject):
    """exception raise by failing ACL checks"""

    def __init__(self, acl, reason):
        self.acl = acl
        self.reason = reason

    def __str__(self):
        return "ACL {0}: {1}".format(self.acl.name, self.reason)


class Check(object):
    """base class for checks

    checks are called by L{daklib.archive.ArchiveUpload}. Failing tests should
    raise a L{daklib.checks.Reject} exception including a human-readable
    description why the upload should be rejected.
    """

    def check(self, upload):
        """do checks

        @type  upload: L{daklib.archive.ArchiveUpload}
        @param upload: upload to check

        @raise daklib.checks.Reject: upload should be rejected
        """
        raise NotImplementedError

    def per_suite_check(self, upload, suite):
        """do per-suite checks

        @type  upload: L{daklib.archive.ArchiveUpload}
        @param upload: upload to check

        @type  suite: L{daklib.dbconn.Suite}
        @param suite: suite to check

        @raise daklib.checks.Reject: upload should be rejected
        """
        raise NotImplementedError

    @property
    def forcable(self):
        """allow to force ignore failing test

        C{True} if it is acceptable to force ignoring a failing test,
        C{False} otherwise
        """
        return False


class SignatureAndHashesCheck(Check):
    def check_replay(self, upload):
        # Use private session as we want to remember having seen the .changes
        # in all cases.
        session = upload.session
        history = SignatureHistory.from_signed_file(upload.changes)
        r = history.query(session)
        if r is not None:
            raise Reject('Signature for changes file was already seen at {0}.\nPlease refresh the signature of the changes file if you want to upload it again.'.format(r.seen))
        return True

    """Check signature of changes and dsc file (if included in upload)

    Make sure the signature is valid and done by a known user.
    """

    def check(self, upload):
        allow_source_untrusted_sig_keys = Config().value_list('Dinstall::AllowSourceUntrustedSigKeys')

        changes = upload.changes
        if not changes.valid_signature:
            raise Reject("Signature for .changes not valid.")
        self.check_replay(upload)
        self._check_hashes(upload, changes.filename, changes.files.values())

        source = None
        try:
            source = changes.source
        except Exception as e:
            raise Reject("Invalid dsc file: {0}".format(e))
        if source is not None:
            if changes.primary_fingerprint not in allow_source_untrusted_sig_keys:
                if not source.valid_signature:
                    raise Reject("Signature for .dsc not valid.")
                if source.primary_fingerprint != changes.primary_fingerprint:
                    raise Reject(".changes and .dsc not signed by the same key.")
            self._check_hashes(upload, source.filename, source.files.values())

        if upload.fingerprint is None or upload.fingerprint.uid is None:
            raise Reject(".changes signed by unknown key.")

    """Make sure hashes match existing files

    @type  upload: L{daklib.archive.ArchiveUpload}
    @param upload: upload we are processing

    @type  filename: str
    @param filename: name of the file the expected hash values are taken from

    @type  files: sequence of L{daklib.upload.HashedFile}
    @param files: files to check the hashes for
    """

    def _check_hashes(self, upload, filename, files):
        try:
            for f in files:
                f.check(upload.directory)
        except daklib.upload.FileDoesNotExist as e:
            raise Reject('{0}: {1}\n'
                         'Perhaps you need to include the file in your upload?\n\n'
                         'If the orig tarball is missing, the -sa flag for dpkg-buildpackage will be your friend.'
                         .format(filename, six.text_type(e)))
        except daklib.upload.UploadException as e:
            raise Reject('{0}: {1}'.format(filename, six.text_type(e)))


class WeakSignatureCheck(Check):
    """Check that .changes and .dsc are not signed using a weak algorithm"""

    def check(self, upload):
        changes = upload.changes
        if changes.weak_signature:
            raise Reject("The .changes was signed using a weak algorithm (such as SHA-1)")

        source = changes.source
        if source is not None:
            if source.weak_signature:
                raise Reject("The source package was signed using a weak algorithm (such as SHA-1)")

        return True


class SignatureTimestampCheck(Check):
    """Check timestamp of .changes signature"""

    def check(self, upload):
        changes = upload.changes

        now = datetime.datetime.utcnow()
        timestamp = changes.signature_timestamp
        age = now - timestamp

        age_max = datetime.timedelta(days=365)
        age_min = datetime.timedelta(days=-7)

        if age > age_max:
            raise Reject('{0}: Signature from {1} is too old (maximum age is {2} days)'.format(changes.filename, timestamp, age_max.days))
        if age < age_min:
            raise Reject('{0}: Signature from {1} is too far in the future (tolerance is {2} days)'.format(changes.filename, timestamp, abs(age_min.days)))

        return True


class ChangesCheck(Check):
    """Check changes file for syntax errors."""

    def check(self, upload):
        changes = upload.changes
        control = changes.changes
        fn = changes.filename

        for field in ('Distribution', 'Source', 'Architecture', 'Version', 'Maintainer', 'Files', 'Changes'):
            if field not in control:
                raise Reject('{0}: misses mandatory field {1}'.format(fn, field))

        if len(changes.binaries) > 0:
            for field in ('Binary', 'Description'):
                if field not in control:
                    raise Reject('{0}: binary upload requires {1} field'.format(fn, field))

        check_fields_for_valid_utf8(fn, control)

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

        if changes.sourceful and changes.source is None:
            raise Reject("Changes has architecture source, but no source found.")
        if changes.source is not None and not changes.sourceful:
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

        try:
            changes.byhand_files
        except daklib.upload.InvalidChangesException as e:
            raise Reject('{0}'.format(e))

        if len(changes.files) == 0:
            raise Reject("Changes includes no files.")

        for bugnum in changes.closed_bugs:
            if not re_isanum.match(bugnum):
                raise Reject('{0}: "{1}" in Closes field is not a number'.format(changes.filename, bugnum))

        return True


class ExternalHashesCheck(Check):
    """Checks hashes in .changes and .dsc against an external database."""

    def check_single(self, session, f):
        q = session.execute("SELECT size, md5sum, sha1sum, sha256sum FROM external_files WHERE filename LIKE :pattern", {'pattern': '%/{}'.format(f.filename)})
        (ext_size, ext_md5sum, ext_sha1sum, ext_sha256sum) = q.fetchone() or (None, None, None, None)

        if not ext_size:
            return

        if ext_size != f.size:
            raise RejectExternalFilesMismatch(f.filename, 'size', f.size, ext_size)

        if ext_md5sum != f.md5sum:
            raise RejectExternalFilesMismatch(f.filename, 'md5sum', f.md5sum, ext_md5sum)

        if ext_sha1sum != f.sha1sum:
            raise RejectExternalFilesMismatch(f.filename, 'sha1sum', f.sha1sum, ext_sha1sum)

        if ext_sha256sum != f.sha256sum:
            raise RejectExternalFilesMismatch(f.filename, 'sha256sum', f.sha256sum, ext_sha256sum)

    def check(self, upload):
        cnf = Config()

        if not cnf.use_extfiles:
            return

        session = upload.session
        changes = upload.changes

        for f in changes.files.values():
            self.check_single(session, f)
        source = changes.source
        if source is not None:
            for f in source.files.values():
                self.check_single(session, f)


class BinaryCheck(Check):
    """Check binary packages for syntax errors."""

    def check(self, upload):
        debug_deb_name_postfix = "-dbgsym"
        # XXX: Handle dynamic debug section name here

        self._architectures = set()

        for binary in upload.changes.binaries:
            self.check_binary(upload, binary)

        for arch in upload.changes.architectures:
            if arch == 'source':
                continue
            if arch not in self._architectures:
                raise Reject('{}: Architecture field includes {}, but no binary packages for {} are included in the upload'.format(upload.changes.filename, arch, arch))

        binaries = {binary.control['Package']: binary
                        for binary in upload.changes.binaries}

        for name, binary in list(binaries.items()):
            if name in upload.changes.binary_names:
                # Package is listed in Binary field. Everything is good.
                pass
            elif daklib.utils.is_in_debug_section(binary.control):
                # If we have a binary package in the debug section, we
                # can allow it to not be present in the Binary field
                # in the .changes file, so long as its name (without
                # -dbgsym) is present in the Binary list.
                if not name.endswith(debug_deb_name_postfix):
                    raise Reject('Package {0} is in the debug section, but '
                                 'does not end in {1}.'.format(name, debug_deb_name_postfix))

                # Right, so, it's named properly, let's check that
                # the corresponding package is in the Binary list
                origin_package_name = name[:-len(debug_deb_name_postfix)]
                if origin_package_name not in upload.changes.binary_names:
                    raise Reject(
                        "Debug package {debug}'s corresponding binary package "
                        "{origin} is not present in the Binary field.".format(
                            debug=name, origin=origin_package_name))
            else:
                # Someone was a nasty little hacker and put a package
                # into the .changes that isn't in debian/control. Bad,
                # bad person.
                raise Reject('Package {0} is not mentioned in Binary field in changes'.format(name))

        return True

    def check_binary(self, upload, binary):
        fn = binary.hashed_file.filename
        control = binary.control

        for field in ('Package', 'Architecture', 'Version', 'Description', 'Section'):
            if field not in control:
                raise Reject('{0}: Missing mandatory field {1}.'.format(fn, field))

        check_fields_for_valid_utf8(fn, control)

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
        self._architectures.add(architecture)

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

        def check_dependency_field(
                field, control,
                dependency_parser=apt_pkg.parse_depends,
                allow_alternatives=True,
                allow_relations=('', '<', '<=', '=', '>=', '>')):
            value = control.get(field)
            if value is not None:
                if value.strip() == '':
                    raise Reject('{0}: empty {1} field'.format(fn, field))
                try:
                    depends = dependency_parser(value)
                except:
                    raise Reject('{0}: APT could not parse {1} field'.format(fn, field))
                for group in depends:
                    if not allow_alternatives and len(group) != 1:
                        raise Reject('{0}: {1}: alternatives are not allowed'.format(fn, field))
                    for dep_pkg, dep_ver, dep_rel in group:
                        if dep_rel not in allow_relations:
                            raise Reject('{}: {}: depends on {}, but only relations {} are allowed for this field'.format(fn, field, " ".join(dep_pkg, dep_rel, dep_ver), allow_relations))

        for field in ('Breaks', 'Conflicts', 'Depends', 'Enhances', 'Pre-Depends',
                      'Recommends', 'Replaces', 'Suggests'):
            check_dependency_field(field, control)

        check_dependency_field("Provides", control,
                               allow_alternatives=False,
                               allow_relations=('', '='))
        check_dependency_field("Built-Using", control,
                               dependency_parser=apt_pkg.parse_src_depends,
                               allow_alternatives=False,
                               allow_relations=('=',))


class BinaryTimestampCheck(Check):
    """check timestamps of files in binary packages

    Files in the near future cause ugly warnings and extreme time travel
    can cause errors on extraction.
    """

    def check(self, upload):
        cnf = Config()
        future_cutoff = time.time() + cnf.find_i('Dinstall::FutureTimeTravelGrace', 24 * 3600)
        past_cutoff = time.mktime(time.strptime(cnf.find('Dinstall::PastCutoffYear', '1975'), '%Y'))

        class TarTime(object):
            def __init__(self):
                self.future_files = dict()
                self.past_files = dict()

            def callback(self, member, data):
                if member.mtime > future_cutoff:
                    self.future_files[member.name] = member.mtime
                elif member.mtime < past_cutoff:
                    self.past_files[member.name] = member.mtime

        def format_reason(filename, direction, files):
            reason = "{0}: has {1} file(s) with a timestamp too far in the {2}:\n".format(filename, len(files), direction)
            for fn, ts in files.items():
                reason += "  {0} ({1})".format(fn, time.ctime(ts))
            return reason

        for binary in upload.changes.binaries:
            filename = binary.hashed_file.filename
            path = os.path.join(upload.directory, filename)
            deb = apt_inst.DebFile(path)
            tar = TarTime()
            for archive in (deb.control, deb.data):
                archive.go(tar.callback)
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
            upstream_match = re_field_version_upstream.match(version)
            if not upstream_match:
                raise Reject('{0}: Source package includes upstream tarball, but {1} has no Debian revision.'.format(filename, version))
            version = upstream_match.group('upstream')
        version_match = re_field_version.match(version)
        version_without_epoch = version_match.group('without_epoch')
        if match.group('version') != version_without_epoch:
            raise Reject('{0}: filename does not match Version field'.format(filename))

    def check(self, upload):
        if upload.changes.source is None:
            if upload.changes.sourceful:
                raise Reject("{}: Architecture field includes source, but no source package is included in the upload".format(upload.changes.filename))
            return True

        if not upload.changes.sourceful:
            raise Reject("{}: Architecture field does not include source, but a source package is included in the upload".format(upload.changes.filename))

        changes = upload.changes.changes
        source = upload.changes.source
        control = source.dsc
        dsc_fn = source._dsc_file.filename

        check_fields_for_valid_utf8(dsc_fn, control)

        # check fields
        if not re_field_package.match(control['Source']):
            raise Reject('{0}: Invalid Source field'.format(dsc_fn))
        if control['Source'] != changes['Source']:
            raise Reject('{0}: Source field does not match Source field in changes'.format(dsc_fn))
        if control['Version'] != changes['Version']:
            raise Reject('{0}: Version field does not match Version field in changes'.format(dsc_fn))

        # check filenames
        self.check_filename(control, dsc_fn, re_file_dsc)
        for f in source.files.values():
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

        rejects = utils.check_dsc_files(dsc_fn, control, list(source.files.keys()))
        if len(rejects) > 0:
            raise Reject("\n".join(rejects))

        return True


class SingleDistributionCheck(Check):
    """Check that the .changes targets only a single distribution."""

    def check(self, upload):
        if len(upload.changes.distributions) != 1:
            raise Reject("Only uploads to a single distribution are allowed.")


class ACLCheck(Check):
    """Check the uploader is allowed to upload the packages in .changes"""

    def _does_hijack(self, session, upload, suite):
        # Try to catch hijacks.
        # This doesn't work correctly. Uploads to experimental can still
        # "hijack" binaries from unstable. Also one can hijack packages
        # via buildds (but people who try this should not be DMs).
        for binary_name in upload.changes.binary_names:
            binaries = session.query(DBBinary).join(DBBinary.source) \
                .filter(DBBinary.suites.contains(suite)) \
                .filter(DBBinary.package == binary_name)
            for binary in binaries:
                if binary.source.source != upload.changes.changes['Source']:
                    return True, binary.package, binary.source.source
        return False, None, None

    def _check_acl(self, session, upload, acl):
        source_name = upload.changes.source_name

        if acl.match_fingerprint and upload.fingerprint not in acl.fingerprints:
            return None, None
        if acl.match_keyring is not None and upload.fingerprint.keyring != acl.match_keyring:
            return None, None

        if not acl.allow_new:
            if upload.new:
                return False, "NEW uploads are not allowed"
            for f in upload.changes.files.values():
                if f.section == 'byhand' or f.section.startswith("raw-"):
                    return False, "BYHAND uploads are not allowed"
        if not acl.allow_source and upload.changes.source is not None:
            return False, "sourceful uploads are not allowed"
        binaries = upload.changes.binaries
        if len(binaries) != 0:
            if not acl.allow_binary:
                return False, "binary uploads are not allowed"
            if upload.changes.source is None and not acl.allow_binary_only:
                return False, "binary-only uploads are not allowed"
            if not acl.allow_binary_all:
                uploaded_arches = set(upload.changes.architectures)
                uploaded_arches.discard('source')
                allowed_arches = set(a.arch_string for a in acl.architectures)
                forbidden_arches = uploaded_arches - allowed_arches
                if len(forbidden_arches) != 0:
                    return False, "uploads for architecture(s) {0} are not allowed".format(", ".join(forbidden_arches))
        if not acl.allow_hijack:
            for suite in upload.final_suites:
                does_hijack, hijacked_binary, hijacked_from = self._does_hijack(session, upload, suite)
                if does_hijack:
                    return False, "hijacks are not allowed (binary={0}, other-source={1})".format(hijacked_binary, hijacked_from)

        acl_per_source = session.query(ACLPerSource).filter_by(acl=acl, fingerprint=upload.fingerprint, source=source_name).first()
        if acl.allow_per_source:
            if acl_per_source is None:
                return False, "not allowed to upload source package '{0}'".format(source_name)
        if acl.deny_per_source and acl_per_source is not None:
            return False, acl_per_source.reason or "forbidden to upload source package '{0}'".format(source_name)

        return True, None

    def check(self, upload):
        session = upload.session
        fingerprint = upload.fingerprint
        keyring = fingerprint.keyring

        if keyring is None:
            raise Reject('No keyring for fingerprint {0}'.format(fingerprint.fingerprint))
        if not keyring.active:
            raise Reject('Keyring {0} is not active'.format(keyring.name))

        acl = fingerprint.acl or keyring.acl
        if acl is None:
            raise Reject('No ACL for fingerprint {0}'.format(fingerprint.fingerprint))
        result, reason = self._check_acl(session, upload, acl)
        if not result:
            raise RejectACL(acl, reason)

        for acl in session.query(ACL).filter_by(is_global=True):
            result, reason = self._check_acl(session, upload, acl)
            if result is False:
                raise RejectACL(acl, reason)

        return True

    def per_suite_check(self, upload, suite):
        acls = suite.acls
        if len(acls) != 0:
            accept = False
            for acl in acls:
                result, reason = self._check_acl(upload.session, upload, acl)
                if result is False:
                    raise Reject(reason)
                accept = accept or result
            if not accept:
                raise Reject('Not accepted by any per-suite acl (suite={0})'.format(suite.suite_name))
        return True


class TransitionCheck(Check):
    """check for a transition"""

    def check(self, upload):
        if not upload.changes.sourceful:
            return True

        transitions = self.get_transitions()
        if transitions is None:
            return True

        session = upload.session

        control = upload.changes.changes
        source = re_field_source.match(control['Source']).group('package')

        for trans in transitions:
            t = transitions[trans]
            transition_source = t["source"]
            expected = t["new"]

            # Will be None if nothing is in testing.
            current = get_source_in_suite(transition_source, "testing", session)
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
transition is done.""".format(transition_source, currentlymsg, expected, t["rm"])))

                    raise Reject(rejectmsg)

        return True

    def get_transitions(self):
        cnf = Config()
        path = cnf.get('Dinstall::ReleaseTransitions', '')
        if path == '' or not os.path.exists(path):
            return None

        with open(path, 'r') as fd:
            contents = fd.read()
        try:
            transitions = yaml.safe_load(contents)
            return transitions
        except yaml.YAMLError as msg:
            utils.warn('Not checking transitions, the transitions file is broken: {0}'.format(msg))

        return None


class NoSourceOnlyCheck(Check):
    def is_source_only_upload(self, upload):
        changes = upload.changes
        if changes.source is not None and len(changes.binaries) == 0:
            return True
        return False

    """Check for source-only upload

    Source-only uploads are only allowed if Dinstall::AllowSourceOnlyUploads is
    set. Otherwise they are rejected.

    Source-only uploads are only accepted for source packages having a
    Package-List field that also lists architectures per package. This
    check can be disabled via
    Dinstall::AllowSourceOnlyUploadsWithoutPackageList.

    Source-only uploads to NEW are only allowed if
    Dinstall::AllowSourceOnlyNew is set.

    Uploads not including architecture-independent packages are only
    allowed if Dinstall::AllowNoArchIndepUploads is set.

    """

    def check(self, upload):
        if not self.is_source_only_upload(upload):
            return True

        allow_source_only_uploads = Config().find_b('Dinstall::AllowSourceOnlyUploads')
        allow_source_only_uploads_without_package_list = Config().find_b('Dinstall::AllowSourceOnlyUploadsWithoutPackageList')
        allow_source_only_new = Config().find_b('Dinstall::AllowSourceOnlyNew')
        allow_source_only_new_keys = Config().value_list('Dinstall::AllowSourceOnlyNewKeys')
        allow_source_only_new_sources = Config().value_list('Dinstall::AllowSourceOnlyNewSources')
        allow_no_arch_indep_uploads = Config().find_b('Dinstall::AllowNoArchIndepUploads', True)
        changes = upload.changes

        if not allow_source_only_uploads:
            raise Reject('Source-only uploads are not allowed.')
        if not allow_source_only_uploads_without_package_list \
           and changes.source.package_list.fallback:
            raise Reject('Source-only uploads are only allowed if a Package-List field that also list architectures is included in the source package. dpkg (>= 1.17.7) includes this information.')
        if not allow_source_only_new and upload.new \
           and changes.primary_fingerprint not in allow_source_only_new_keys \
           and changes.source_name not in allow_source_only_new_sources:
            raise Reject('Source-only uploads to NEW are not allowed.')

        if 'all' not in changes.architectures and changes.source.package_list.has_arch_indep_packages():
            if not allow_no_arch_indep_uploads:
                raise Reject('Uploads must include architecture-independent packages.')
            for suite in ('oldoldstable', 'oldoldstable-proposed-updates', 'oldoldstable-security',
                          'jessie', 'jessie-proposed-updates', 'jessie-security',
                          'oldoldstable-backports', 'oldoldstable-backports-sloppy',
                          'jessie-backports', 'jessie-backports-sloppy'):
                if suite in changes.distributions:
                    raise Reject('Suite {} is not configured to build arch:all packages. Please include them in your upload'.format(suite))

        return True


class NewOverrideCheck(Check):
    """Override NEW requirement
    """
    def check(self, upload):
        if not upload.new:
            return True

        new_override_keys = Config().value_list('Dinstall::NewOverrideKeys')
        changes = upload.changes

        if changes.primary_fingerprint in new_override_keys:
            upload.new = False

        return True


class ArchAllBinNMUCheck(Check):
    """Check for arch:all binNMUs"""

    def check(self, upload):
        changes = upload.changes

        if 'all' in changes.architectures and changes.changes.get('Binary-Only') == 'yes':
            raise Reject('arch:all binNMUs are not allowed.')

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
            lintiantags = yaml.safe_load(sourcecontent)['lintian']
        except yaml.YAMLError as msg:
            raise Exception('Could not read lintian tags file {0}, YAML error: {1}'.format(tagfile, msg))

        with tempfile.NamedTemporaryFile(mode="w+t") as temptagfile:
            os.fchmod(temptagfile.fileno(), 0o644)
            for tags in lintiantags.values():
                for tag in tags:
                    print(tag, file=temptagfile)
            temptagfile.flush()

            changespath = os.path.join(upload.directory, changes.filename)

            cmd = []
            user = cnf.get('Dinstall::UnprivUser') or None
            if user is not None:
                cmd.extend(['sudo', '-H', '-u', user])
            cmd.extend(['/usr/bin/lintian', '--show-overrides', '--tags-from-file', temptagfile.name, changespath])
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output_raw = process.communicate()[0]
            output = six.ensure_text(output_raw)
            result = process.returncode

        if result == 2:
            utils.warn("lintian failed for %s [return code: %s]." %
                (changespath, result))
            utils.warn(utils.prefix_multi_line_string(output,
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


class SuiteCheck(Check):
    def per_suite_check(self, upload, suite):
        if not suite.accept_source_uploads and upload.changes.source is not None:
            raise Reject('The suite "{0}" does not accept source uploads.'.format(suite.suite_name))
        if not suite.accept_binary_uploads and len(upload.changes.binaries) != 0:
            raise Reject('The suite "{0}" does not accept binary uploads.'.format(suite.suite_name))
        return True


class SuiteArchitectureCheck(Check):
    def per_suite_check(self, upload, suite):
        session = upload.session
        for arch in upload.changes.architectures:
            query = session.query(Architecture).filter_by(arch_string=arch).filter(Architecture.suites.contains(suite))
            if query.first() is None:
                raise Reject('Architecture {0} is not allowed in suite {1}'.format(arch, suite.suite_name))

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

    def _version_checks(self, upload, suite, other_suite, op, op_name):
        session = upload.session

        if upload.changes.source is not None:
            source_name = upload.changes.source.dsc['Source']
            source_version = upload.changes.source.dsc['Version']
            v = self._highest_source_version(session, source_name, other_suite)
            if v is not None and not op(version_compare(source_version, v)):
                raise Reject("Version check failed:\n"
                             "Your upload included the source package {0}, version {1},\n"
                             "however {3} already has version {2}.\n"
                             "Uploads to {5} must have a {4} version than present in {3}."
                             .format(source_name, source_version, v, other_suite.suite_name, op_name, suite.suite_name))

        for binary in upload.changes.binaries:
            binary_name = binary.control['Package']
            binary_version = binary.control['Version']
            architecture = binary.control['Architecture']
            v = self._highest_binary_version(session, binary_name, other_suite, architecture)
            if v is not None and not op(version_compare(binary_version, v)):
                raise Reject("Version check failed:\n"
                             "Your upload included the binary package {0}, version {1}, for {2},\n"
                             "however {4} already has version {3}.\n"
                             "Uploads to {6} must have a {5} version than present in {4}."
                             .format(binary_name, binary_version, architecture, v, other_suite.suite_name, op_name, suite.suite_name))

    def per_suite_check(self, upload, suite):
        session = upload.session

        vc_newer = session.query(dbconn.VersionCheck).filter_by(suite=suite) \
            .filter(dbconn.VersionCheck.check.in_(['MustBeNewerThan', 'Enhances']))
        must_be_newer_than = [vc.reference for vc in vc_newer]
        # Must be newer than old versions in `suite`
        must_be_newer_than.append(suite)

        for s in must_be_newer_than:
            self._version_checks(upload, suite, s, lambda result: result > 0, 'higher')

        vc_older = session.query(dbconn.VersionCheck).filter_by(suite=suite, check='MustBeOlderThan')
        must_be_older_than = [vc.reference for vc in vc_older]

        for s in must_be_older_than:
            self._version_checks(upload, suite, s, lambda result: result < 0, 'lower')

        return True

    @property
    def forcable(self):
        return True
