#! /usr/bin/env python3

"""Manage external signature requests

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2018, Ansgar Burchardt <ansgar@debian.org>

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

import apt_pkg
import sys

from daklib import daklog
from daklib.dbconn import *
from daklib.config import Config
from daklib.externalsignature import *

################################################################################

Options = None
Logger = None

################################################################################


def usage(exit_code=0):
    print("""Usage: dak manage-external-signature-requests [OPTIONS]
Manage external signature requests such as requests to sign EFI binaries or
kernel modules.

  -h, --help                 show this help and exit""")

    sys.exit(exit_code)

################################################################################


def main():
    global Options, Logger

    cnf = Config()

    for i in ["Help"]:
        key = "Manage-External-Signature-Requests::Options::{}".format(i)
        if key not in cnf:
            cnf[key] = ""

    Arguments = [('h', "help", "Manage-External-Signature-Requests::Options::Help")]

    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Manage-External-Signature-Requests::Options")

    if Options["Help"]:
        usage()

    Logger = daklog.Logger('manage-external-signature-requests')

    if 'External-Signature-Requests' not in cnf:
        print("DAK not configured to handle external signature requests")
        return

    config = cnf.subtree('External-Signature-Requests')

    session = DBConn().session()

    export_external_signature_requests(session, config['Export'])

    if 'ExportSigningKeys' in config:
        args = {
            'pubring': cnf.get('Dinstall::SigningPubKeyring') or None,
            'secring': cnf.get('Dinstall::SigningKeyring') or None,
            'homedir': cnf.get('Dinstall::SigningHomedir') or None,
            'passphrase_file': cnf.get('Dinstall::SigningPassphraseFile') or None,
        }
        sign_external_signature_requests(session, config['Export'], config.value_list('ExportSigningKeys'), args)

    session.close()

    Logger.close()

#######################################################################################


if __name__ == '__main__':
    main()
