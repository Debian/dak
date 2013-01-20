"""module to handle command files

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2012, Ansgar Burchardt <ansgar@debian.org>
@license: GPL-2+
"""

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

import apt_pkg
import os
import re
import tempfile

from daklib.config import Config
from daklib.dbconn import *
from daklib.gpg import SignedFile
from daklib.regexes import re_field_package
from daklib.textutils import fix_maintainer
from daklib.utils import gpg_get_key_addresses, send_mail, TemplateSubst

class CommandError(Exception):
    pass

class CommandFile(object):
    def __init__(self, filename, data, log=None):
        if log is None:
            from daklib.daklog import Logger
            log = Logger()
        self.cc = []
        self.result = []
        self.log = log
        self.filename = filename
        self.data = data

    def _check_replay(self, signed_file, session):
        """check for replays

        @note: Will commit changes to the database.

        @type signed_file: L{daklib.gpg.SignedFile}

        @param session: database session
        """
        # Mark commands file as seen to prevent replays.
        signature_history = SignatureHistory.from_signed_file(signed_file)
        session.add(signature_history)
        session.commit()

    def _quote_section(self, section):
        lines = []
        for l in str(section).splitlines():
            lines.append("> {0}".format(l))
        return "\n".join(lines)

    def _evaluate_sections(self, sections, session):
        session.rollback()
        try:
            while True:
                sections.next()
                section = sections.section
                self.result.append(self._quote_section(section))

                action = section.get('Action', None)
                if action is None:
                    raise CommandError('Encountered section without Action field')

                if action == 'dm':
                    self.action_dm(self.fingerprint, section, session)
                elif action == 'dm-remove':
                    self.action_dm_remove(self.fingerprint, section, session)
                elif action == 'dm-migrate':
                    self.action_dm_migrate(self.fingerprint, section, session)
                elif action == 'break-the-archive':
                    self.action_break_the_archive(self.fingerprint, section, session)
                else:
                    raise CommandError('Unknown action: {0}'.format(action))

                self.result.append('')
        except StopIteration:
            pass
        finally:
            session.rollback()

    def _notify_uploader(self):
        cnf = Config()

        bcc = 'X-DAK: dak process-command'
        if 'Dinstall::Bcc' in cnf:
            bcc = '{0}\nBcc: {1}'.format(bcc, cnf['Dinstall::Bcc'])

        cc = set(fix_maintainer(address)[1] for address in self.cc)

        subst = {
            '__DAK_ADDRESS__': cnf['Dinstall::MyEmailAddress'],
            '__MAINTAINER_TO__': fix_maintainer(self.uploader)[1],
            '__CC__': ", ".join(cc),
            '__BCC__': bcc,
            '__RESULTS__': "\n".join(self.result),
            '__FILENAME__': self.filename,
            }

        message = TemplateSubst(subst, os.path.join(cnf['Dir::Templates'], 'process-command.processed'))

        send_mail(message)

    def evaluate(self):
        """evaluate commands file

        @rtype:   bool
        @returns: C{True} if the file was processed sucessfully,
                  C{False} otherwise
        """
        result = True

        session = DBConn().session()

        keyrings = session.query(Keyring).filter_by(active=True).order_by(Keyring.priority)
        keyring_files = [ k.keyring_name for k in keyrings ]

        signed_file = SignedFile(self.data, keyring_files)
        if not signed_file.valid:
            self.log.log(['invalid signature', self.filename])
            return False

        self.fingerprint = session.query(Fingerprint).filter_by(fingerprint=signed_file.primary_fingerprint).one()
        if self.fingerprint.keyring is None:
            self.log.log(['singed by key in unknown keyring', self.filename])
            return False
        assert self.fingerprint.keyring.active

        self.log.log(['processing', self.filename, 'signed-by={0}'.format(self.fingerprint.fingerprint)])

        with tempfile.TemporaryFile() as fh:
            fh.write(signed_file.contents)
            fh.seek(0)
            sections = apt_pkg.TagFile(fh)

        self.uploader = None
        addresses = gpg_get_key_addresses(self.fingerprint.fingerprint)
        if len(addresses) > 0:
            self.uploader = addresses[0]

        try:
            sections.next()
            section = sections.section
            if 'Uploader' in section:
                self.uploader = section['Uploader']
            # TODO: Verify first section has valid Archive field
            if 'Archive' not in section:
                raise CommandError('No Archive field in first section.')

            # TODO: send mail when we detected a replay.
            self._check_replay(signed_file, session)

            self._evaluate_sections(sections, session)
            self.result.append('')
        except Exception as e:
            self.log.log(['ERROR', e])
            self.result.append("There was an error processing this section. No changes were committed.\nDetails:\n{0}".format(e))
            result = False

        self._notify_uploader()

        session.close()

        return result

    def _split_packages(self, value):
        names = value.split()
        for name in names:
            if not re_field_package.match(name):
                raise CommandError('Invalid package name "{0}"'.format(name))
        return names

    def action_dm(self, fingerprint, section, session):
        cnf = Config()

        if 'Command::DM::AdminKeyrings' not in cnf \
                or 'Command::DM::ACL' not in cnf \
                or 'Command::DM::Keyrings' not in cnf:
            raise CommandError('DM command is not configured for this archive.')

        allowed_keyrings = cnf.value_list('Command::DM::AdminKeyrings')
        if fingerprint.keyring.keyring_name not in allowed_keyrings:
            raise CommandError('Key {0} is not allowed to set DM'.format(fingerprint.fingerprint))

        acl_name = cnf.get('Command::DM::ACL', 'dm')
        acl = session.query(ACL).filter_by(name=acl_name).one()

        fpr_hash = section['Fingerprint'].translate(None, ' ')
        fpr = session.query(Fingerprint).filter_by(fingerprint=fpr_hash).first()
        if fpr is None:
            raise CommandError('Unknown fingerprint {0}'.format(fpr_hash))
        if fpr.keyring is None or fpr.keyring.keyring_name not in cnf.value_list('Command::DM::Keyrings'):
            raise CommandError('Key {0} is not in DM keyring.'.format(fpr.fingerprint))
        addresses = gpg_get_key_addresses(fpr.fingerprint)
        if len(addresses) > 0:
            self.cc.append(addresses[0])

        self.log.log(['dm', 'fingerprint', fpr.fingerprint])
        self.result.append('Fingerprint: {0}'.format(fpr.fingerprint))
        if len(addresses) > 0:
            self.log.log(['dm', 'uid', addresses[0]])
            self.result.append('Uid: {0}'.format(addresses[0]))

        for source in self._split_packages(section.get('Allow', '')):
            # Check for existance of source package to catch typos
            if session.query(DBSource).filter_by(source=source).first() is None:
                raise CommandError('Tried to grant permissions for unknown source package: {0}'.format(source))

            if session.query(ACLPerSource).filter_by(acl=acl, fingerprint=fpr, source=source).first() is None:
                aps = ACLPerSource()
                aps.acl = acl
                aps.fingerprint = fpr
                aps.source = source
                aps.created_by = fingerprint
                aps.reason = section.get('Reason')
                session.add(aps)
                self.log.log(['dm', 'allow', fpr.fingerprint, source])
                self.result.append('Allowed: {0}'.format(source))
            else:
                self.result.append('Already-Allowed: {0}'.format(source))

        session.flush()

        for source in self._split_packages(section.get('Deny', '')):
            count = session.query(ACLPerSource).filter_by(acl=acl, fingerprint=fpr, source=source).delete()
            if count == 0:
                raise CommandError('Tried to remove upload permissions for package {0}, '
                                   'but no upload permissions were granted before.'.format(source))

            self.log.log(['dm', 'deny', fpr.fingerprint, source])
            self.result.append('Denied: {0}'.format(source))

        session.commit()

    def _action_dm_admin_common(self, fingerprint, section, session):
        cnf = Config()

        if 'Command::DM-Admin::AdminFingerprints' not in cnf \
                or 'Command::DM::ACL' not in cnf:
            raise CommandError('DM admin command is not configured for this archive.')

        allowed_fingerprints = cnf.value_list('Command::DM-Admin::AdminFingerprints')
        if fingerprint.fingerprint not in allowed_fingerprints:
            raise CommandError('Key {0} is not allowed to admin DM'.format(fingerprint.fingerprint))

    def action_dm_remove(self, fingerprint, section, session):
        self._action_dm_admin_common(fingerprint, section, session)

        cnf = Config()
        acl_name = cnf.get('Command::DM::ACL', 'dm')
        acl = session.query(ACL).filter_by(name=acl_name).one()

        fpr_hash = section['Fingerprint'].translate(None, ' ')
        fpr = session.query(Fingerprint).filter_by(fingerprint=fpr_hash).first()
        if fpr is None:
            self.result.append('Unknown fingerprint: {0}\nNo action taken.'.format(fpr_hash))
            return

        self.log.log(['dm-remove', fpr.fingerprint])

        count = 0
        for entry in session.query(ACLPerSource).filter_by(acl=acl, fingerprint=fpr):
            self.log.log(['dm-remove', fpr.fingerprint, 'source={0}'.format(entry.source)])
            count += 1
            session.delete(entry)

        self.result.append('Removed: {0}.\n{1} acl entries removed.'.format(fpr.fingerprint, count))

        session.commit()

    def action_dm_migrate(self, fingerprint, section, session):
        self._action_dm_admin_common(fingerprint, section, session)
        cnf = Config()
        acl_name = cnf.get('Command::DM::ACL', 'dm')
        acl = session.query(ACL).filter_by(name=acl_name).one()

        fpr_hash_from = section['From'].translate(None, ' ')
        fpr_from = session.query(Fingerprint).filter_by(fingerprint=fpr_hash_from).first()
        if fpr_from is None:
            self.result.append('Unknown fingerprint (From): {0}\nNo action taken.'.format(fpr_hash_from))
            return

        fpr_hash_to = section['To'].translate(None, ' ')
        fpr_to = session.query(Fingerprint).filter_by(fingerprint=fpr_hash_to).first()
        if fpr_to is None:
            self.result.append('Unknown fingerprint (To): {0}\nNo action taken.'.format(fpr_hash_to))
            return
        if fpr_to.keyring is None or fpr_to.keyring.keyring_name not in cnf.value_list('Command::DM::Keyrings'):
            self.result.append('Key (To) {0} is not in DM keyring.\nNo action taken.'.format(fpr_to.fingerprint))
            return

        self.log.log(['dm-migrate', 'from={0}'.format(fpr_hash_from), 'to={0}'.format(fpr_hash_to)])

        count = 0
        for entry in session.query(ACLPerSource).filter_by(acl=acl, fingerprint=fpr_from):
            self.log.log(['dm-migrate', 'from={0}'.format(fpr_hash_from), 'to={0}'.format(fpr_hash_to), 'source={0}'.format(entry.source)])
            entry.fingerprint = fpr_to
            count += 1

        self.result.append('Migrated {0} to {1}.\n{2} acl entries changed.'.format(fpr_hash_from, fpr_hash_to, count))

        session.commit()

    def action_break_the_archive(self, fingerprint, section, session):
        name = 'Dave'
        uid = fingerprint.uid
        if uid is not None and uid.name is not None:
            name = uid.name.split()[0]

        self.result.append("DAK9000: I'm sorry, {0}. I'm afraid I can't do that.".format(name))
