#! /usr/bin/env python3

"""
Writes out a rfc2822-formatted list of sections and their descriptions.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Peter Palfrader <peter@palfrader.org>
@copyright: 2020  Joerg Jaspert <joerg@debian.org>
@license: GNU General Public License version 2 or later
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


################################################################################

import sys

from daklib.dbconn import *

################################################################################


def write_sections(session):
    query_sections = """
    SELECT
      section,
      description,
      longdesc
    FROM section
    ORDER BY section
    """

    for row in session.execute(query_sections).fetchall():
        (section, description, longdesc) = row
        print("Section: {0}".format(section))
        print("Description: {0}".format(description))
        print("Longdesc: {0}".format(longdesc))
        print()

################################################################################


def usage():
    print("usage: dak write-sections")
    sys.exit(0)

################################################################################


def main():
    if len(sys.argv) != 1:
        usage()

    session = DBConn().session()
    write_sections(session)

#########################################################################################


if __name__ == '__main__':
    main()

# vim:set et:
# vim:set ts=4:
# vim:set shiftwidth=4:
