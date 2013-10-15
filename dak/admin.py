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
from sqlalchemy.orm.exc import NoResultFound

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

  config / c:
     c db                   show db config
     c db-shell             show db config in a usable form for psql
     c NAME                 show option NAME as set in configuration table

  keyring / k:
     k list-all             list all keyrings
     k list-binary          list all keyrings with a NULL source acl
     k list-source          list all keyrings with a non NULL source acl
     k add-buildd NAME ARCH...   add buildd keyring with upload permission
                                 for the given architectures

  architecture / a:
     a list                 show a list of architectures
     a rm ARCH              remove an architecture (will only work if
                            no longer linked to any suites)
     a add ARCH DESCRIPTION [SUITELIST]
                            add architecture ARCH with DESCRIPTION.
                            If SUITELIST is given, add to each of the
                            suites at the same time

  component:
     component list         show a list of components
     component rm COMPONENT remove a component (will only work if
                            empty)
     component add NAME DESCRIPTION ORDERING
                            add component NAME with DESCRIPTION.
                            Ordered at ORDERING.

  suite / s:
     s list [--print-archive]
                            show a list of suites
     s show SUITE           show config details for a suite
     s add SUITE VERSION [ label=LABEL ] [ description=DESCRIPTION ]
                         [ origin=ORIGIN ] [ codename=CODENAME ]
                         [ signingkey=SIGNINGKEY ] [ archive=ARCHIVE ]
                            add suite SUITE, version VERSION.
                            label, description, origin, codename
                            and signingkey are optional.

     s add-all-arches SUITE VERSION... as "s add" but adds suite-architecture
                            relationships for all architectures

  suite-architecture / s-a:
     s-a list               show the architectures for all suites
     s-a list-suite ARCH    show the suites an ARCH is in
     s-a list-arch SUITE    show the architectures in a SUITE
     s-a add SUITE ARCH     add ARCH to suite
     s-a rm SUITE ARCH      remove ARCH from suite (will only work if
                            no packages remain for the arch in the suite)

  suite-component / s-c:
     s-c list               show the architectures for all suites
     s-c list-suite COMPONENT
                            show the suites a COMPONENT is in
     s-c list-component SUITE
                            show the components in a SUITE
     s-c add SUITE COMPONENT
                            add COMPONENT to suite
     s-c rm SUITE COMPONENT remove component from suite (will only work if
                            no packages remain for the component in the suite)

  archive:
     archive list           list all archives
     archive add NAME ROOT DESCRIPTION [primary-mirror=MIRROR] [tainted=1]
                            add archive NAME with path ROOT,
                            primary mirror MIRROR.
     archive rm NAME        remove archive NAME (will only work if there are
                            no files and no suites in the archive)
     archive rename OLD NEW rename archive OLD to NEW

  version-check / v-c:
     v-c list                        show version checks for all suites
     v-c list-suite SUITE            show version checks for suite SUITE
     v-c add SUITE CHECK REFERENCE   add a version check for suite SUITE
     v-c rm SUITE CHECK REFERENCE    remove a version check
       where
         CHECK     is one of Enhances, MustBeNewerThan, MustBeOlderThan
	 REFERENCE is another suite name
"""
    sys.exit(exit_code)

################################################################################

def __architecture_list(d, args):
    q = d.session().query(Architecture).order_by(Architecture.arch_string)
    for j in q.all():
        # HACK: We should get rid of source from the arch table
        if j.arch_string == 'source': continue
        print j.arch_string
    sys.exit(0)

def __architecture_add(d, args):
    die_arglen(args, 4, "E: adding an architecture requires a name and a description")
    print "Adding architecture %s" % args[2]
    suites = [str(x) for x in args[4:]]
    if len(suites) > 0:
        print "Adding to suites %s" % ", ".join(suites)
    if not dryrun:
        try:
            s = d.session()
            a = Architecture()
            a.arch_string = str(args[2]).lower()
            a.description = str(args[3])
            s.add(a)
            for sn in suites:
                su = get_suite(sn, s)
                if su is not None:
                    a.suites.append(su)
                else:
                    warn("W: Cannot find suite %s" % su)
            s.commit()
        except IntegrityError as e:
            die("E: Integrity error adding architecture %s (it probably already exists)" % args[2])
        except SQLAlchemyError as e:
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
        except IntegrityError as e:
            die("E: Integrity error removing architecture %s (suite-arch entries probably still exist)" % args[2])
        except SQLAlchemyError as e:
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

def component_list():
    session = DBConn().session()
    for component in session.query(Component).order_by(Component.component_name):
        print "{0} ordering={1}".format(component.component_name, component.ordering)

def component_add(args):
    (name, description, ordering) = args[0:3]

    attributes = dict(
        component_name=name,
        description=description,
        ordering=ordering,
        )

    for option in args[3:]:
        (key, value) = option.split('=')
        attributes[key] = value

    session = DBConn().session()

    component = Component()
    for key, value in attributes.iteritems():
        setattr(component, key, value)

    session.add(component)
    session.flush()

    if dryrun:
        session.rollback()
    else:
        session.commit()

def component_rm(name):
    session = DBConn().session()
    component = get_component(name, session)
    session.delete(component)
    session.flush()

    if dryrun:
        session.rollback()
    else:
        session.commit()

def component_rename(oldname, newname):
    session = DBConn().session()
    component = get_component(oldname, session)
    component.component_name = newname
    session.flush()

    if dryrun:
        session.rollback()
    else:
        session.commit()

def component(command):
    mode = command[1]
    if mode == 'list':
        component_list()
    elif mode == 'rename':
        component_rename(command[2], command[3])
    elif mode == 'add':
        component_add(command[2:])
    elif mode == 'rm':
        component_rm(command[2])
    else:
        die("E: component command unknown")

dispatch['component'] = component

################################################################################

def __suite_list(d, args):
    s = d.session()
    for j in s.query(Suite).join(Suite.archive).order_by(Archive.archive_name, Suite.suite_name).all():
        if len(args) > 2 and args[2] == "--print-archive":
            print "{0} {1}".format(j.archive.archive_name, j.suite_name)
        else:
            print "{0}".format(j.suite_name)

def __suite_show(d, args):
    if len(args) < 2:
        die("E: showing an suite entry requires a suite")

    s = d.session()
    su = get_suite(args[2].lower())
    if su is None:
        die("E: can't find suite entry for %s" % (args[2].lower()))

    print su.details()

def __suite_add(d, args, addallarches=False):
    die_arglen(args, 4, "E: adding a suite requires at least a name and a version")
    suite_name = args[2].lower()
    version = args[3]
    rest = args[3:]

    def get_field(field):
        for varval in args:
            if varval.startswith(field + '='):
                return varval.split('=')[1]
        return None

    print "Adding suite %s" % suite_name
    if not dryrun:
        try:
            s = d.session()
            suite = Suite()
            suite.suite_name = suite_name
            suite.overridecodename = suite_name
            suite.version = version
            suite.label = get_field('label')
            suite.description = get_field('description')
            suite.origin = get_field('origin')
            suite.codename = get_field('codename')
            signingkey = get_field('signingkey')
            if signingkey is not None:
                suite.signingkeys = [signingkey.upper()]
            archive_name = get_field('archive')
            if archive_name is not None:
                suite.archive = get_archive(archive_name, s)
            else:
                suite.archive = s.query(Archive).filter(~Archive.archive_name.in_(['build-queues', 'new', 'policy'])).one()
            suite.srcformats = s.query(SrcFormat).all()
            s.add(suite)
            s.flush()
        except IntegrityError as e:
            die("E: Integrity error adding suite %s (it probably already exists)" % suite_name)
        except SQLAlchemyError as e:
            die("E: Error adding suite %s (%s)" % (suite_name, e))
    print "Suite %s added" % (suite_name)

    if addallarches:
        arches = []
        q = s.query(Architecture).order_by(Architecture.arch_string)
        for arch in q.all():
            suite.architectures.append(arch)
            arches.append(arch.arch_string)

        print "Architectures %s added to %s" % (','.join(arches), suite_name)

    s.commit()

def __suite_rm(d, args):
    die_arglen(args, 3, "E: removing a suite requires at least a name")
    name = args[2]
    print "Removing suite {0}".format(name)
    if not dryrun:
        try:
            s = d.session()
            su = get_suite(name.lower())
            if su is None:
                die("E: Cannot find suite {0}".format(name))
            s.delete(su)
            s.commit()
        except IntegrityError as e:
            die("E: Integrity error removing suite {0} (suite-arch entries probably still exist)".format(name))
        except SQLAlchemyError as e:
            die("E: Error removing suite {0} ({1})".format(name, e))
    print "Suite {0} removed".format(name)

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
    elif mode == 'rm':
        __suite_rm(d, args)
    elif mode == 'add':
        __suite_add(d, args, False)
    elif mode == 'add-all-arches':
        __suite_add(d, args, True)
    else:
        die("E: suite command unknown")

dispatch['suite'] = suite
dispatch['s'] = suite

################################################################################

def __suite_architecture_list(d, args):
    s = d.session()
    for j in s.query(Suite).order_by(Suite.suite_name):
        architectures = j.get_architectures(skipsrc = True, skipall = True)
        print j.suite_name + ': ' + \
              ', '.join([a.arch_string for a in architectures])

def __suite_architecture_listarch(d, args):
    die_arglen(args, 3, "E: suite-architecture list-arch requires a suite")
    suite = get_suite(args[2].lower(), d.session())
    if suite is None:
        die('E: suite %s is invalid' % args[2].lower())
    a = suite.get_architectures(skipsrc = True, skipall = True)
    for j in a:
        print j.arch_string


def __suite_architecture_listsuite(d, args):
    die_arglen(args, 3, "E: suite-architecture list-suite requires an arch")
    architecture = get_architecture(args[2].lower(), d.session())
    if architecture is None:
        die("E: architecture %s is invalid" % args[2].lower())
    for j in architecture.suites:
        print j.suite_name


def __suite_architecture_add(d, args):
    if len(args) < 3:
        die("E: adding a suite-architecture entry requires a suite and arch")

    s = d.session()

    suite = get_suite(args[2].lower(), s)
    if suite is None: die("E: Can't find suite %s" % args[2].lower())

    for arch_name in args[3:]:
        arch = get_architecture(arch_name.lower(), s)
        if arch is None: die("E: Can't find architecture %s" % args[3].lower())

        try:
            suite.architectures.append(arch)
            s.flush()
        except IntegrityError as e:
            die("E: Can't add suite-architecture entry (%s, %s) - probably already exists" % (args[2].lower(), arch_name))
        except SQLAlchemyError as e:
            die("E: Can't add suite-architecture entry (%s, %s) - %s" % (args[2].lower(), arch_name, e))

        print "Added suite-architecture entry for %s, %s" % (args[2].lower(), arch_name)

    if not dryrun:
        s.commit()

    s.close()

def __suite_architecture_rm(d, args):
    if len(args) < 3:
        die("E: removing an suite-architecture entry requires a suite and arch")

    s = d.session()
    if not dryrun:
        try:
            suite_name = args[2].lower()
            suite = get_suite(suite_name, s)
            if suite is None:
                die('E: no such suite %s' % suite_name)
            arch_string = args[3].lower()
            architecture = get_architecture(arch_string, s)
            if architecture not in suite.architectures:
                die("E: architecture %s not found in suite %s" % (arch_string, suite_name))
            suite.architectures.remove(architecture)
            s.commit()
        except IntegrityError as e:
            die("E: Can't remove suite-architecture entry (%s, %s) - it's probably referenced" % (args[2].lower(), args[3].lower()))
        except SQLAlchemyError as e:
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

def __suite_component_list(d, args):
    s = d.session()
    for j in s.query(Suite).order_by(Suite.suite_name):
        components = j.components
        print j.suite_name + ': ' + \
              ', '.join([c.component_name for c in components])


def __suite_component_listcomponent(d, args):
     die_arglen(args, 3, "E: suite-component list-component requires a suite")
     suite = get_suite(args[2].lower(), d.session())
     if suite is None:
         die('E: suite %s is invalid' % args[2].lower())
     for c in suite.components:
         print c.component_name


def __suite_component_listsuite(d, args):
     die_arglen(args, 3, "E: suite-component list-suite requires an component")
     component = get_component(args[2].lower(), d.session())
     if component is None:
         die("E: component %s is invalid" % args[2].lower())
     for s in component.suites:
         print s.suite_name


def __suite_component_add(d, args):
     if len(args) < 3:
         die("E: adding a suite-component entry requires a suite and component")

     s = d.session()

     suite = get_suite(args[2].lower(), s)
     if suite is None: die("E: Can't find suite %s" % args[2].lower())

     for component_name in args[3:]:
         component = get_component(component_name.lower(), s)
         if component is None: die("E: Can't find component %s" % args[3].lower())

         try:
             suite.components.append(component)
             s.flush()
         except IntegrityError as e:
             die("E: Can't add suite-component entry (%s, %s) - probably already exists" % (args[2].lower(), component_name))
         except SQLAlchemyError as e:
             die("E: Can't add suite-component entry (%s, %s) - %s" % (args[2].lower(), component_name, e))

         print "Added suite-component entry for %s, %s" % (args[2].lower(), component_name)

     if not dryrun:
         s.commit()
     s.close()

def __suite_component_rm(d, args):
     if len(args) < 3:
         die("E: removing an suite-component entry requires a suite and component")

     s = d.session()
     if not dryrun:
         try:
             suite_name = args[2].lower()
             suite = get_suite(suite_name, s)
             if suite is None:
                 die('E: no such suite %s' % suite_name)
             component_string = args[3].lower()
             component = get_component(arch_string, s)
             if component not in suite.components:
                 die("E: component %s not found in suite %s" % (component_string, suite_name))
             suite.components.remove(component)
             s.commit()
         except IntegrityError as e:
             die("E: Can't remove suite-component entry (%s, %s) - it's probably referenced" % (args[2].lower(), args[3].lower()))
         except SQLAlchemyError as e:
             die("E: Can't remove suite-component entry (%s, %s) - %s" % (args[2].lower(), args[3].lower(), e))

     print "Removed suite-component entry for %s, %s" % (args[2].lower(), args[3].lower())


def suite_component(command):
    args = [str(x) for x in command]
    Cnf = utils.get_conf()
    d = DBConn()

    die_arglen(args, 2, "E: suite-component needs at least a command")

    mode = args[1].lower()

    if mode == 'list':
        __suite_component_list(d, args)
    elif mode == 'list-component':
        __suite_component_listcomponent(d, args)
    elif mode == 'list-suite':
        __suite_component_listsuite(d, args)
    elif mode == 'add':
        __suite_component_add(d, args)
    # elif mode == 'rm':
    #     __suite_architecture_rm(d, args)
    else:
        die("E: suite-component command unknown")

dispatch['suite-component'] = suite_component
dispatch['s-c'] = suite_component

################################################################################

def archive_list():
    session = DBConn().session()
    for archive in session.query(Archive).order_by(Archive.archive_name):
        print "{0} path={1} description={2} tainted={3}".format(archive.archive_name, archive.path, archive.description, archive.tainted)

def archive_add(args):
    (name, path, description) = args[0:3]

    attributes = dict(
        archive_name=name,
        path=path,
        description=description,
        )

    for option in args[3:]:
        (key, value) = option.split('=')
        attributes[key] = value

    session = DBConn().session()

    archive = Archive()
    for key, value in attributes.iteritems():
        setattr(archive, key, value)

    session.add(archive)
    session.flush()

    if dryrun:
        session.rollback()
    else:
        session.commit()

def archive_rm(name):
    session = DBConn().session()
    archive = get_archive(name, session)
    session.delete(archive)
    session.flush()

    if dryrun:
        session.rollback()
    else:
        session.commit()

def archive_rename(oldname, newname):
    session = DBConn().session()
    archive = get_archive(oldname, session)
    archive.archive_name = newname
    session.flush()

    if dryrun:
        session.rollback()
    else:
        session.commit()

def archive(command):
    mode = command[1]
    if mode == 'list':
        archive_list()
    elif mode == 'rename':
        archive_rename(command[2], command[3])
    elif mode == 'add':
        archive_add(command[2:])
    elif mode == 'rm':
        archive_rm(command[2])
    else:
        die("E: archive command unknown")

dispatch['archive'] = archive

################################################################################

def __version_check_list(d):
    session = d.session()
    for s in session.query(Suite).order_by(Suite.suite_name):
        __version_check_list_suite(d, s.suite_name)

def __version_check_list_suite(d, suite_name):
    vcs = get_version_checks(suite_name)
    for vc in vcs:
        print "%s %s %s" % (suite_name, vc.check, vc.reference.suite_name)

def __version_check_add(d, suite_name, check, reference_name):
    suite = get_suite(suite_name)
    if not suite:
        die("E: Could not find suite %s." % (suite_name))
    reference = get_suite(reference_name)
    if not reference:
        die("E: Could not find reference suite %s." % (reference_name))

    session = d.session()
    vc = VersionCheck()
    vc.suite = suite
    vc.check = check
    vc.reference = reference
    session.add(vc)
    session.commit()

def __version_check_rm(d, suite_name, check, reference_name):
    suite = get_suite(suite_name)
    if not suite:
        die("E: Could not find suite %s." % (suite_name))
    reference = get_suite(reference_name)
    if not reference:
        die("E: Could not find reference suite %s." % (reference_name))

    session = d.session()
    try:
      vc = session.query(VersionCheck).filter_by(suite=suite, check=check, reference=reference).one()
      session.delete(vc)
      session.commit()
    except NoResultFound:
      print "W: version-check not found."

def version_check(command):
    args = [str(x) for x in command]
    Cnf = utils.get_conf()
    d = DBConn()

    die_arglen(args, 2, "E: version-check needs at least a command")
    mode = args[1].lower()

    if mode == 'list':
        __version_check_list(d)
    elif mode == 'list-suite':
        if len(args) != 3:
            die("E: version-check list-suite needs a single parameter")
        __version_check_list_suite(d, args[2])
    elif mode == 'add':
        if len(args) != 5:
            die("E: version-check add needs three parameters")
        __version_check_add(d, args[2], args[3], args[4])
    elif mode == 'rm':
        if len(args) != 5:
            die("E: version-check rm needs three parameters")
        __version_check_rm(d, args[2], args[3], args[4])
    else:
        die("E: version-check command unknown")

dispatch['version-check'] = version_check
dispatch['v-c'] = version_check

################################################################################

def show_config(command):
    args = [str(x) for x in command]
    cnf = utils.get_conf()

    die_arglen(args, 2, "E: config needs at least a command")

    mode = args[1].lower()

    if mode == 'db':
        connstr = ""
        if cnf.has_key("DB::Service"):
            # Service mode
            connstr = "postgresql://service=%s" % cnf["DB::Service"]
        elif cnf.has_key("DB::Host"):
            # TCP/IP
            connstr = "postgres://%s" % cnf["DB::Host"]
            if cnf.has_key("DB::Port") and cnf["DB::Port"] != "-1":
                connstr += ":%s" % cnf["DB::Port"]
            connstr += "/%s" % cnf["DB::Name"]
        else:
            # Unix Socket
            connstr = "postgres:///%s" % cnf["DB::Name"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += "?port=%s" % cnf["DB::Port"]
        print connstr
    elif mode == 'db-shell':
        e = []
        if cnf.has_key("DB::Service"):
            e.append('PGSERVICE')
            print "PGSERVICE=%s" % cnf["DB::Service"]
        if cnf.has_key("DB::Name"):
            e.append('PGDATABASE')
            print "PGDATABASE=%s" % cnf["DB::Name"]
        if cnf.has_key("DB::Host"):
            print "PGHOST=%s" % cnf["DB::Host"]
            e.append('PGHOST')
        if cnf.has_key("DB::Port") and cnf["DB::Port"] != "-1":
            print "PGPORT=%s" % cnf["DB::Port"]
            e.append('PGPORT')
        print "export " + " ".join(e)
    elif mode == 'get':
        print cnf.get(args[2])
    else:
        session = DBConn().session()
        try:
            o = session.query(DBConfig).filter_by(name = mode).one()
            print o.value
        except NoResultFound:
            print "W: option '%s' not set" % mode

dispatch['config'] = show_config
dispatch['c'] = show_config

################################################################################

def show_keyring(command):
    args = [str(x) for x in command]
    cnf = utils.get_conf()

    die_arglen(args, 2, "E: keyring needs at least a command")

    mode = args[1].lower()

    d = DBConn()

    q = d.session().query(Keyring).filter(Keyring.active == True)

    if mode == 'list-all':
        pass
    elif mode == 'list-binary':
        q = q.join(Keyring.acl).filter(ACL.allow_source == False)
    elif mode == 'list-source':
        q = q.join(Keyring.acl).filter(ACL.allow_source == True)
    else:
        die("E: keyring command unknown")

    for k in q.all():
        print k.keyring_name

def keyring_add_buildd(command):
    name = command[2]
    arch_names = command[3:]

    session = DBConn().session()
    arches = session.query(Architecture).filter(Architecture.arch_string.in_(arch_names))

    acl = ACL()
    acl.name = 'buildd-{0}'.format('+'.join(arch_names))
    acl.architectures.update(arches)
    acl.allow_new = True
    acl.allow_binary = True
    acl.allow_binary_only = True
    acl.allow_hijack = True
    session.add(acl)

    k = Keyring()
    k.keyring_name = name
    k.acl = acl
    k.priority = 10
    session.add(k)

    session.commit()

def keyring(command):
    if command[1].startswith('list-'):
        show_keyring(command)
    elif command[1] == 'add-buildd':
        keyring_add_buildd(command)
    else:
        die("E: keyring command unknown")

dispatch['keyring'] = keyring
dispatch['k'] = keyring

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

    arguments = apt_pkg.parse_commandline(Cnf, arguments, sys.argv)

    options = Cnf.subtree("Admin::Options")
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
