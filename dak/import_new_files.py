#!/usr/bin/env python
# coding=utf8

"""
Import known_changes files

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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


################################################################################

import sys
import os
import logging
import threading
import glob
from daklib.dbconn import DBConn, get_dbchange
from daklib.config import Config

# where in dak.conf all of our configuration will be stowed
options_prefix = "NewFiles"
options_prefix = "%s::Options" % options_prefix

log = logging.getLogger()

################################################################################


def usage (exit_code=0):
    print """Usage: dak import-new-files [options]

OPTIONS
     -v, --verbose
        show verbose information messages

     -q, --quiet
        supress all output but errors

"""
    sys.exit(exit_code)

class ImportKnownChanges(object):
    @session_wrapper
    def __init__(self, session=None):
        try:
            newq = get_policy_queue('new', session)
            for changes_fn in glob.glob(newq.path + "/*.changes"):
                changes_bn = os.path.basename(fn)
                chg = session.query(DBChange).filter_by(changesname=changes_bn).one()

                u = Upload()
                u.changes_file = changes_fn
                u.load_changes(changes_fn)

                for chg_fn in u.pkg.files.keys():
                    cpf = ChangePendingFile()
                    cpf.filename = chg_fn
                    cpf.size = self.files[chg_fn]['size']
                    cpf.md5sum = self.files[chg_fn]['md5sum']

                    session.add(cpf)
                    chg.files.append(cpf)


            session.commit()
            
        except KeyboardInterrupt:
            print("Caught C-c; terminating.")
            utils.warn("Caught C-c; terminating.")
            self.plsDie()


def main():
    cnf = Config()

    arguments = [('h',"help", "%s::%s" % (options_prefix,"Help")),
                 ('q',"quiet", "%s::%s" % (options_prefix,"Quiet")),
                 ('v',"verbose", "%s::%s" % (options_prefix,"Verbose")),
                ]

    args = apt_pkg.ParseCommandLine(cnf.Cnf, arguments,sys.argv)

    num_threads = 1

    if len(args) > 0:
        usage(1)

    if cnf.has_key("%s::%s" % (options_prefix,"Help")):
        usage(0)

    level=logging.INFO
    if cnf.has_key("%s::%s" % (options_prefix,"Quiet")):
        level=logging.ERROR

    elif cnf.has_key("%s::%s" % (options_prefix,"Verbose")):
        level=logging.DEBUG


    logging.basicConfig( level=level,
                         format='%(asctime)s %(levelname)s %(message)s',
                         stream = sys.stderr )

    ImportNewFiles()


if __name__ == '__main__':
    main()
