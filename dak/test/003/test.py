#!/usr/bin/env python

# Check utils.parse_changes()'s for handling of multi-line fields
# Copyright (C) 2000, 2006  James Troup <james@nocrew.org>

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

# The deal here is that for the first 6 months of dak's
# implementation it has been misparsing multi-line fields in .changes
# files; specifically multi-line fields where there _is_ data on the
# first line. So, for example:

# Foo: bar baz
#  bat bant

# Became "foo: bar bazbat bant" rather than "foo: bar baz\nbat bant"

################################################################################

import os, sys

sys.path.append(os.path.abspath('../../'))

import utils

################################################################################

def fail(message):
    sys.stderr.write("%s\n" % (message))
    sys.exit(1)

################################################################################

def main ():
    # Valid .changes file with a multi-line Binary: field
    try:
        changes = utils.parse_changes('krb5_1.2.2-4_m68k.changes', 0)
    except utils.changes_parse_error_exc, line:
        fail("parse_changes() returned an exception with error message `%s'." % (line))

    o = changes.get("binary", "")
    if o != "":
        del changes["binary"]
    changes["binary"] = {}
    for j in o.split():
        changes["binary"][j] = 1

    if not changes["binary"].has_key("krb5-ftpd"):
        fail("parse_changes() is broken; 'krb5-ftpd' is not in the Binary: dictionary.")

################################################################################

if __name__ == '__main__':
    main()
