#!/usr/bin/env python

# Check utils.extract_component_from_section()
# Copyright (C) 2000  James Troup <james@nocrew.org>
# $Id: test.py,v 1.1 2001-06-10 16:35:04 troup Exp $

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

import os, string, sys

sys.path.append(os.path.abspath('../../'));

import utils

################################################################################

def fail(message):
    sys.stderr.write("%s\n" % (message));
    sys.exit(1);
    
################################################################################

# prefix: non-US
# component: main, contrib, non-free
# section: games, admin, libs, [...]

# [1] Order is as above.
# [2] Prefix is optional for the default archive, but mandatory when
#     uploads are going anywhere else.
# [3] Default component is main and may be omitted.
# [4] Section is optional.
# [5] Prefix is case insensitive
# [6] Everything else is case sensitive.

def test(input, output):
    result = utils.extract_component_from_section(input);
    if result != output:
        fail ("%s -> %s [should have been %s]" % (input, repr(result), repr(output)));

def main ():
    # Err, whoops?  should probably be "utils", "main"...
    input = "main/utils"; output = ("main/utils", "main");
    test (input, output);


    # Validate #3
    input = "utils"; output = ("utils", "main");
    test (input, output);

    input = "non-free/libs"; output = ("non-free/libs", "non-free");
    test (input, output);

    input = "contrib/net"; output = ("contrib/net", "contrib");
    test (input, output);


    # Validate #3 with a prefix
    input = "non-US"; output = ("non-US", "non-US/main");
    test (input, output);


    # Validate #4
    input = "main"; output = ("main", "main");
    test (input, output);

    input = "contrib"; output = ("contrib", "contrib");
    test (input, output);

    input = "non-free"; output = ("non-free", "non-free");
    test (input, output);


    # Validate #4 with a prefix
    input = "non-US/main"; output = ("non-US/main", "non-US/main");
    test (input, output);

    input = "non-US/contrib"; output = ("non-US/contrib", "non-US/contrib");
    test (input, output);

    input = "non-US/non-free"; output = ("non-US/non-free", "non-US/non-free");
    test (input, output);


    # Validate #5
    input = "non-us"; output = ("non-us", "non-US/main");
    test (input, output);

    input = "non-us/contrib"; output = ("non-us/contrib", "non-US/contrib");
    test (input, output);


    # Validate #6 (section)
    input = "utIls"; output = ("utIls", "main");
    test (input, output);

################################################################################

if __name__ == '__main__':
    main()
