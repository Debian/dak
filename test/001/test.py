#!/usr/bin/env python

# Check utils.parse_changes()'s .dsc file validation
# Copyright (C) 2000  James Troup <james@nocrew.org>
# $Id: test.py,v 1.1 2001-01-28 09:06:44 troup Exp $

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
    # Valid .dsc
    utils.parse_changes('1.dsc',1);

    # Missing blank line before signature body
    try:
        utils.parse_changes('2.dsc',1);
    except utils.invalid_dsc_format_exc, line:
        if line != 14:
            fail("Incorrect line number ('%s') for test #2." % (line));
    else:
        fail("Test #2 wasn't recognised as invalid.");

    # Missing blank line after signature header
    try:
        utils.parse_changes('3.dsc',1);
    except utils.invalid_dsc_format_exc, line:
        if line != 14:
            fail("Incorrect line number ('%s') for test #3." % (line));
    else:
        fail("Test #3 wasn't recognised as invalid.");

    # No blank lines at all
    try:
        utils.parse_changes('4.dsc',1);
    except utils.invalid_dsc_format_exc, line:
        if line != 19:
            fail("Incorrect line number ('%s') for test #4." % (line));
    else:
        fail("Test #4 wasn't recognised as invalid.");

    # Extra blank line before signature body
    try:
        utils.parse_changes('5.dsc',1);
    except utils.invalid_dsc_format_exc, line:
        if line != 15:
            fail("Incorrect line number ('%s') for test #5." % (line));
    else:
        fail("Test #5 wasn't recognised as invalid.");

    # Extra blank line after signature header
    try:
        utils.parse_changes('6.dsc',1);
    except utils.invalid_dsc_format_exc, line:
        if line != 5:
            fail("Incorrect line number ('%s') for test #6." % (line));
    else:
        fail("Test #6 wasn't recognised as invalid.");

    # Valid .dsc ; ignoring errors
    utils.parse_changes('1.dsc', 0);

    # Invalid .dsc ; ignoring errors
    utils.parse_changes('2.dsc', 0);

################################################################################

if __name__ == '__main__':
    main()
