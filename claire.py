#!/usr/bin/env python

# 'Fix' stable to make debian-cd and dpkg -BORGiE users happy
# Copyright (C) 2000  James Troup <james@nocrew.org>
# $Id: claire.py,v 1.3 2001-01-25 07:27:08 troup Exp $

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

import os, pg, re, string, sys
import utils, db_access
import apt_pkg;

################################################################################

re_strip_section_prefix = re.compile(r'.*/');

Cnf = None;
projectB = None;

################################################################################

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

def fix_component_section (component, section):
    if component == "":
        (None, component) = utils.extract_component_from_section(section);

    # FIXME: ugly hacks to work around override brain damage
    section = re_strip_section_prefix.sub('', section);
    section = string.replace(string.lower(section), 'non-us', '');
    if section == "main" or section == "contrib" or section == "non-free":
        section = '';
    if section != '':
        section = section + '/';

    return (component, section);

################################################################################

def find_dislocated_stable(Cnf, projectB):
    dislocated_files = {}

    # Source
    q = projectB.query("""
SELECT DISTINCT ON (f.id) c.name, sec.section, l.path, f.filename, f.id
    FROM component c, override o, section sec, source s, files f, location l,
         dsc_files df, suite su, src_associations sa, files f2, location l2
    WHERE su.suite_name = 'stable' AND sa.suite = su.id AND sa.source = s.id
      AND f2.id = s.file AND f2.location = l2.id AND df.source = s.id
      AND f.id = df.file AND f.location = l.id AND o.package = s.source
      AND sec.id = o.section AND NOT (f.filename ~ '^potato/')
      AND l.component = c.id
UNION SELECT DISTINCT ON (f.id) null, sec.section, l.path, f.filename, f.id
    FROM component c, override o, section sec, source s, files f, location l,
         dsc_files df, suite su, src_associations sa, files f2, location l2
    WHERE su.suite_name = 'stable' AND sa.suite = su.id AND sa.source = s.id
      AND f2.id = s.file AND f2.location = l2.id AND df.source = s.id
      AND f.id = df.file AND f.location = l.id AND o.package = s.source
      AND sec.id = o.section AND NOT (f.filename ~ '^potato/')
      AND NOT EXISTS (SELECT l.path FROM location l WHERE l.component IS NOT NULL AND f.location = l.id);
""");
    for i in q.getresult():
        src = i[2]+i[3]
        (component, section) = fix_component_section(i[0], i[1]);
        dest = "%sdists/stable/%s/source/%s%s" % (Cnf["Dir::RootDir"], component, section, os.path.basename(i[3]));
        src = clean_symlink(src, dest, Cnf["Dir::RootDir"]);
        if not os.path.exists(dest):
            if Cnf.Find("Claire::Options::Verbose"):
                print src+' -> '+dest
            os.symlink(src, dest);
        dislocated_files[i[4]] = dest;

    #return dislocated_files;

    # TODO later when there's something to test it with!
    # Binary
    q = projectB.query("""
SELECT DISTINCT ON (f.id) c.name, a.arch_string, sec.section, b.package,
                          b.version, l.path, f.filename, f.id
    FROM architecture a, bin_associations ba, binaries b, component c, files f,
         location l, override o, section sec, suite su
    WHERE su.suite_name = 'stable' AND ba.suite = su.id AND ba.bin = b.id
      AND f.id = b.file AND f.location = l.id AND o.package = b.package
      AND sec.id = o.section AND NOT (f.filename ~ '^potato/')
      AND b.architecture = a.id AND l.component = c.id
UNION SELECT DISTINCT ON (f.id) null, a.arch_string, sec.section, b.package,
                          b.version, l.path, f.filename, f.id
    FROM architecture a, bin_associations ba, binaries b, component c, files f,
         location l, override o, section sec, suite su
    WHERE su.suite_name = 'stable' AND ba.suite = su.id AND ba.bin = b.id
      AND f.id = b.file AND f.location = l.id AND o.package = b.package
      AND sec.id = o.section AND NOT (f.filename ~ '^potato/')
      AND b.architecture = a.id AND NOT EXISTS
        (SELECT l.path FROM location l WHERE l.component IS NOT NULL AND f.location = l.id);
""");
    for i in q.getresult():
        (component, section) = fix_component_section(i[0], i[2]);
        architecture = i[1];
        package = i[3]
        version = utils.re_no_epoch.sub('', i[4]);
        src = i[5]+i[6]
       
        dest = "%sdists/stable/%s/binary-%s/%s%s_%s.deb" % (Cnf["Dir::RootDir"], component, architecture, section, package, version);
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

