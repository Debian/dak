#!/usr/bin/env python

# Fix for bug in katie where dsc_files was initialized from changes and not dsc
# Copyright (C) 2000  James Troup <james@nocrew.org>
# $Id: fix.b,v 1.1 2000-12-19 17:23:03 troup Exp $

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

# "Look around... leaves are brown... and the sky is hazy shade of winter,
#  Look around... leaves are brown... there's a patch of snow on the ground."
#                                         -- Simon & Garfunkel / 'A Hazy Shade'

################################################################################

import pg, sys, os, string, stat, re
import utils, db_access
import apt_pkg;

################################################################################

Cnf = None;
projectB = None;

bad_arch = re.compile(r'/binary-(hppa|mips|mipsel|sh|hurd-i386)/');

################################################################################

def main ():
    global Cnf, projectB;

    apt_pkg.init();
    
    Cnf = apt_pkg.newConfiguration();
    apt_pkg.ReadConfigFileISC(Cnf,utils.which_conf_file());

    Arguments = [('d',"debug","Claire::Options::Debug", "IntVal"),
                 ('h',"help","Claire::Options::Help"),
                 ('v',"version","Claire::Options::Version")];

    apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv);

    projectB = pg.connect('projectb', 'localhost');

    db_access.init(Cnf, projectB);

    file = utils.open_file('x', 'r');
    for line in file.readlines():
        if string.find(line, '/binary-') != -1:
            if bad_arch.search(line) != None:
                new_line = string.replace(line, 'woody/', 'sid/');
                if new_line == line:
                    print line;
                    sys.exit(2);
                line = new_line;
        sys.stdout.write(line);

#######################################################################################

if __name__ == '__main__':
    main()

