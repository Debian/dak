"""module to send announcements for processed packages

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

import os

from daklib.config import Config
from daklib.textutils import fix_maintainer
from daklib.utils import mail_addresses_for_upload, TemplateSubst, send_mail

class ProcessedUpload(object):
    # people
    maintainer = None
    changed_by = None
    fingerprint = None

    # suites
    suites = []
    from_policy_suites = []

    # package
    changes = None
    changes_filename = None
    sourceful = None
    source = None
    architecture = None
    version = None
    bugs = None

    # program
    program = "unknown-program"

    warnings = []

def _subst_for_upload(upload):
    cnf = Config()

    maintainer = upload.maintainer or cnf['Dinstall::MyEmailAddress']
    changed_by = upload.changed_by or maintainer
    if upload.sourceful:
        maintainer_to = mail_addresses_for_upload(maintainer, changed_by, upload.fingerprint)
    else:
        maintainer_to = mail_addresses_for_upload(maintainer, maintainer, upload.fingerprint)

    bcc = 'X-DAK: dak {0}'.format(upload.program)
    if 'Dinstall::Bcc' in cnf:
        bcc = '{0}\nBcc: {1}'.format(bcc, cnf['Dinstall::Bcc'])

    subst = {
        '__DISTRO__': cnf['Dinstall::MyDistribution'],
        '__BUG_SERVER__': cnf.get('Dinstall::BugServer'),
        '__ADMIN_ADDRESS__': cnf['Dinstall::MyAdminAddress'],
        '__DAK_ADDRESS__': cnf['Dinstall::MyEmailAddress'],
        '__REJECTOR_ADDRESS__': cnf['Dinstall::MyEmailAddress'],
        '__MANUAL_REJECT_MESSAGE__': '',

        '__BCC__': bcc,

        '__MAINTAINER__': changed_by,
        '__MAINTAINER_FROM__': fix_maintainer(changed_by)[1],
        '__MAINTAINER_TO__': ', '.join(maintainer_to),
        '__CHANGES_FILENAME__': upload.changes_filename,
        '__FILE_CONTENTS__': upload.changes,
        '__SOURCE__': upload.source,
        '__VERSION__': upload.version,
        '__ARCHITECTURE__': upload.architecture,
        '__WARNINGS__': '\n'.join(upload.warnings),
        }

    override_maintainer = cnf.get('Dinstall::OverrideMaintainer')
    if override_maintainer:
        subst['__MAINTAINER_FROM__'] = subst['__MAINTAINER_TO__'] = override_maintainer

    return subst

def _whitelists(upload):
    return [ s.mail_whitelist for s in upload.suites ]

def announce_reject(upload, reason, rejected_by=None):
    cnf = Config()
    subst = _subst_for_upload(upload)
    whitelists = _whitelists(upload)

    automatic = rejected_by is None

    subst['__CC__'] = 'X-DAK-Rejection: {0}'.format('automatic' if automatic else 'manual')
    subst['__REJECT_MESSAGE__'] = reason

    if rejected_by:
        subst['__REJECTOR_ADDRESS__'] = rejected_by

    if not automatic:
        subst['__BCC__'] = '{0}\nBcc: {1}'.format(subst['__BCC__'], subst['__REJECTOR_ADDRESS__'])

    message = TemplateSubst(subst, os.path.join(cnf['Dir::Templates'], 'queue.rejected'))
    send_mail(message, whitelists=whitelists)

def announce_accept(upload):
    cnf = Config()
    subst = _subst_for_upload(upload)
    whitelists = _whitelists(upload)

    accepted_to_real_suite = any(suite.policy_queue is None or suite in upload.from_policy_suites for suite in upload.suites)

    suite_names = []
    for suite in upload.suites:
        if suite.policy_queue:
            suite_names.append("{0}->{1}".format(suite.suite_name, suite.policy_queue.queue_name))
        else:
            suite_names.append(suite.suite_name)
    suite_names.extend(suite.suite_name for suite in upload.from_policy_suites)
    subst['__SUITE__'] = ', '.join(suite_names) or '(none)'

    message = TemplateSubst(subst, os.path.join(cnf['Dir::Templates'], 'process-unchecked.accepted'))
    send_mail(message, whitelists=whitelists)

    if accepted_to_real_suite and upload.sourceful:
        # senf mail to announce lists and tracking server
        announce = set()
        for suite in upload.suites:
            if suite.policy_queue is None or suite in upload.from_policy_suites:
                announce.update(suite.announce or [])

        announce_list_address = ", ".join(announce)

        tracking = cnf.get('Dinstall::TrackingServer')
        if tracking:
            announce_list_address = "{0}\nBcc: {1}@{2}".format(announce_list_address, upload.source, tracking)

        if len(announce_list_address) != 0:
            my_subst = subst.copy()
            my_subst['__ANNOUNCE_LIST_ADDRESS__'] = announce_list_address

            message = TemplateSubst(my_subst, os.path.join(cnf['Dir::Templates'], 'process-unchecked.announce'))
            send_mail(message, whitelists=whitelists)

    close_bugs_default = cnf.find_b('Dinstall::CloseBugs')
    close_bugs = any(s.close_bugs if s.close_bugs is not None else close_bugs_default for s in upload.suites)
    if accepted_to_real_suite and upload.sourceful and close_bugs:
        for bug in upload.bugs:
            my_subst = subst.copy()
            my_subst['__BUG_NUMBER__'] = str(bug)

            message = TemplateSubst(my_subst, os.path.join(cnf['Dir::Templates'], 'process-unchecked.bug-close'))
            send_mail(message, whitelists=whitelists)

def announce_new(upload):
    cnf = Config()
    subst = _subst_for_upload(upload)
    whitelists = _whitelists(upload)

    message = TemplateSubst(subst, os.path.join(cnf['Dir::Templates'], 'process-unchecked.new'))
    send_mail(message, whitelists=whitelists)
