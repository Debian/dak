#!/usr/bin/env python

"""
Display, edit and check the release manager's transition file.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008 Joerg Jaspert <joerg@debian.org>
@license: GNU General Public License version 2 or later
"""

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

# <elmo> if klecker.d.o died, I swear to god, I'm going to migrate to gentoo.

################################################################################

import os
import sys
import time
import errno
import fcntl
import tempfile
import apt_pkg

from daklib.dbconn import *
from daklib import utils
from daklib.dak_exceptions import TransitionsError
from daklib.regexes import re_broken_package
import yaml

# Globals
Cnf = None      #: Configuration, apt_pkg.Configuration
Options = None  #: Parsed CommandLine arguments

################################################################################

#####################################
#### This may run within sudo !! ####
#####################################
def init():
    """
    Initialize. Sets up database connection, parses commandline arguments.

    @attention: This function may run B{within sudo}

    """
    global Cnf, Options

    apt_pkg.init()

    Cnf = utils.get_conf()

    Arguments = [('a',"automatic","Edit-Transitions::Options::Automatic"),
                 ('h',"help","Edit-Transitions::Options::Help"),
                 ('e',"edit","Edit-Transitions::Options::Edit"),
                 ('i',"import","Edit-Transitions::Options::Import", "HasArg"),
                 ('c',"check","Edit-Transitions::Options::Check"),
                 ('s',"sudo","Edit-Transitions::Options::Sudo"),
                 ('n',"no-action","Edit-Transitions::Options::No-Action")]

    for i in ["automatic", "help", "no-action", "edit", "import", "check", "sudo"]:
        if not Cnf.has_key("Edit-Transitions::Options::%s" % (i)):
            Cnf["Edit-Transitions::Options::%s" % (i)] = ""

    apt_pkg.parse_commandline(Cnf, Arguments, sys.argv)

    Options = Cnf.subtree("Edit-Transitions::Options")

    if Options["help"]:
        usage()

    username = utils.getusername()
    if username != "dak":
        print "Non-dak user: %s" % username
        Options["sudo"] = "y"

    # Initialise DB connection
    DBConn()

################################################################################

def usage (exit_code=0):
    print """Usage: transitions [OPTION]...
Update and check the release managers transition file.

Options:

  -h, --help                show this help and exit.
  -e, --edit                edit the transitions file
  -i, --import <file>       check and import transitions from file
  -c, --check               check the transitions file, remove outdated entries
  -S, --sudo                use sudo to update transitions file
  -a, --automatic           don't prompt (only affects check).
  -n, --no-action           don't do anything (only affects check)"""

    sys.exit(exit_code)

################################################################################

#####################################
#### This may run within sudo !! ####
#####################################
def load_transitions(trans_file):
    """
    Parse a transition yaml file and check it for validity.

    @attention: This function may run B{within sudo}

    @type trans_file: string
    @param trans_file: filename to parse

    @rtype: dict or None
    @return: validated dictionary of transition entries or None
             if validation fails, empty string if reading C{trans_file}
             returned something else than a dict

    """
    # Parse the yaml file
    sourcefile = file(trans_file, 'r')
    sourcecontent = sourcefile.read()
    failure = False
    try:
        trans = yaml.safe_load(sourcecontent)
    except yaml.YAMLError as exc:
        # Someone fucked it up
        print "ERROR: %s" % (exc)
        return None

    # lets do further validation here
    checkkeys = ["source", "reason", "packages", "new", "rm"]

    # If we get an empty definition - we just have nothing to check, no transitions defined
    if type(trans) != dict:
        # This can be anything. We could have no transitions defined. Or someone totally fucked up the
        # file, adding stuff in a way we dont know or want. Then we set it empty - and simply have no
        # transitions anymore. User will see it in the information display after he quit the editor and
        # could fix it
        trans = ""
        return trans

    try:
        for test in trans:
            t = trans[test]

            # First check if we know all the keys for the transition and if they have
            # the right type (and for the packages also if the list has the right types
            # included, ie. not a list in list, but only str in the list)
            for key in t:
                if key not in checkkeys:
                    print "ERROR: Unknown key %s in transition %s" % (key, test)
                    failure = True

                if key == "packages":
                    if type(t[key]) != list:
                        print "ERROR: Unknown type %s for packages in transition %s." % (type(t[key]), test)
                        failure = True
                    try:
                        for package in t["packages"]:
                            if type(package) != str:
                                print "ERROR: Packages list contains invalid type %s (as %s) in transition %s" % (type(package), package, test)
                                failure = True
                            if re_broken_package.match(package):
                                # Someone had a space too much (or not enough), we have something looking like
                                # "package1 - package2" now.
                                print "ERROR: Invalid indentation of package list in transition %s, around package(s): %s" % (test, package)
                                failure = True
                    except TypeError:
                        # In case someone has an empty packages list
                        print "ERROR: No packages defined in transition %s" % (test)
                        failure = True
                        continue

                elif type(t[key]) != str:
                    if key == "new" and type(t[key]) == int:
                        # Ok, debian native version
                        continue
                    else:
                        print "ERROR: Unknown type %s for key %s in transition %s" % (type(t[key]), key, test)
                        failure = True

            # And now the other way round - are all our keys defined?
            for key in checkkeys:
                if key not in t:
                    print "ERROR: Missing key %s in transition %s" % (key, test)
                    failure = True
    except TypeError:
        # In case someone defined very broken things
        print "ERROR: Unable to parse the file"
        failure = True


    if failure:
        return None

    return trans

################################################################################

#####################################
#### This may run within sudo !! ####
#####################################
def lock_file(f):
    """
    Lock a file

    @attention: This function may run B{within sudo}

    """
    for retry in range(10):
        lock_fd = os.open(f, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_fd
        except OSError as e:
            if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EEXIST':
                print "Unable to get lock for %s (try %d of 10)" % \
                        (file, retry+1)
                time.sleep(60)
            else:
                raise

    utils.fubar("Couldn't obtain lock for %s." % (f))

################################################################################

#####################################
#### This may run within sudo !! ####
#####################################
def write_transitions(from_trans):
    """
    Update the active transitions file safely.
    This function takes a parsed input file (which avoids invalid
    files or files that may be be modified while the function is
    active) and ensure the transitions file is updated atomically
    to avoid locks.

    @attention: This function may run B{within sudo}

    @type from_trans: dict
    @param from_trans: transitions dictionary, as returned by L{load_transitions}

    """

    trans_file = Cnf["Dinstall::ReleaseTransitions"]
    trans_temp = trans_file + ".tmp"

    trans_lock = lock_file(trans_file)
    temp_lock  = lock_file(trans_temp)

    destfile = file(trans_temp, 'w')
    yaml.safe_dump(from_trans, destfile, default_flow_style=False)
    destfile.close()

    os.rename(trans_temp, trans_file)
    os.close(temp_lock)
    os.close(trans_lock)

################################################################################

##########################################
#### This usually runs within sudo !! ####
##########################################
def write_transitions_from_file(from_file):
    """
    We have a file we think is valid; if we're using sudo, we invoke it
    here, otherwise we just parse the file and call write_transitions

    @attention: This function usually runs B{within sudo}

    @type from_file: filename
    @param from_file: filename of a transitions file

    """

    # Lets check if from_file is in the directory we expect it to be in
    if not os.path.abspath(from_file).startswith(Cnf["Dir::TempPath"]):
        print "Will not accept transitions file outside of %s" % (Cnf["Dir::TempPath"])
        sys.exit(3)

    if Options["sudo"]:
        os.spawnl(os.P_WAIT, "/usr/bin/sudo", "/usr/bin/sudo", "-u", "dak", "-H",
              "/usr/local/bin/dak", "transitions", "--import", from_file)
    else:
        trans = load_transitions(from_file)
        if trans is None:
            raise TransitionsError("Unparsable transitions file %s" % (file))
        write_transitions(trans)

################################################################################

def temp_transitions_file(transitions):
    """
    Open a temporary file and dump the current transitions into it, so users
    can edit them.

    @type transitions: dict
    @param transitions: current defined transitions

    @rtype: string
    @return: path of newly created tempfile

    @note: NB: file is unlinked by caller, but fd is never actually closed.
           We need the chmod, as the file is (most possibly) copied from a
           sudo-ed script and would be unreadable if it has default mkstemp mode
    """

    (fd, path) = tempfile.mkstemp("", "transitions", Cnf["Dir::TempPath"])
    os.chmod(path, 0o644)
    f = open(path, "w")
    yaml.safe_dump(transitions, f, default_flow_style=False)
    return path

################################################################################

def edit_transitions():
    """ Edit the defined transitions. """
    trans_file = Cnf["Dinstall::ReleaseTransitions"]
    edit_file = temp_transitions_file(load_transitions(trans_file))

    editor = os.environ.get("EDITOR", "vi")

    while True:
        result = os.system("%s %s" % (editor, edit_file))
        if result != 0:
            os.unlink(edit_file)
            utils.fubar("%s invocation failed for %s, not removing tempfile." % (editor, edit_file))

        # Now try to load the new file
        test = load_transitions(edit_file)

        if test == None:
            # Edit is broken
            print "Edit was unparsable."
            prompt = "[E]dit again, Drop changes?"
            default = "E"
        else:
            print "Edit looks okay.\n"
            print "The following transitions are defined:"
            print "------------------------------------------------------------------------"
            transition_info(test)

            prompt = "[S]ave, Edit again, Drop changes?"
            default = "S"

        answer = "XXX"
        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            if answer == "":
                answer = default
            answer = answer[:1].upper()

        if answer == 'E':
            continue
        elif answer == 'D':
            os.unlink(edit_file)
            print "OK, discarding changes"
            sys.exit(0)
        elif answer == 'S':
            # Ready to save
            break
        else:
            print "You pressed something you shouldn't have :("
            sys.exit(1)

    # We seem to be done and also have a working file. Copy over.
    write_transitions_from_file(edit_file)
    os.unlink(edit_file)

    print "Transitions file updated."

################################################################################

def check_transitions(transitions):
    """
    Check if the defined transitions still apply and remove those that no longer do.
    @note: Asks the user for confirmation first unless -a has been set.

    """
    global Cnf

    to_dump = 0
    to_remove = []
    info = {}

    session = DBConn().session()

    # Now look through all defined transitions
    for trans in transitions:
        t = transitions[trans]
        source = t["source"]
        expected = t["new"]

        # Will be an empty list if nothing is in testing.
        sourceobj = get_source_in_suite(source, "testing", session)

        info[trans] = get_info(trans, source, expected, t["rm"], t["reason"], t["packages"])
        print info[trans]

        if sourceobj is None:
            # No package in testing
            print "Transition source %s not in testing, transition still ongoing." % (source)
        else:
            current = sourceobj.version
            compare = apt_pkg.version_compare(current, expected)
            if compare < 0:
                # This is still valid, the current version in database is older than
                # the new version we wait for
                print "This transition is still ongoing, we currently have version %s" % (current)
            else:
                print "REMOVE: This transition is over, the target package reached testing. REMOVE"
                print "%s wanted version: %s, has %s" % (source, expected, current)
                to_remove.append(trans)
                to_dump = 1
        print "-------------------------------------------------------------------------"

    if to_dump:
        prompt = "Removing: "
        for remove in to_remove:
            prompt += remove
            prompt += ","

        prompt += " Commit Changes? (y/N)"
        answer = ""

        if Options["no-action"]:
            answer="n"
        elif Options["automatic"]:
            answer="y"
        else:
            answer = utils.our_raw_input(prompt).lower()

        if answer == "":
            answer = "n"

        if answer == 'n':
            print "Not committing changes"
            sys.exit(0)
        elif answer == 'y':
            print "Committing"
            subst = {}
            subst['__SUBJECT__'] = "Transitions completed: " + ", ".join(sorted(to_remove))
            subst['__TRANSITION_MESSAGE__'] = "The following transitions were removed:\n"
            for remove in sorted(to_remove):
                subst['__TRANSITION_MESSAGE__'] += info[remove] + '\n'
                del transitions[remove]

            # If we have a mail address configured for transitions,
            # send a notification
            subst['__TRANSITION_EMAIL__'] = Cnf.get("Transitions::Notifications", "")
            if subst['__TRANSITION_EMAIL__'] != "":
                print "Sending notification to %s" % subst['__TRANSITION_EMAIL__']
                subst['__DAK_ADDRESS__'] = Cnf["Dinstall::MyEmailAddress"]
                subst['__BCC__'] = 'X-DAK: dak transitions'
                if Cnf.has_key("Dinstall::Bcc"):
                    subst["__BCC__"] += '\nBcc: %s' % Cnf["Dinstall::Bcc"]
                message = utils.TemplateSubst(subst,
                                              os.path.join(Cnf["Dir::Templates"], 'transition.removed'))
                utils.send_mail(message)

            edit_file = temp_transitions_file(transitions)
            write_transitions_from_file(edit_file)

            print "Done"
        else:
            print "WTF are you typing?"
            sys.exit(0)

################################################################################

def get_info(trans, source, expected, rm, reason, packages):
    """
    Print information about a single transition.

    @type trans: string
    @param trans: Transition name

    @type source: string
    @param source: Source package

    @type expected: string
    @param expected: Expected version in testing

    @type rm: string
    @param rm: Responsible RM

    @type reason: string
    @param reason: Reason

    @type packages: list
    @param packages: list of blocked packages

    """
    return """Looking at transition: %s
Source:      %s
New Version: %s
Responsible: %s
Description: %s
Blocked Packages (total: %d): %s
""" % (trans, source, expected, rm, reason, len(packages), ", ".join(packages))

################################################################################

def transition_info(transitions):
    """
    Print information about all defined transitions.
    Calls L{get_info} for every transition and then tells user if the transition is
    still ongoing or if the expected version already hit testing.

    @type transitions: dict
    @param transitions: defined transitions
    """

    session = DBConn().session()

    for trans in transitions:
        t = transitions[trans]
        source = t["source"]
        expected = t["new"]

        # Will be None if nothing is in testing.
        sourceobj = get_source_in_suite(source, "testing", session)

        print get_info(trans, source, expected, t["rm"], t["reason"], t["packages"])

        if sourceobj is None:
            # No package in testing
            print "Transition source %s not in testing, transition still ongoing." % (source)
        else:
            compare = apt_pkg.version_compare(sourceobj.version, expected)
            print "Apt compare says: %s" % (compare)
            if compare < 0:
                # This is still valid, the current version in database is older than
                # the new version we wait for
                print "This transition is still ongoing, we currently have version %s" % (sourceobj.version)
            else:
                print "This transition is over, the target package reached testing, should be removed"
                print "%s wanted version: %s, has %s" % (source, expected, sourceobj.version)
        print "-------------------------------------------------------------------------"

################################################################################

def main():
    """
    Prepare the work to be done, do basic checks.

    @attention: This function may run B{within sudo}

    """
    global Cnf

    #####################################
    #### This can run within sudo !! ####
    #####################################
    init()

    # Check if there is a file defined (and existant)
    transpath = Cnf.get("Dinstall::ReleaseTransitions", "")
    if transpath == "":
        utils.warn("Dinstall::ReleaseTransitions not defined")
        sys.exit(1)
    if not os.path.exists(transpath):
        utils.warn("ReleaseTransitions file, %s, not found." %
                          (Cnf["Dinstall::ReleaseTransitions"]))
        sys.exit(1)
    # Also check if our temp directory is defined and existant
    temppath = Cnf.get("Dir::TempPath", "")
    if temppath == "":
        utils.warn("Dir::TempPath not defined")
        sys.exit(1)
    if not os.path.exists(temppath):
        utils.warn("Temporary path %s not found." %
                          (Cnf["Dir::TempPath"]))
        sys.exit(1)

    if Options["import"]:
        try:
            write_transitions_from_file(Options["import"])
        except TransitionsError as m:
            print m
            sys.exit(2)
        sys.exit(0)
    ##############################################
    #### Up to here it can run within sudo !! ####
    ##############################################

    # Parse the yaml file
    transitions = load_transitions(transpath)
    if transitions == None:
        # Something very broken with the transitions, exit
        utils.warn("Could not parse existing transitions file. Aborting.")
        sys.exit(2)

    if Options["edit"]:
        # Let's edit the transitions file
        edit_transitions()
    elif Options["check"]:
        # Check and remove outdated transitions
        check_transitions(transitions)
    else:
        # Output information about the currently defined transitions.
        print "Currently defined transitions:"
        transition_info(transitions)

    sys.exit(0)

################################################################################

if __name__ == '__main__':
    main()
