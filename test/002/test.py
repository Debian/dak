#!/usr/bin/env python

# Check utils.parse_changes()'s for handling empty files
# Copyright (C) 2000  James Troup <james@nocrew.org>
# $Id: test.py,v 1.1 2001-03-02 02:31:07 troup Exp $

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

import os, sys

sys.path.append(os.path.abspath('../../'));

import utils

################################################################################

def fail(message):
    sys.stderr.write("%s\n" % (message));
    sys.exit(1);
    
################################################################################

def main ():
    # Empty .changes file; should raise a 'parse error' exception.
    try:
        utils.parse_changes('empty.changes', 0)
    except utils.changes_parse_error_exc, line:
        if line != "[Empty changes file]":
            fail("Returned exception with unexcpected error message `%s'." % (line));
    else:
        fail("Didn't raise a 'parse error' exception for a zero-length .changes file.");

################################################################################

if __name__ == '__main__':
    main()
