#!/usr/bin/env python

# Script to automate some parts of checking NEW packages
# Copyright (C) 2000, 2001, 2002  James Troup <james@nocrew.org>
# $Id: fernanda.py,v 1.3 2002-05-18 23:54:51 troup Exp $

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

# <Omnic> elmo wrote docs?!!?!?!?!?!?!
# <aj> as if he wasn't scary enough before!!
# * aj imagines a little red furry toy sitting hunched over a computer
#   tapping furiously and giggling to himself
# <aj> eventually he stops, and his heads slowly spins around and you
#      see this really evil grin and then he sees you, and picks up a
#      knife from beside the keyboard and throws it at you, and as you
#      breathe your last breath, he starts giggling again
# <aj> but i should be telling this to my psychiatrist, not you guys,
#      right? :)

################################################################################

import errno, os, re, sys
import utils
import apt_pkg

################################################################################

Cnf = None;
projectB = None;

re_package = re.compile(r"^(.+?)_.*");
re_doc_directory = re.compile(r".*/doc/([^/]*).*");

################################################################################

def usage (exit_code=0):
    print """Usage: fernanda [PACKAGE]...
Check NEW package(s).

  -h, --help                 show this help and exit

PACKAGE can be a .changes, .dsc, .deb or .udeb filename."""

    sys.exit(exit_code)

################################################################################

def do_command (command, filename):
    o = os.popen("%s %s" % (command, filename));
    print o.read();

def print_copyright (deb_filename):
    package = re_package.sub(r'\1', deb_filename);
    o = os.popen("ar p %s data.tar.gz | tar tzvf - | egrep 'usr(/share)?/doc/[^/]*/copyright' | awk '{ print $6 }' | head -n 1" % (deb_filename));
    copyright = o.read()[:-1];

    if copyright == "":
        print "WARNING: No copyright found, please check package manually."
        return;

    doc_directory = re_doc_directory.sub(r'\1', copyright);
    if package != doc_directory:
        print "WARNING: wrong doc directory (expected %s, got %s)." % (package, doc_directory);
        return;

    o = os.popen("ar p %s data.tar.gz | tar xzOf - %s" % (deb_filename, copyright));
    print o.read();

def check_dsc (dsc_filename):
    print "---- .dsc file for %s ----" % (dsc_filename);
    dsc_file = utils.open_file(dsc_filename);
    for line in dsc_file.readlines():
        print line[:-1];
    print;

def check_deb (deb_filename):
    filename = os.path.basename(deb_filename);

    if filename[-5:] == ".udeb":
	is_a_udeb = 1;
    else:
	is_a_udeb = 0;

    print "---- control file for %s ----" % (filename);
    do_command ("dpkg -I", deb_filename);

    if is_a_udeb:
	print "---- skipping lintian check for µdeb ----";
	print ;
    else:
	print "---- lintian check for %s ----" % (filename);
        do_command ("lintian", deb_filename);

    print "---- contents of %s ----" % (filename);
    do_command ("dpkg -c", deb_filename);

    if is_a_udeb:
	print "---- skipping copyright for µdeb ----";
    else:
	print "---- copyright of %s ----" % (filename);
        print_copyright(deb_filename);

    print "---- file listing of %s ----" % (filename);
    do_command ("ls -l", deb_filename);

def display_changes (changes_filename):
    print "---- .changes file for %s ----" % (changes_filename);
    file = utils.open_file (changes_filename);
    for line in file.readlines():
	print line[:-1]
    print ;
    file.close();

def check_changes (changes_filename):
    display_changes(changes_filename);

    changes = utils.parse_changes (changes_filename);
    files = utils.build_file_list(changes);
    for file in files.keys():
	if file[-4:] == ".deb" or file[-5:] == ".udeb":
	    check_deb(file);
        if file[-4:] == ".dsc":
            check_dsc(file);
        # else: => byhand

def main ():
    global Cnf, projectB, db_files, waste, excluded;

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Fernanda::Options::Help")];
    for i in [ "help" ]:
	if not Cnf.has_key("Frenanda::Options::%s" % (i)):
	    Cnf["Fernanda::Options::%s" % (i)] = "";

    args = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv);
    Options = Cnf.SubTree("Fernanda::Options")

    if Options["Help"]:
	usage();

    stdout_fd = sys.stdout;

    for file in args:
        try:
            # Pipe output for each argument through less
            less_fd = os.popen("less -", 'w', 0);
            sys.stdout = less_fd;

            try:
                if file[-8:] == ".changes":
                    check_changes(file);
                elif file[-4:] == ".deb" or file[-5:] == ".udeb":
                    check_deb(file);
                elif file[-4:] == ".dsc":
                    check_dsc(file);
                else:
                    utils.fubar("Unrecognised file type: '%s'." % (file));
            finally:
                # Reset stdout here so future less invocations aren't FUBAR
                less_fd.close();
                sys.stdout = stdout_fd;
        except IOError, e:
            if errno.errorcode[e.errno] == 'EPIPE':
                utils.warn("[fernanda] Caught EPIPE; skipping.");
                pass;
            else:
                raise;
        except KeyboardInterrupt:
            utils.warn("[fernanda] Caught C-c; skipping.");
            pass;

#######################################################################################

if __name__ == '__main__':
    main()

