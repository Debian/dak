#! /usr/bin/env python3
#
# Copyright (C) 2014, Ansgar Burchardt <ansgar@debian.org>
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

import datetime
import unittest
from base_test import DakTestCase, fixture
from daklib.gpg import GpgException, SignedFile

keyring = fixture('gpg/gnupghome/pubring.gpg')
fpr_valid = '0ABB89079CB58F8F94F6F310CB9D5C5828606E84'
fpr_expired = '05A558AE65B77B559BBE0C4D543B2BAEDA044F0B'
fpr_expired_subkey = '8865D9EC71713394ADBD8F729F7A24B7F6388CE1'


def verify(filename, require_signature=True):
    with open(fixture(filename), mode='rb') as fh:
        data = fh.read()
    return SignedFile(data, [keyring], require_signature)


class GpgTest(DakTestCase):
    def test_valid(self):
        result = verify('gpg/valid.asc')
        self.assertTrue(result.valid)
        self.assertFalse(result.weak_signature)
        self.assertEqual(result.primary_fingerprint, fpr_valid)
        self.assertEqual(result.contents, b"Valid: yes\n")
        self.assertEqual(result.signature_timestamp, datetime.datetime(2014, 9, 2, 21, 24, 10))

    def test_weak_sha1(self):
        result = verify('gpg/sha1.asc')
        self.assertTrue(result.valid)
        self.assertTrue(result.weak_signature)
        self.assertEqual(result.primary_fingerprint, fpr_valid)
        self.assertEqual(result.contents, b"Message generated with gpg --homedir gnupghome --digest-algo=sha1 --clearsign\n")
        self.assertEqual(result.signature_timestamp, datetime.datetime(2017, 2, 22, 18, 59, 59))

    def test_weak_ripemd160(self):
        result = verify('gpg/ripemd160.asc')
        self.assertTrue(result.valid)
        self.assertTrue(result.weak_signature)
        self.assertEqual(result.primary_fingerprint, fpr_valid)
        self.assertEqual(result.contents, b"Message generated with gpg --homedir gnupghome --digest-algo=ripemd160 --clearsign\n")
        self.assertEqual(result.signature_timestamp, datetime.datetime(2017, 2, 22, 19, 2, 54))

    def test_expired(self):
        result = verify('gpg/expired.asc', False)
        self.assertFalse(result.valid)
        self.assertEqual(result.primary_fingerprint, fpr_expired)
        self.assertEqual(result.contents, b"Valid: expired\n")
        self.assertEqual(result.signature_timestamp, datetime.datetime(2001, 2, 1, 0, 0, 0))

    def test_expired_assertion(self):
        with self.assertRaises(GpgException):
            verify('gpg/expired.asc')

    def test_expired_subkey(self):
        result = verify('gpg/expired-subkey.asc', False)
        self.assertFalse(result.valid)
        self.assertEqual(result.primary_fingerprint, fpr_expired_subkey)
        self.assertEqual(result.contents, b"Valid: expired-subkey\n")
        self.assertEqual(result.signature_timestamp, datetime.datetime(2014, 2, 1, 0, 0, 0))

    def test_expires_subkey_assertion(self):
        with self.assertRaises(GpgException):
            verify('gpg/expired-subkey.asc')

    def test_message_assertion(self):
        with self.assertRaises(GpgException):
            verify('gpg/message.asc')

    def test_plain_assertion(self):
        with self.assertRaises(GpgException):
            verify('gpg/plaintext.txt')

    def test_md5_assertion(self):
        with self.assertRaises(GpgException):
            verify('gpg/md5.asc')


if __name__ == '__main__':
    unittest.main()
