#! /usr/bin/env python
#
# Copyright (C) 2018, Margarita Manteroa <marga@debian.org>
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

from db_test import DBDakTestCase, fixture
from daklib import archive, upload, dbconn

from unittest import main


class ArchiveTestCase(DBDakTestCase):

    def setup_keys(self):
        """ Inserts the fingerprints in the keyring into the database."""
        if 'keyring' in self.__dict__:
            return
        self.keyring = dbconn.Keyring()
        self.keyring.keyring_id = 1
        self.keyring.load_keys(fixture('packages/gpg/pubring.gpg'))
        _, _ = self.keyring.generate_users_from_keyring("%s", self.session)

        for key in self.keyring.keys.values():
            fpr = key["fingerprints"][0]
            fp = dbconn.get_or_set_fingerprint(fpr, self.session)
            fp.keyring_id = self.keyring.keyring_id
            fp.uid_id = dbconn.get_or_set_uid(key["uid"], self.session).uid_id
            self.session.add(fp)
        self.session.commit()

    def setup_suites(self):
        """Add the unstable suite which is needed for the upload."""
        if 'suite' in self.__dict__:
            return
        self.setup_archive()
        self.suite = {}
        suite_name, codename = "unstable", "sid"
        self.suite[suite_name] = dbconn.Suite(suite_name)
        self.suite[suite_name].codename = codename
        self.suite[suite_name].archive_id = self.archive.archive_id
        self.session.add(self.suite[suite_name])
        self.session.commit()

    def setup_srcformats(self):
        """Add all source formats to the supported suites."""
        for suite_name in self.suite:
            self.suite[suite_name].srcformats = self.session.query(dbconn.SrcFormat).all()
            self.session.add(self.suite[suite_name])
        self.session.commit()

    def attempt_upload(self, changes):
        """Return an ArchiveUpload for the received changes."""
        return archive.ArchiveUpload(
            fixture("packages"), changes, [fixture('packages/gpg/pubring.gpg')])

    def test_upload_rejects(self):
        # Parse the changes file
        changes = upload.Changes(fixture("packages"),
                                 "linux_42.0-1_amd64.changes",
                                 [fixture('packages/gpg/pubring.gpg')],
                                 True)

        # Insert the fingerprint, but without associating it to a keyring
        dbconn.get_or_set_fingerprint(changes.primary_fingerprint, self.session)
        self.session.commit()

        # Try to upload, it should fail with the key being unknown
        with self.attempt_upload(changes) as attempt:
            result = attempt.check()
            self.assertFalse(result)
            self.assertEquals(attempt.reject_reasons,
                [u'.changes signed by unknown key.'])

        # Import the keyring
        self.setup_keys()

        # New attempt, it should fail with missing suite
        with self.attempt_upload(changes) as attempt:
            result = attempt.check()
            self.assertFalse(result)
            self.assertEquals(attempt.reject_reasons,
                [u'No target suite found. Please check your target distribution and that you uploaded to the right archive.'])

        # Add the missing suite
        self.setup_suites()

        # New attempt, it should fail with missing srcformat
        with self.attempt_upload(changes) as attempt:
            result = attempt.check()
            self.assertFalse(result)
            self.assertEquals(attempt.reject_reasons,
                [u'source format 3.0 (quilt) is not allowed in suite unstable'])

        # Add the missing format
        self.setup_srcformats()

        # New attempt, it should fail with missing architecture
        with self.attempt_upload(changes) as attempt:
            result = attempt.check()
            self.assertFalse(result)
            self.assertEquals(attempt.reject_reasons,
                [u'Architecture source is not allowed in suite unstable'])

        # Add the missing architecture / suites connection
        self.setup_architectures()
        self.session.commit()

        # New attempt, it should succeed and be a new package.
        with self.attempt_upload(changes) as attempt:
            result = attempt.check()
            self.assertTrue(result)
            self.assertTrue(attempt.new)
            self.assertEquals(attempt.reject_reasons, [])


    def classes_to_clean(self):
        if 'suite' in self.__dict__:
            self.clean_suites()
        return [dbconn.Fingerprint, dbconn.Uid]

if __name__ == '__main__':
    main()
