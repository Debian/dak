#!/usr/bin/env python

# 'Fix' stable to make debian-cd and dpkg -BORGiE users happy
# Copyright (C) 2000  James Troup <james@nocrew.org>
# $Id: claire.py,v 1.1 2000-12-05 04:27:48 troup Exp $

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

# "Look around... leaves are brown... and the sky's a hazy shade of winter,
#  Look around... leaves are brown... there's a patch of snow on the ground."
#                                         -- Simon & Garfunkel / 'A Hazy Shade'

################################################################################

import pg, sys, os, string
import utils, db_access
import apt_pkg;

################################################################################

Cnf = None;
projectB = None;

# Relativize an absolute symlink from 'src' -> 'dest' relative to 'root'.
# Returns fixed 'src'
def clean_symlink (src, dest, root):
    src = string.replace(src, root, '', 1);
    dest = string.replace(dest, root, '', 1);
    dest = os.path.dirname(dest);
    new_src = '';
    for i in xrange(len(string.split(dest, '/'))):
        new_src = new_src + '../';
    return new_src + src

################################################################################

def find_dislocated_stable(Cnf, projectB):
    dislocated_files = {}

    # Source
    q = projectB.query("SELECT su.suite_name, c.name, s.id FROM suite su, src_associations sa, source s, files f, component c, location l WHERE su.suite_name = 'stable' AND sa.suite = su.id AND sa.source = s.id AND f.id = s.file AND f.location = l.id AND (l.component = c.id OR (l.component = NULL AND c.name = 'non-US/main')) AND NOT (f.filename ~ '^potato/');")
    for i in q.getresult():
        q = projectB.query("SELECT l.path, f.filename, f.id FROM source s, files f, location l, dsc_files df WHERE s.id = %d AND df.source = %d AND f.id = df.file AND f.location = l.id AND NOT (f.filename ~ '^potato/')" % (i[2], i[2]));
        for j in q.getresult():
            src = j[0]+j[1]
            dest = Cnf["Dir::RootDir"]+'dists/'+i[0]+'/'+i[1]+'/source/'+os.path.basename(j[1]);
            src = clean_symlink(src, dest, Cnf["Dir::RootDir"]);
            if not os.path.exists(dest):
                if Cnf.Find("Claire::Options::Verbose"):
                    print src+' -> '+dest
                os.symlink(src, dest);
            dislocated_files[j[2]] = dest;

    # Binary
    q = projectB.query("SELECT su.suite_name, c.name, a.arch_string, b.package, b.version, l.path, f.filename, f.id FROM suite su, bin_associations ba, binaries b, files f, component c, architecture a, location l WHERE ba.suite = su.id AND su.suite_name = 'stable' AND ba.bin = b.id AND f.id = b.file AND f.location = l.id AND (l.component = c.id OR (l.component = NULL and c.name = 'non-US/main')) AND b.architecture = a.id AND NOT (f.filename ~ '^potato/');");
    for i in q.getresult():
        src = i[5]+i[6]
        dest = Cnf["Dir::RootDir"]+'dists/'+i[0]+'/'+i[1]+'/binary-'+i[2]+'/'+i[3]+'_'+utils.re_no_epoch.sub('', i[4])+'.deb'
        src = clean_symlink(src, dest, Cnf["Dir::RootDir"]);
        if not os.path.exists(dest):
            if Cnf.Find("Claire::Options::Verbose"):
                print src+' -> '+dest
            os.symlink(src, dest);
        dislocated_files[i[7]] = dest;

    return dislocated_files

################################################################################

def main ():
    global Cnf, projectB;

    apt_pkg.init();
    
    Cnf = apt_pkg.newConfiguration();
    apt_pkg.ReadConfigFileISC(Cnf,utils.which_conf_file());

    Arguments = [('d',"debug","Claire::Options::Debug", "IntVal"),
                 ('h',"help","Claire::Options::Help"),
                 ('v',"verbose","Claire::Options::Verbose"),
                 ('V',"version","Claire::Options::Version")];

    apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv);

    projectB = pg.connect('projectb', 'localhost');

    db_access.init(Cnf, projectB);

    find_dislocated_stable(Cnf, projectB);

#######################################################################################

if __name__ == '__main__':
    main()

