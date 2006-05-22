#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Test utils.fix_maintainer()
# Copyright (C) 2004, 2006  James Troup <james@nocrew.org>

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

sys.path.append(os.path.abspath('../../'))

import utils

################################################################################

def fail(message):
    sys.stderr.write("%s\n" % (message))
    sys.exit(1)

################################################################################

def check_valid(s, xa, xb, xc, xd):
    (a, b, c, d) = utils.fix_maintainer(s)
    if a != xa:
        fail("rfc822_maint: %s (returned) != %s (expected [From: '%s']" % (a, xa, s))
    if b != xb:
        fail("rfc2047_maint: %s (returned) != %s (expected [From: '%s']" % (b, xb, s))
    if c != xc:
        fail("name: %s (returned) != %s (expected [From: '%s']" % (c, xc, s))
    if d != xd:
        fail("email: %s (returned) != %s (expected [From: '%s']" % (d, xd, s))

def check_invalid(s):
    try:
        utils.fix_maintainer(s)
        fail("%s was parsed successfully but is expected to be invalid." % (s))
    except utils.ParseMaintError, unused:
        pass

def main ():
    # Check Valid UTF-8 maintainer field
    s = "Noèl Köthe <noel@debian.org>"
    xa = "Noèl Köthe <noel@debian.org>"
    xb = "=?utf-8?b?Tm/DqGwgS8O2dGhl?= <noel@debian.org>"
    xc = "Noèl Köthe"
    xd = "noel@debian.org"
    check_valid(s, xa, xb, xc, xd)

    # Check valid ISO-8859-1 maintainer field
    s = "No�l K�the <noel@debian.org>"
    xa = "Noèl Köthe <noel@debian.org>"
    xb = "=?iso-8859-1?q?No=E8l_K=F6the?= <noel@debian.org>"
    xc = "Noèl Köthe"
    xd = "noel@debian.org"
    check_valid(s, xa, xb, xc, xd)

    # Check valid ASCII maintainer field
    s = "James Troup <james@nocrew.org>"
    xa = "James Troup <james@nocrew.org>"
    xb = "James Troup <james@nocrew.org>"
    xc = "James Troup"
    xd = "james@nocrew.org"
    check_valid(s, xa, xb, xc, xd)

    # Check "Debian vs RFC822" fixup of names with '.' or ',' in them
    s = "James J. Troup <james@nocrew.org>"
    xa = "james@nocrew.org (James J. Troup)"
    xb = "james@nocrew.org (James J. Troup)"
    xc = "James J. Troup"
    xd = "james@nocrew.org"
    check_valid(s, xa, xb, xc, xd)
    s = "James J, Troup <james@nocrew.org>"
    xa = "james@nocrew.org (James J, Troup)"
    xb = "james@nocrew.org (James J, Troup)"
    xc = "James J, Troup"
    xd = "james@nocrew.org"
    check_valid(s, xa, xb, xc, xd)

    # Check just-email form
    s = "james@nocrew.org"
    xa = " <james@nocrew.org>"
    xb = " <james@nocrew.org>"
    xc = ""
    xd = "james@nocrew.org"
    check_valid(s, xa, xb, xc, xd)

    # Check bracketed just-email form
    s = "<james@nocrew.org>"
    xa = " <james@nocrew.org>"
    xb = " <james@nocrew.org>"
    xc = ""
    xd = "james@nocrew.org"
    check_valid(s, xa, xb, xc, xd)

    # Check Krazy quoted-string local part email address
    s = "Cris van Pelt <\"Cris van Pelt\"@tribe.eu.org>"
    xa = "Cris van Pelt <\"Cris van Pelt\"@tribe.eu.org>"
    xb = "Cris van Pelt <\"Cris van Pelt\"@tribe.eu.org>"
    xc = "Cris van Pelt"
    xd = "\"Cris van Pelt\"@tribe.eu.org"
    check_valid(s, xa, xb, xc, xd)

    # Check empty string
    s = xa = xb = xc = xd = ""
    check_valid(s, xa, xb, xc, xd)

    # Check for missing email address
    check_invalid("James Troup")
    # Check for invalid email address
    check_invalid("James Troup <james@nocrew.org")

################################################################################

if __name__ == '__main__':
    main()
