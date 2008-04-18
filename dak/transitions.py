#!/usr/bin/env python

# Display, edit and check the release manager's transition file.
# Copyright (C) 2008 Joerg Jaspert <joerg@debian.org>

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

import os, pg, sys, time, errno, fcntl, tempfile, pwd, re
import apt_pkg
import daklib.database
import daklib.utils
import syck

# Globals
Cnf = None
Options = None
projectB = None

re_broken_package = re.compile(r"[a-zA-Z]\w+\s+\-.*")

################################################################################

#####################################
#### This may run within sudo !! ####
#####################################
def init():
    global Cnf, Options, projectB

    apt_pkg.init()

    Cnf = daklib.utils.get_conf()

    Arguments = [('h',"help","Edit-Transitions::Options::Help"),
                 ('e',"edit","Edit-Transitions::Options::Edit"),
                 ('i',"import","Edit-Transitions::Options::Import", "HasArg"),
                 ('c',"check","Edit-Transitions::Options::Check"),
                 ('s',"sudo","Edit-Transitions::Options::Sudo"),
                 ('n',"no-action","Edit-Transitions::Options::No-Action")]

    for i in ["help", "no-action", "edit", "import", "check", "sudo"]:
        if not Cnf.has_key("Edit-Transitions::Options::%s" % (i)):
            Cnf["Edit-Transitions::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Edit-Transitions::Options")

    if Options["help"]:
        usage()

    whoami = os.getuid()
    whoamifull = pwd.getpwuid(whoami)
    username = whoamifull[0]
    if username != "dak":
        print "Non-dak user: %s" % username
        Options["sudo"] = "y"

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)
    
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
  -n, --no-action           don't do anything (only affects check)"""

    sys.exit(exit_code)

################################################################################

#####################################
#### This may run within sudo !! ####
#####################################
def load_transitions(trans_file):
    # Parse the yaml file
    sourcefile = file(trans_file, 'r')
    sourcecontent = sourcefile.read()
    failure = False
    try:
        trans = syck.load(sourcecontent)
    except syck.error, msg:
        # Someone fucked it up
        print "ERROR: %s" % (msg)
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
                    if t[key] == "new" and type(t[key]) == int:
                        # Ok, debian native version
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
def lock_file(file):
    for retry in range(10):
        lock_fd = os.open(file, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_fd
        except OSError, e:
            if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EEXIST':
                print "Unable to get lock for %s (try %d of 10)" % \
                        (file, retry+1)
                time.sleep(60)
            else:
                raise

    daklib.utils.fubar("Couldn't obtain lock for %s." % (lockfile))

################################################################################

#####################################
#### This may run within sudo !! ####
#####################################
def write_transitions(from_trans):
    """Update the active transitions file safely.
       This function takes a parsed input file (which avoids invalid
       files or files that may be be modified while the function is
       active), and ensure the transitions file is updated atomically
       to avoid locks."""

    trans_file = Cnf["Dinstall::Reject::ReleaseTransitions"]
    trans_temp = trans_file + ".tmp"
  
    trans_lock = lock_file(trans_file)
    temp_lock  = lock_file(trans_temp)

    destfile = file(trans_temp, 'w')
    syck.dump(from_trans, destfile)
    destfile.close()

    os.rename(trans_temp, trans_file)
    os.close(temp_lock)
    os.close(trans_lock)

################################################################################

class ParseException(Exception):
    pass

##########################################
#### This usually runs within sudo !! ####
##########################################
def write_transitions_from_file(from_file):
    """We have a file we think is valid; if we're using sudo, we invoke it
       here, otherwise we just parse the file and call write_transitions"""

    # Lets check if from_file is in the directory we expect it to be in
    if not os.path.abspath(from_file).startswith(Cnf["Transitions::TempPath"]):
        print "Will not accept transitions file outside of %s" % (Cnf["Transitions::TempPath"])
        sys.exit(3)

    if Options["sudo"]:
        os.spawnl(os.P_WAIT, "/usr/bin/sudo", "/usr/bin/sudo", "-u", "dak", "-H", 
              "/usr/local/bin/dak", "transitions", "--import", from_file)
    else:
        trans = load_transitions(from_file)
        if trans is None:
            raise ParseException, "Unparsable transitions file %s" % (file)
        write_transitions(trans)

################################################################################

def temp_transitions_file(transitions):
    # NB: file is unlinked by caller, but fd is never actually closed.
    # We need the chmod, as the file is (most possibly) copied from a
    # sudo-ed script and would be unreadable if it has default mkstemp mode
    
    (fd, path) = tempfile.mkstemp("", "transitions", Cnf["Transitions::TempPath"])
    os.chmod(path, 0644)
    f = open(path, "w")
    syck.dump(transitions, f)
    return path

################################################################################

def edit_transitions():
    trans_file = Cnf["Dinstall::Reject::ReleaseTransitions"]
    edit_file = temp_transitions_file(load_transitions(trans_file))

    editor = os.environ.get("EDITOR", "vi")

    while True:
        result = os.system("%s %s" % (editor, edit_file))
        if result != 0:
            os.unlink(edit_file)
            daklib.utils.fubar("%s invocation failed for %s, not removing tempfile." % (editor, edit_file))
    
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
            answer = daklib.utils.our_raw_input(prompt)
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
    to_dump = 0
    to_remove = []
    # Now look through all defined transitions
    for trans in transitions:
        t = transitions[trans]
        source = t["source"]
        expected = t["new"]

        # Will be None if nothing is in testing.
        current = daklib.database.get_suite_version(source, "testing")

        print_info(trans, source, expected, t["rm"], t["reason"], t["packages"])

        if current == None:
            # No package in testing
            print "Transition source %s not in testing, transition still ongoing." % (source)
        else:
            compare = apt_pkg.VersionCompare(current, expected)
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
        else:
            answer = daklib.utils.our_raw_input(prompt).lower()

        if answer == "":
            answer = "n"

        if answer == 'n':
            print "Not committing changes"
            sys.exit(0)
        elif answer == 'y':
            print "Committing"
            for remove in to_remove:
                del transitions[remove]
    
            edit_file = temp_transitions_file(transitions)
            write_transitions_from_file(edit_file)

            print "Done"
        else:
            print "WTF are you typing?"
            sys.exit(0)

################################################################################

def print_info(trans, source, expected, rm, reason, packages):
        print """Looking at transition: %s
 Source:      %s
 New Version: %s
 Responsible: %s
 Description: %s
 Blocked Packages (total: %d): %s
""" % (trans, source, expected, rm, reason, len(packages), ", ".join(packages))
        return

################################################################################

def transition_info(transitions):
    for trans in transitions:
        t = transitions[trans]
        source = t["source"]
        expected = t["new"]

        # Will be None if nothing is in testing.
        current = daklib.database.get_suite_version(source, "testing")

        print_info(trans, source, expected, t["rm"], t["reason"], t["packages"])

        if current == None:
            # No package in testing
            print "Transition source %s not in testing, transition still ongoing." % (source)
        else:
            compare = apt_pkg.VersionCompare(current, expected)
            print "Apt compare says: %s" % (compare)
            if compare < 0:
                # This is still valid, the current version in database is older than
                # the new version we wait for
                print "This transition is still ongoing, we currently have version %s" % (current)
            else:
                print "This transition is over, the target package reached testing, should be removed"
                print "%s wanted version: %s, has %s" % (source, expected, current)
        print "-------------------------------------------------------------------------"

################################################################################

def main():
    global Cnf

    #####################################
    #### This can run within sudo !! ####
    #####################################
    init()
    
    # Check if there is a file defined (and existant)
    transpath = Cnf.get("Dinstall::Reject::ReleaseTransitions", "")
    if transpath == "":
        daklib.utils.warn("Dinstall::Reject::ReleaseTransitions not defined")
        sys.exit(1)
    if not os.path.exists(transpath):
        daklib.utils.warn("ReleaseTransitions file, %s, not found." %
                          (Cnf["Dinstall::Reject::ReleaseTransitions"]))
        sys.exit(1)
    # Also check if our temp directory is defined and existant
    temppath = Cnf.get("Transitions::TempPath", "")
    if temppath == "":
        daklib.utils.warn("Transitions::TempPath not defined")
        sys.exit(1)
    if not os.path.exists(temppath):
        daklib.utils.warn("Temporary path %s not found." %
                          (Cnf["Transitions::TempPath"]))
        sys.exit(1)
   
    if Options["import"]:
        try:
            write_transitions_from_file(Options["import"])
        except ParseException, m:
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
        daklib.utils.warn("Could not parse existing transitions file. Aborting.")
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
