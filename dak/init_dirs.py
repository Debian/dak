#!/usr/bin/env python

# Initial setup of an archive
# Copyright (C) 2002, 2004, 2006  James Troup <james@nocrew.org>

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
import apt_pkg
import daklib.utils

################################################################################

Cnf = None
AptCnf = None

################################################################################

def usage(exit_code=0):
    print """Usage: dak init-dirs
Creates directories for an archive based on dak.conf configuration file.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def do_dir(target, config_name):
    if os.path.exists(target):
        if not os.path.isdir(target):
            daklib.utils.fubar("%s (%s) is not a directory." % (target, config_name))
    else:
        print "Creating %s ..." % (target)
        os.makedirs(target)

def process_file(config, config_name):
    if config.has_key(config_name):
        target = os.path.dirname(config[config_name])
        do_dir(target, config_name)

def process_tree(config, tree):
    for entry in config.SubTree(tree).List():
        entry = entry.lower()
        if tree == "Dir":
            if entry in [ "poolroot", "queue" , "morguereject" ]:
                continue
        config_name = "%s::%s" % (tree, entry)
        target = config[config_name]
        do_dir(target, config_name)

def process_morguesubdir(subdir):
    config_name = "%s::MorgueSubDir" % (subdir)
    if Cnf.has_key(config_name):
        target = os.path.join(Cnf["Dir::Morgue"], Cnf[config_name])
        do_dir(target, config_name)

######################################################################

def create_directories():
    # Process directories from apt.conf
    process_tree(Cnf, "Dir")
    process_tree(Cnf, "Dir::Queue")
    for file in [ "Dinstall::LockFile", "Rm::LogFile", "Import-Archive::ExportDir" ]:
        process_file(Cnf, file)
    for subdir in [ "Clean-Queues", "Clean-Suites" ]:
        process_morguesubdir(subdir)

    # Process directories from apt.conf
    process_tree(AptCnf, "Dir")
    for tree in AptCnf.SubTree("Tree").List():
        config_name = "Tree::%s" % (tree)
        tree_dir = os.path.join(Cnf["Dir::Root"], tree)
        do_dir(tree_dir, tree)
        for file in [ "FileList", "SourceFileList" ]:
            process_file(AptCnf, "%s::%s" % (config_name, file))
        for component in AptCnf["%s::Sections" % (config_name)].split():
            for architecture in AptCnf["%s::Architectures" % (config_name)].split():
                if architecture != "source":
                    architecture = "binary-"+architecture
                target = os.path.join(tree_dir,component,architecture)
                do_dir(target, "%s, %s, %s" % (tree, component, architecture))


################################################################################

def main ():
    global AptCnf, Cnf, projectB

    Cnf = daklib.utils.get_conf()
    Arguments = [('h',"help","Init-Dirs::Options::Help")]
    for i in [ "help" ]:
	if not Cnf.has_key("Init-Dirs::Options::%s" % (i)):
	    Cnf["Init-Dirs::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Init-Dirs::Options")
    if Options["Help"]:
	usage()

    AptCnf = apt_pkg.newConfiguration()
    apt_pkg.ReadConfigFileISC(AptCnf,daklib.utils.which_apt_conf_file())

    create_directories()

################################################################################

if __name__ == '__main__':
    main()

