#!/usr/bin/env python

"""
Wrapper to launch dak functionality

G{importgraph}

"""
# Copyright (C) 2005, 2006 Anthony Towns <ajt@debian.org>
# Copyright (C) 2006 James Troup <james@nocrew.org>

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

# well I don't know where you're from but in AMERICA, there's a little
# thing called "abstinent until proven guilty."
#  -- http://harrietmiers.blogspot.com/2005/10/wow-i-feel-loved.html

# (if James had a blog, I bet I could find a funny quote in it to use!)

################################################################################

import os
import sys
import traceback
import daklib.utils

from daklib.daklog import Logger
from daklib.config import Config
from daklib.dak_exceptions import CantOpenError

################################################################################

def init():
    """Setup the list of modules and brief explanation of what they
    do."""

    functionality = [
        ("ls",
         "Show which suites packages are in"),
        ("override",
         "Query/change the overrides"),
        ("check-archive",
         "Archive sanity checks"),
        ("queue-report",
         "Produce a report on NEW and BYHAND packages"),
        ("show-new",
         "Output html for packages in NEW"),
        ("show-deferred",
         "Output html and symlinks for packages in DEFERRED"),
        ("graph",
         "Output graphs of number of packages in various queues"),

        ("rm",
         "Remove packages from suites"),

        ("process-new",
         "Process NEW and BYHAND packages"),
        ("process-upload",
         "Process packages in queue/unchecked"),
        ("process-commands",
         "Process command files (*.dak-commands)"),
        ("process-policy",
         "Process packages in policy queues from COMMENTS files"),

        ("dominate",
         "Remove obsolete source and binary associations from suites"),
        ("export",
         "Export uploads from policy queues"),
        ("export-suite",
         "export a suite to a flat directory structure"),
        ("make-pkg-file-mapping",
         "Generate package <-> file mapping"),
        ("generate-filelist",
         "Generate file lists for apt-ftparchive"),
        ("generate-releases",
         "Generate Release files"),
        ("generate-packages-sources",
         "Generate Packages/Sources files"),
        ("generate-packages-sources2",
         "Generate Packages/Sources files [directly from database]"),
        ("contents",
         "Generate content files"),
        ("metadata",
         "Load data for packages/sources files"),
        ("generate-index-diffs",
         "Generate .diff/Index files"),
        ("clean-suites",
         "Clean unused/superseded packages from the archive"),
        ("manage-build-queues",
         "Clean and update metadata for build queues"),
        ("clean-queues",
         "Clean cruft from incoming"),

        ("transitions",
         "Manage the release transition file"),
        ("check-overrides",
         "Override cruft checks"),
        ("control-overrides",
         "Manipulate/list override entries in bulk"),
        ("control-suite",
         "Manipulate suites in bulk"),
        ("cruft-report",
         "Check for obsolete or duplicated packages"),
        ("examine-package",
         "Show information useful for NEW processing"),
        ("import",
         "Import existing source and binary packages"),
        ("import-keyring",
         "Populate fingerprint/uid table based on a new/updated keyring"),
        ("import-users-from-passwd",
         "Sync PostgreSQL users with passwd file"),
        ("acl",
         "Manage upload ACLs"),
        ("admin",
         "Perform administration on the dak database"),
        ("update-db",
         "Updates databae schema to latest revision"),
        ("init-dirs",
         "Initial setup of the archive"),
        ("make-maintainers",
         "Generates Maintainers file for BTS etc"),
        ("make-overrides",
         "Generates override files"),
        ("new-security-install",
         "New way to install a security upload into the archive"),
        ("stats",
         "Generate statistics"),
        ("bts-categorize",
         "Categorize uncategorized bugs filed against ftp.debian.org"),
        ("add-user",
         "Add a user to the archive"),
        ("make-changelog",
         "Generate changelog between two suites"),
        ("copy-installer",
         "Copies the installer from one suite to another"),
        ("override-disparity",
         "Generate a list of override disparities"),
        ("external-overrides",
         "Modify external overrides"),
        ]
    return functionality

################################################################################

def usage(functionality, exit_code=0):
    """Print a usage message and exit with 'exit_code'."""

    print """Usage: dak COMMAND [...]
Run DAK commands.  (Will also work if invoked as COMMAND.)

Available commands:"""
    for (command, description) in functionality:
        print "  %-23s %s" % (command, description)
    sys.exit(exit_code)

################################################################################

def main():
    """Launch dak functionality."""


    try:
        logger = Logger('dak top-level', print_starting=False)
    except CantOpenError:
        logger = None

    functionality = init()
    modules = [ command for (command, _) in functionality ]

    if len(sys.argv) == 0:
        daklib.utils.fubar("err, argc == 0? how is that possible?")
    elif (len(sys.argv) == 1
          or (len(sys.argv) == 2 and
              (sys.argv[1] == "--help" or sys.argv[1] == "-h"))):
        usage(functionality)

    # First see if we were invoked with/as the name of a module
    cmdname = sys.argv[0]
    cmdname = cmdname[cmdname.rfind("/")+1:]
    if cmdname in modules:
        pass
    # Otherwise the argument is the module
    else:
        cmdname = sys.argv[1]
        sys.argv = [sys.argv[0] + " " + sys.argv[1]] + sys.argv[2:]
        if cmdname not in modules:
            match = []
            for name in modules:
                if name.startswith(cmdname):
                    match.append(name)
            if len(match) == 1:
                cmdname = match[0]
            elif len(match) > 1:
                daklib.utils.warn("ambiguous command '%s' - could be %s" \
                           % (cmdname, ", ".join(match)))
                usage(functionality, 1)
            else:
                daklib.utils.warn("unknown command '%s'" % (cmdname))
                usage(functionality, 1)

    # Invoke the module
    module = __import__(cmdname.replace("-","_"))

    try:
        module.main()
    except KeyboardInterrupt:
        msg = 'KeyboardInterrupt caught; exiting'
        print msg
        if logger:
            logger.log([msg])
        sys.exit(1)
    except SystemExit:
        pass
    except:
        if logger:
            for line in traceback.format_exc().split('\n')[:-1]:
                logger.log(['exception', line])
        raise

################################################################################

if __name__ == "__main__":
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    main()
