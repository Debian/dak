#!/usr/bin/env python

# Check utils.parse_changes()'s for handling of multi-line fields
# Copyright (C) 2004  James Troup <james@nocrew.org>
# $Id: test.py,v 1.2 2004-01-21 03:48:58 troup Exp $

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

# Check util.parse_changes() correctly ignores data outside the signed area

################################################################################

import os, sys

sys.path.append(os.path.abspath('../../'));

import utils

################################################################################

def fail(message):
    sys.stderr.write("%s\n" % (message));
    sys.exit(1);

################################################################################

def main ():
    for file in [ "valid", "bogus-pre", "bogus-post" ]:
        for strict_whitespace in [ 0, 1 ]:
            try:
                changes = utils.parse_changes("%s.changes" % (file), strict_whitespace)
            except utils.changes_parse_error_exc, line:
                fail("%s[%s]: parse_changes() returned an exception with error message `%s'." % (file, strict_whitespace, line));
            oh_dear = changes.get("you");
            if oh_dear:
                fail("%s[%s]: parsed and accepted unsigned data!" % (file, strict_whitespace));

################################################################################

if __name__ == '__main__':
    main()
