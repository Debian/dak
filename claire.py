#!/usr/bin/env python

# 'Fix' stable to make debian-cd and dpkg -BORGiE users happy
# Copyright (C) 2000, 2001, 2002  James Troup <james@nocrew.org>
# $Id: claire.py,v 1.18 2002-10-16 02:47:32 troup Exp $

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

# "Look around... leaves are brown... and the sky's a hazy shade of winter,
#  Look around... leaves are brown... there's a patch of snow on the ground."
#                                         -- Simon & Garfunkel / 'A Hazy Shade'

################################################################################

import os, pg, re, sys;
import utils, db_access;
import apt_pkg;

################################################################################

re_strip_section_prefix = re.compile(r'.*/');

Cnf = None;
projectB = None;

################################################################################

def usage (exit_code=0):
    print """Usage: claire [OPTIONS]
Create compatibility symlinks from legacy locations to the pool.

  -v, --verbose              explain what is being done
  -h, --help                 show this help and exit"""

    sys.exit(exit_code)

################################################################################

# Relativize an absolute symlink from 'src' -> 'dest' relative to 'root'.
# Returns fixed 'src'
def clean_symlink (src, dest, root):
    src = src.replace(root, '', 1);
    dest = dest.replace(root, '', 1);
    dest = os.path.dirname(dest);
    new_src = '../' * len(dest.split('/'));
    return new_src + src;

################################################################################

def fix_component_section (component, section):
    if component == "":
        component = utils.extract_component_from_section(section)[1];

    # FIXME: ugly hacks to work around override brain damage
    section = re_strip_section_prefix.sub('', section);
    section = section.lower().replace('non-us', '');
    if section == "main" or section == "contrib" or section == "non-free":
        section = '';
    if section != '':
        section += '/';

    return (component, section);

################################################################################

def find_dislocated_stable(Cnf, projectB):
    dislocated_files = {}

    codename = Cnf["Suite::Stable::Codename"];

    # Source
    q = projectB.query("""
SELECT DISTINCT ON (f.id) c.name, sec.section, l.path, f.filename, f.id
    FROM component c, override o, section sec, source s, files f, location l,
         dsc_files df, suite su, src_associations sa, files f2, location l2
    WHERE su.suite_name = 'stable' AND sa.suite = su.id AND sa.source = s.id
      AND f2.id = s.file AND f2.location = l2.id AND df.source = s.id
      AND f.id = df.file AND f.location = l.id AND o.package = s.source
      AND sec.id = o.section AND NOT (f.filename ~ '^%s/')
      AND l.component = c.id AND o.suite = su.id
""" % (codename));
# Only needed if you have files in legacy-mixed locations
#  UNION SELECT DISTINCT ON (f.id) null, sec.section, l.path, f.filename, f.id
#      FROM component c, override o, section sec, source s, files f, location l,
#           dsc_files df, suite su, src_associations sa, files f2, location l2
#      WHERE su.suite_name = 'stable' AND sa.suite = su.id AND sa.source = s.id
#        AND f2.id = s.file AND f2.location = l2.id AND df.source = s.id
#        AND f.id = df.file AND f.location = l.id AND o.package = s.source
#        AND sec.id = o.section AND NOT (f.filename ~ '^%s/') AND o.suite = su.id
#        AND NOT EXISTS (SELECT l.path FROM location l WHERE l.component IS NOT NULL AND f.location = l.id);
    for i in q.getresult():
        (component, section) = fix_component_section(i[0], i[1]);
        if Cnf.FindB("Dinstall::LegacyStableHasNoSections"):
            section="";
        dest = "%sdists/%s/%s/source/%s%s" % (Cnf["Dir::Root"], codename, component, section, os.path.basename(i[3]));
        if not os.path.exists(dest):
	    src = i[2]+i[3];
	    src = clean_symlink(src, dest, Cnf["Dir::Root"]);
            if Cnf.Find("Claire::Options::Verbose"):
                print src+' -> '+dest
            os.symlink(src, dest);
        dislocated_files[i[4]] = dest;

    # Binary
    architectures = filter(utils.real_arch, Cnf.ValueList("Suite::Stable::Architectures"));
    q = projectB.query("""
SELECT DISTINCT ON (f.id) c.name, a.arch_string, sec.section, b.package,
                          b.version, l.path, f.filename, f.id
    FROM architecture a, bin_associations ba, binaries b, component c, files f,
         location l, override o, section sec, suite su
    WHERE su.suite_name = 'stable' AND ba.suite = su.id AND ba.bin = b.id
      AND f.id = b.file AND f.location = l.id AND o.package = b.package
      AND sec.id = o.section AND NOT (f.filename ~ '^%s/')
      AND b.architecture = a.id AND l.component = c.id AND o.suite = su.id""" %
                       (codename));
# Only needed if you have files in legacy-mixed locations
#  UNION SELECT DISTINCT ON (f.id) null, a.arch_string, sec.section, b.package,
#                            b.version, l.path, f.filename, f.id
#      FROM architecture a, bin_associations ba, binaries b, component c, files f,
#           location l, override o, section sec, suite su
#      WHERE su.suite_name = 'stable' AND ba.suite = su.id AND ba.bin = b.id
#        AND f.id = b.file AND f.location = l.id AND o.package = b.package
#        AND sec.id = o.section AND NOT (f.filename ~ '^%s/')
#        AND b.architecture = a.id AND o.suite = su.id AND NOT EXISTS
#          (SELECT l.path FROM location l WHERE l.component IS NOT NULL AND f.location = l.id);
    for i in q.getresult():
        (component, section) = fix_component_section(i[0], i[2]);
        if Cnf.FindB("Dinstall::LegacyStableHasNoSections"):
            section="";
        architecture = i[1];
        package = i[3];
        version = utils.re_no_epoch.sub('', i[4]);
        src = i[5]+i[6];

        dest = "%sdists/%s/%s/binary-%s/%s%s_%s.deb" % (Cnf["Dir::Root"], codename, component, architecture, section, package, version);
        src = clean_symlink(src, dest, Cnf["Dir::Root"]);
        if not os.path.exists(dest):
            if Cnf.Find("Claire::Options::Verbose"):
                print src+' -> '+dest;
            os.symlink(src, dest);
        dislocated_files[i[7]] = dest;
        # Add per-arch symlinks for arch: all debs
        if architecture == "all":
            for arch in architectures:
                dest = "%sdists/%s/%s/binary-%s/%s%s_%s.deb" % (Cnf["Dir::Root"], codename, component, arch, section, package, version);
                if not os.path.exists(dest):
                    if Cnf.Find("Claire::Options::Verbose"):
                        print src+' -> '+dest
                    os.symlink(src, dest);

    return dislocated_files

################################################################################

def main ():
    global Cnf, projectB;

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Claire::Options::Help"),
                 ('v',"verbose","Claire::Options::Verbose")];
    for i in ["help", "verbose" ]:
	if not Cnf.has_key("Claire::Options::%s" % (i)):
	    Cnf["Claire::Options::%s" % (i)] = "";

    apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv);
    Options = Cnf.SubTree("Claire::Options")

    if Options["Help"]:
	usage();

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]));

    db_access.init(Cnf, projectB);

    find_dislocated_stable(Cnf, projectB);

#######################################################################################

if __name__ == '__main__':
    main();

