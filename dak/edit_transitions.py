#!/usr/bin/env python

# Edit and then check the release managers transition file for correctness
# and outdated transitions
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

import os, pg, sys, time
import apt_pkg
import daklib.database
import daklib.utils
import syck

# Globals
Cnf = None
Options = None
projectB = None

################################################################################

def init():
    global Cnf, Options, projectB

    apt_pkg.init()

    Cnf = daklib.utils.get_conf()

    Arguments = [('h',"help","Edit-Transitions::Options::Help"),
                 ('e',"edit","Edit-Transitions::Option::Edit"),
                 ('c',"check","Edit-Transitions::Option::check"),
                 ('n',"no-action","Edit-Transitions::Options::No-Action")]

    for i in ["help", "no-action", "edit", "check"]:
        if not Cnf.has_key("Edit-Transitions::Options::%s" % (i)):
            Cnf["Edit-Transitions::Options::%s" % (i)] = ""

    apt_pkg.ParseCommandLine(Cnf, Arguments, sys.argv)

    Options = Cnf.SubTree("Edit-Transitions::Options")

    projectB = pg.connect(Cnf["DB::Name"], Cnf["DB::Host"], int(Cnf["DB::Port"]))
    daklib.database.init(Cnf, projectB)
    
    if Options["help"]:
        usage()

################################################################################

def usage (exit_code=0):
    print """Usage: edit_transitions [OPTION]...
  Check the release managers transition file for correctness and outdated transitions
  -h, --help                show this help and exit.
  -e, --edit                edit the transitions file
  -c, --check               check the transitions file, remove outdated entries
  -n, --no-action           don't do anything

  Called without an option this tool will check the transition file for outdated
  transitions and remove them."""
    sys.exit(exit_code)

################################################################################

def lock_file(lockfile):
    while retry < 10:
        try:
            lock_fd = os.open(lockfile, os.O_RDONLY | os.O_CREAT | os.O_EXCL)
            retry = 10
	    except OSError, e:
            if errno.errorcode[e.errno] == 'EACCES' or errno.errorcode[e.errno] == 'EEXIST':
                retry += 1
                if (retry >= 10):
                    daklib.utils.fubar("Couldn't obtain lock for %s." % (lockfile) )
                else:
                    print("Unable to get lock for %s (try %d of 10)" % (lockfile, retry) )
                    time.sleep(60)
            else:
                raise


################################################################################

def edit_transitions():
    trans_file = Cnf["Dinstall::Reject::ReleaseTransitions"]

    tempfile = "./%s.transition.tmp" % (os.getpid() )

    lockfile="%s.lock" % (tempfile)
    lock_file(lockfile)

    daklib.utils.copy(trans_file, tempfile )

    editor = os.environ.get("EDITOR", "vi")

    while True:
        result = os.system("%s %s" % (editor, temp_file))
        if result != 0:
            os.unlink(tempfile)
            os.unlink(lockfile)
            daklib.utils.fubar("%s invocation failed for %s, not removing tempfile." % (editor, temp_file))
    
        # Now try to load the new file
        test = load_transitions(tempfile)

        if test = None:
            # Edit is broken
            prompt = "Broken edit: [E]dit again, Drop changes?"
            while prompt.find(answer) == -1:
                answer = daklib.utils.our_raw_input(prompt)
                m = daklib.queue.re_default_answer.match(prompt)
                if answer == "":
                    answer = m.group(1)
                answer = answer[:1].upper()

            if answer == 'E':
                continue
            elif answer == 'D':
                os.unlink(tempfile)
                os.unlink(lockfile)
                sys.exit(0)
        else:
            # No problems in loading the new file, jump out of the while loop
            break

    # We seem to be done and also have a working file. Copy over.
    daklib.utils.copy(tempfile, trans_file)
    os.unlink(tempfile)
    os.unlink(lockfile)

################################################################################

def load_transitions(trans_file):
    # Parse the yaml file
    sourcefile = file(trans_file, 'r')
    sourcecontent = sourcefile.read()
    try:
        trans = syck.load(sourcecontent)
    except error, msg:
        # Someone fucked it up
        print "ERROR: %s" % (msg)
        return None
    return trans

################################################################################

def print_info(trans, source, expected, rm, reason, packages):
        print """
Looking at transition: %s
 Source:      %s
 New Version: %s
 Responsible: %s
 Description: %s
 Blocked Packages (total: %d): %s
""" % (trans, source, expected, rm, reason, len(packages), ", ".join(packages))
        return

################################################################################

def transition_info(transitions):
    print "Currently defined transitions:"
    for trans in transitions:
        t = transitions[trans]
        source = t["source"]
        expected = t["new"]

        # Will be None if nothing is in testing.
        current = daklib.database.get_testing_version(source)

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

def check_transitions(transitions):
    to_dump = 0
    to_remove = []
    # Now look through all defined transitions
    for trans in transitions:
        t = transitions[trans]
        source = t["source"]
        expected = t["new"]

        # Will be None if nothing is in testing.
        current = daklib.database.get_testing_version(source)

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
            destfile = file(Cnf["Dinstall::Reject::ReleaseTransitions"], 'w')
            syck.dump(transitions, destfile)
            print "Done"
        else:
            print "WTF are you typing?"
            sys.exit(0)


################################################################################

def main():
    global Cnf

    init()
    
    # Only check if there is a file defined (and existant) with checks. It's a little bit
    # specific to Debian, not much use for others, so return early there.
    if not Cnf.has_key("Dinstall::Reject::ReleaseTransitions") or not os.path.exists("%s" % (Cnf["Dinstall::Reject::ReleaseTransitions"])):
        daklib.utils.warn("Dinstall::Reject::ReleaseTransitions not defined or file %s not existant." %
                          (Cnf["Dinstall::Reject::ReleaseTransitions"]))
        sys.exit(1)
    
    # Parse the yaml file
    transitions = load_transitions(Cnf["Dinstall::Reject::ReleaseTransitions"])
    if transitions = None:
        # Something very broken with the transitions, exit
        daklib.utils.warn("Not doing any work, someone fucked up the transitions file outside our control")
        sys.exit(2)

    if Options["edit"]:
        # Output information about the currently defined transitions.
        transition_info(transitions)
        daklib.utils.our_raw_input("Press a key to continue...")

        # Lets edit the transitions file
        edit_transitions(Cnf["Dinstall::Reject::ReleaseTransitions"])
    elif Options["check"]:
        # Check and remove outdated transitions
        check_transitions(transitions, Cnf["Dinstall::Reject::ReleaseTransitions"])
    else:
        # Output information about the currently defined transitions.
        transition_info(transitions)
        daklib.utils.our_raw_input("Press a key to continue...")

        # Nothing requested, doing nothing besides the above display of the transitions
        sys.exit(0)
    

################################################################################

if __name__ == '__main__':
    main()
