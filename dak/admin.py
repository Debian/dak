#!/usr/bin/env python

"""Configure dak parameters in the database"""
# Copyright (C) 2009  Mark Hymers <mhy@debian.org>

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

import sys

import apt_pkg

from daklib import utils
from daklib.dbconn import *

################################################################################

dispatch = {}
dryrun = False

################################################################################
def warn(msg):
    print >> sys.stderr, msg

def die(msg, exit_code=1):
    print >> sys.stderr, msg
    sys.exit(exit_code)

def die_arglen(args, args_needed, msg):
    if len(args) < args_needed:
        die(msg)

def usage(exit_code=0):
    """Perform administrative work on the dak database."""

    print """Usage: dak admin COMMAND
Perform administrative work on the dak database.

  -h, --help          show this help and exit.
  -n, --dry-run       don't do anything, just show what would have been done
                      (only applies to add or rm operations).

  Commands can use a long or abbreviated form:

  architecture / a:
     a list                 show a list of architectures
     a rm ARCH              remove an architecture (will only work if
                            no longer linked to any suites)
     a add ARCH DESCRIPTION [SUITELIST]
                            add architecture ARCH with DESCRIPTION.
                            If SUITELIST is given, add to each of the
                            suites at the same time

  suite / s:
     s list                 show a list of suites
     s show SUITE           show config details for a suite

  suite-architecture / s-a:
     s-a list-suite ARCH    show the suites an ARCH is in
     s-a list-arch SUITE    show the architectures in a SUITE
     s-a add SUITE ARCH     add ARCH to suite
     s-a rm SUITE ARCH      remove ARCH from suite (will only work if
                            no packages remain for the arch in the suite)
"""
    sys.exit(exit_code)

################################################################################

def __architecture_list(d, args):
    q = d.session().query(Architecture).order_by('arch_string')
    for j in q.all():
        # HACK: We should get rid of source from the arch table
        if j.arch_string == 'source': continue
        print j.arch_string
    sys.exit(0)

def __architecture_add(d, args):
    die_arglen(args, 3, "E: adding an architecture requires a name and a description")
    print "Adding architecture %s" % args[2]
    suites = [str(x) for x in args[4:]]
    print suites
    if not dryrun:
        try:
            s = d.session()
            a = Architecture()
            a.arch_string = str(args[2]).lower()
            a.description = str(args[3])
            s.add(a)
            for sn in suites:
                su = get_suite(sn ,s)
                if su is not None:
                    archsu = SuiteArchitecture()
                    archsu.arch_id = a.arch_id
                    archsu.suite_id = su.suite_id
                    s.add(archsu)
                else:
                    warn("W: Cannot find suite %s" % su)
            s.commit()
        except IntegrityError, e:
            die("E: Integrity error adding architecture %s (it probably already exists)" % args[2])
        except SQLAlchemyError, e:
            die("E: Error adding architecture %s (%s)" % (args[2], e))
    print "Architecture %s added" % (args[2])

def __architecture_rm(d, args):
    die_arglen(args, 3, "E: removing an architecture requires at least a name")
    print "Removing architecture %s" % args[2]
    if not dryrun:
        try:
            s = d.session()
            a = get_architecture(args[2].lower(), s)
            if a is None:
                die("E: Cannot find architecture %s" % args[2])
            s.delete(a)
            s.commit()
        except IntegrityError, e:
            die("E: Integrity error removing architecture %s (suite-arch entries probably still exist)" % args[2])
        except SQLAlchemyError, e:
            die("E: Error removing architecture %s (%s)" % (args[2], e))
    print "Architecture %s removed" % args[2]

def architecture(command):
    args = [str(x) for x in command]
    Cnf = utils.get_conf()
    d = DBConn()

    die_arglen(args, 2, "E: architecture needs at least a command")

    mode = args[1].lower()
    if mode == 'list':
        __architecture_list(d, args)
    elif mode == 'add':
        __architecture_add(d, args)
    elif mode == 'rm':
        __architecture_rm(d, args)
    else:
        die("E: architecture command unknown")

dispatch['architecture'] = architecture
dispatch['a'] = architecture

################################################################################

def __suite_list(d, args):
    s = d.session()
    for j in s.query(Suite).order_by('suite_name').all():
        print j.suite_name

def __suite_show(d, args):
    if len(args) < 2:
        die("E: showing an suite entry requires a suite")

    s = d.session()
    su = get_suite(args[2].lower())
    if su is None:
        die("E: can't find suite entry for %s" % (args[2].lower()))

    print su.details()

def suite(command):
    args = [str(x) for x in command]
    Cnf = utils.get_conf()
    d = DBConn()

    die_arglen(args, 2, "E: suite needs at least a command")

    mode = args[1].lower()

    if mode == 'list':
        __suite_list(d, args)
    elif mode == 'show':
        __suite_show(d, args)
    else:
        die("E: suite command unknown")

dispatch['suite'] = suite
dispatch['s'] = suite

################################################################################

def __suite_architecture_list(d, args):
    s = d.session()
    for j in s.query(Suite).order_by('suite_name').all():
        print j.suite_name + ' ' + \
              ','.join([a.architecture.arch_string for a in j.suitearchitectures])

def __suite_architecture_listarch(d, args):
    die_arglen(args, 3, "E: suite-architecture list-arch requires a suite")
    a = get_suite_architectures(args[2].lower())
    for j in a:
        # HACK: We should get rid of source from the arch table
        if j.arch_string != 'source':
            print j.arch_string


def __suite_architecture_listsuite(d, args):
    die_arglen(args, 3, "E: suite-architecture list-suite requires an arch")
    for j in get_architecture_suites(args[2].lower()):
        print j.suite_name


def __suite_architecture_add(d, args):
    if len(args) < 3:
        die("E: adding a suite-architecture entry requires a suite and arch")

    s = d.session()

    suite = get_suite(args[2].lower(), s)
    if suite is None: die("E: Can't find suite %s" % args[2].lower())

    arch = get_architecture(args[3].lower(), s)
    if arch is None: die("E: Can't find architecture %s" % args[3].lower())

    if not dryrun:
        try:
            sa = SuiteArchitecture()
            sa.arch_id = arch.arch_id
            sa.suite_id = suite.suite_id
            s.add(sa)
            s.commit()
        except IntegrityError, e:
            die("E: Can't add suite-architecture entry (%s, %s) - probably already exists" % (args[2].lower(), args[3].lower()))
        except SQLAlchemyError, e:
            die("E: Can't add suite-architecture entry (%s, %s) - %s" % (args[2].lower(), args[3].lower(), e))

    print "Added suite-architecture entry for %s, %s" % (args[2].lower(), args[3].lower())


def __suite_architecture_rm(d, args):
    if len(args) < 3:
        die("E: removing an suite-architecture entry requires a suite and arch")

    s = d.session()
    if not dryrun:
        try:
            sa = get_suite_architecture(args[2].lower(), args[3].lower(), s)
            if sa is None:
                die("E: can't find suite-architecture entry for %s, %s" % (args[2].lower(), args[3].lower()))
            s.delete(sa)
            s.commit()
        except IntegrityError, e:
            die("E: Can't remove suite-architecture entry (%s, %s) - it's probably referenced" % (args[2].lower(), args[3].lower()))
        except SQLAlchemyError, e:
            die("E: Can't remove suite-architecture entry (%s, %s) - %s" % (args[2].lower(), args[3].lower(), e))

    print "Removed suite-architecture entry for %s, %s" % (args[2].lower(), args[3].lower())


def suite_architecture(command):
    args = [str(x) for x in command]
    Cnf = utils.get_conf()
    d = DBConn()

    die_arglen(args, 2, "E: suite-architecture needs at least a command")

    mode = args[1].lower()

    if mode == 'list':
        __suite_architecture_list(d, args)
    elif mode == 'list-arch':
        __suite_architecture_listarch(d, args)
    elif mode == 'list-suite':
        __suite_architecture_listsuite(d, args)
    elif mode == 'add':
        __suite_architecture_add(d, args)
    elif mode == 'rm':
        __suite_architecture_rm(d, args)
    else:
        die("E: suite-architecture command unknown")

dispatch['suite-architecture'] = suite_architecture
dispatch['s-a'] = suite_architecture

################################################################################

def main():
    """Perform administrative work on the dak database"""
    global dryrun
    Cnf = utils.get_conf()
    arguments = [('h', "help", "Admin::Options::Help"),
                 ('n', "dry-run", "Admin::Options::Dry-Run")]
    for i in [ "help", "dry-run" ]:
        if not Cnf.has_key("Admin::Options::%s" % (i)):
            Cnf["Admin::Options::%s" % (i)] = ""

    arguments = apt_pkg.ParseCommandLine(Cnf, arguments, sys.argv)

    options = Cnf.SubTree("Admin::Options")
    if options["Help"] or len(arguments) < 1:
        usage()
    if options["Dry-Run"]:
        dryrun = True

    subcommand = str(arguments[0])

    if subcommand in dispatch.keys():
        dispatch[subcommand](arguments)
    else:
        die("E: Unknown command")

################################################################################

if __name__ == '__main__':
    main()
