#!/usr/bin/env python

"""Initial setup of an archive."""
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
from daklib import utils
from daklib.dbconn import *

################################################################################

Cnf = None

################################################################################

def usage(exit_code=0):
    """Print a usage message and exit with 'exit_code'."""

    print """Usage: dak init-dirs
Creates directories for an archive based on dak.conf configuration file.

  -h, --help                show this help and exit."""
    sys.exit(exit_code)

################################################################################

def do_dir(target, config_name):
    """If 'target' exists, make sure it is a directory.  If it doesn't, create
it."""

    if os.path.exists(target):
        if not os.path.isdir(target):
            utils.fubar("%s (%s) is not a directory."
                               % (target, config_name))
    else:
        print "Creating %s ..." % (target)
        os.makedirs(target)

def process_file(config, config_name):
    """Create directories for a config entry that's a filename."""

    if config.has_key(config_name):
        target = os.path.dirname(config[config_name])
        do_dir(target, config_name)

def process_tree(config, tree):
    """Create directories for a config tree."""

    for entry in config.subtree(tree).list():
        entry = entry.lower()
        config_name = "%s::%s" % (tree, entry)
        target = config[config_name]
        do_dir(target, config_name)

def process_morguesubdir(subdir):
    """Create directories for morgue sub directories."""

    config_name = "%s::MorgueSubDir" % (subdir)
    if Cnf.has_key(config_name):
        target = os.path.join(Cnf["Dir::Morgue"], Cnf[config_name])
        do_dir(target, config_name)

def process_keyring(fullpath, secret=False):
    """Create empty keyring if necessary."""

    if os.path.exists(fullpath):
        return

    keydir = os.path.dirname(fullpath)

    if not os.path.isdir(keydir):
        print "Creating %s ..." % (keydir)
        os.makedirs(keydir)
        if secret:
            # Make sure secret keyring directories are 0700
            os.chmod(keydir, 0o700)

    # Touch the file
    print "Creating %s ..." % (fullpath)
    file(fullpath, 'w')
    if secret:
        os.chmod(fullpath, 0o600)
    else:
        os.chmod(fullpath, 0o644)

######################################################################

def create_directories():
    """Create directories referenced in dak.conf."""

    session = DBConn().session()

    # Process directories from dak.conf
    process_tree(Cnf, "Dir")

    # Process queue directories
    for queue in session.query(PolicyQueue):
        do_dir(queue.path, '%s queue' % queue.queue_name)

    for config_name in [ "Rm::LogFile",
                         "Import-Archive::ExportDir" ]:
        process_file(Cnf, config_name)

    for subdir in [ "Clean-Queues", "Clean-Suites" ]:
        process_morguesubdir(subdir)

    suite_suffix = "%s" % (Cnf.find("Dinstall::SuiteSuffix"))

    # Process secret keyrings
    if Cnf.has_key('Dinstall::SigningKeyring'):
        process_keyring(Cnf['Dinstall::SigningKeyring'], secret=True)

    if Cnf.has_key('Dinstall::SigningPubKeyring'):
        process_keyring(Cnf['Dinstall::SigningPubKeyring'], secret=True)

    # Process public keyrings
    for keyring in session.query(Keyring).filter_by(active=True):
        process_keyring(keyring.keyring_name)

    # Process dists directories
    # TODO: Store location of each suite in database
    for suite in session.query(Suite):
        suite_dir = os.path.join(suite.archive.path, 'dists', suite.suite_name, suite_suffix)

        # TODO: Store valid suite/component mappings in database
        for component in session.query(Component):
            component_name = component.component_name

            sc_dir = os.path.join(suite_dir, component_name)

            do_dir(sc_dir, "%s/%s" % (suite.suite_name, component_name))

            for arch in suite.architectures:
                if arch.arch_string == 'source':
                    arch_string = 'source'
                else:
                    arch_string = 'binary-%s' % arch.arch_string

                suite_arch_dir = os.path.join(sc_dir, arch_string)

                do_dir(suite_arch_dir, "%s/%s/%s" % (suite.suite_name, component_name, arch_string))

################################################################################

def main ():
    """Initial setup of an archive."""

    global Cnf

    Cnf = utils.get_conf()
    arguments = [('h', "help", "Init-Dirs::Options::Help")]
    for i in [ "help" ]:
        if not Cnf.has_key("Init-Dirs::Options::%s" % (i)):
            Cnf["Init-Dirs::Options::%s" % (i)] = ""

    d = DBConn()

    arguments = apt_pkg.parse_commandline(Cnf, arguments, sys.argv)

    options = Cnf.subtree("Init-Dirs::Options")
    if options["Help"]:
        usage()
    elif arguments:
        utils.warn("dak init-dirs takes no arguments.")
        usage(exit_code=1)

    create_directories()

################################################################################

if __name__ == '__main__':
    main()
