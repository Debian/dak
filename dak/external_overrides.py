#!/usr/bin/python

"""
Modify external overrides.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011  Ansgar Burchardt <ansgar@debian.org>
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

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils, daklog

import apt_pkg
import sys

def usage():
    print """Usage: dak external-overrides COMMAND
Modify external overrides.

  -h, --help                    show this help and exit.
  -f, --force                   allow processing of untouchable suites.

Commands can use a long or abbreviated form:

    import SUITE COMPONENT KEY  import external overrides for KEY
    i SUITE COMPONENT KEY       NOTE: This will replace existing overrides.

    copy FROM TO                copy external overrides from suite FROM to TO
                                NOTE: Needs --force for untouchable TO

For the 'import' command, external overrides are read from standard input and
should be given as lines of the form 'PACKAGE KEY VALUE'.
"""
    sys.exit()

#############################################################################

class ExternalOverrideReader(object):
    """
    Parses an external override file
    """
    def __init__(self, fh):
        self.fh = fh
        self.package = None
        self.key = None
        self.value = []

    def _flush(self):
        """
        Return the parsed line that is being built and start parsing a new line
        """
        res = self.package, self.key, "\n".join(self.value)
        self.package = self.key = None
        self.value = []
        return res

    def __iter__(self):
        """
        returns a (package, key, value) tuple for every entry in the external
        override file
        """
        for line in self.fh:
            if not line: continue
            if line[0] in (" ", "\t"):
                # Continuation line
                self.value.append(line.rstrip())
            else:
                if self.package is not None:
                    yield self._flush()

                # New line
                (self.package, self.key, value) = line.rstrip().split(None, 2)
                self.value = [value]

        if self.package is not None:
            yield self._flush()

#############################################################################

def external_overrides_copy(from_suite_name, to_suite_name, force = False):
    session = DBConn().session()

    from_suite = get_suite(from_suite_name, session)
    to_suite = get_suite(to_suite_name, session)

    if from_suite is None:
        print "E: source %s not found." % from_suite_name
        session.rollback()
        return False
    if to_suite is None:
        print "E: target %s not found." % to_suite_name
        session.rollback()
        return False

    if not force and to_suite.untouchable:
        print "E: refusing to touch untouchable suite %s (not forced)." % to_suite_name
        session.rollback()
        return False

    session.query(ExternalOverride).filter_by(suite=to_suite).delete()
    session.execute("""
    INSERT INTO external_overrides (suite, component, package, key, value)
      SELECT :to_suite, component, package, key, value FROM external_overrides WHERE suite = :from_suite
    """, { 'from_suite': from_suite.suite_id, 'to_suite': to_suite.suite_id })

    session.commit()

def external_overrides_import(suite_name, component_name, key, file, force = False):
    session = DBConn().session()

    suite = get_suite(suite_name, session)
    component = get_component(component_name, session)

    if not force and suite.untouchable:
        print "E: refusing to touch untouchable suite %s (not forced)." % suite_name
        session.rollback()
        return False

    session.query(ExternalOverride).filter_by(suite=suite,component=component,key=key).delete()

    for package, key, value in ExternalOverrideReader(file):
        eo = ExternalOverride()
        eo.suite = suite
        eo.component = component
        eo.package = package
        eo.key = key
        eo.value = value
        session.add(eo)

    session.commit()

#############################################################################

def main():
    cnf = Config()

    Arguments = [('h',"help","External-Overrides::Options::Help"),
                 ('f','force','External-Overrides::Options::Force')]

    args = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    try:
        Options = cnf.subtree("External-Overrides::Options")
    except KeyError:
        Options = {}

    if Options.has_key("Help"):
        usage()

    force = False
    if Options.has_key("Force") and Options["Force"]:
        force = True

    logger = daklog.Logger('external-overrides')

    command = args[0]
    if command in ('import', 'i'):
        external_overrides_import(args[1], args[2], args[3], sys.stdin, force)
    elif command in ('copy', 'c'):
        external_overrides_copy(args[1], args[2], force)
    else:
        print "E: Unknown commands."

if __name__ == '__main__':
    main()
