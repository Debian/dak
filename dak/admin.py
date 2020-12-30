#! /usr/bin/env python3

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

import collections
import json
import six
import sys

import apt_pkg

import daklib.archive
import daklib.gpg

from daklib import utils
from daklib.dbconn import *
from sqlalchemy.orm.exc import NoResultFound

################################################################################

dispatch = {}
dryrun = False

################################################################################


def warn(msg):
    print(msg, file=sys.stderr)


def die(msg, exit_code=1):
    print(msg, file=sys.stderr)
    sys.exit(exit_code)


def die_arglen(args, args_needed, msg):
    if len(args) < args_needed:
        die(msg)


def get_suite_or_die(suite_name, session=None, error_message=None):
    suite = get_suite(suite_name.lower(), session=session)
    if suite is None:
        if error_message is None:
            error_message = "E: Invalid/unknown suite %(suite_name)s"
        die(error_message % {'suite_name': suite_name})
    return suite


def usage(exit_code=0):
    """Perform administrative work on the dak database."""

    print("""Usage: dak admin COMMAND
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
     s rm SUITE             remove a suite (will only work if empty)

     s add-all-arches SUITE VERSION... as "s add" but adds suite-architecture
                            relationships for all architectures
     s add-build-queue SUITE BUILD-QUEUE BUILD-QUEUE-CODENAME BUILD-QUEUE-ARCHIVE
                            add a build queue for an existing suite

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

  suite-config / suite-cfg / s-cfg:
     s-cfg list             show the names of the configurations
     s-cfg list SUITE       show the configuration values for SUITE
     s-cfg list-json SUITE  show the configuration values for SUITE in JSON format
     s-cfg get SUITE NAME ...
                            show the value for NAME in SUITE (format: NAME=VALUE)
     s-cfg get-value SUITE NAME ...
                            show the value for NAME in SUITE (format: VALUE)
     s-cfg get-json SUITE NAME ...
                            show the value for NAME in SUITE (format: JSON object)
     s-cfg set SUITE NAME=VALUE ...
                            set NAME to VALUE in SUITE
     s-cfg set-json SUITE
     s-cfg set-json SUITE FILENAME
                            parse FILENAME (if absent or "-", then stdin) as JSON
                            and update all configurations listed to match the
                            value in the JSON.
                            Uses the same format as list-json or get-json outputs.

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

  change-component:
     change-component SUITE COMPONENT source SOURCE...
     change-component SUITE COMPONENT binary BINARY...
         Move source or binary packages to a different component by copying
         associated files and changing the overrides.

  forget-signature FILE:    forget that we saw FILE
""")
    sys.exit(exit_code)

################################################################################


def __architecture_list(d, args):
    q = d.session().query(Architecture).order_by(Architecture.arch_string)
    for j in q.all():
        # HACK: We should get rid of source from the arch table
        if j.arch_string == 'source':
            continue
        print(j.arch_string)
    sys.exit(0)


def __architecture_add(d, args):
    die_arglen(args, 4, "E: adding an architecture requires a name and a description")
    print("Adding architecture %s" % args[2])
    suites = [str(x) for x in args[4:]]
    if len(suites) > 0:
        print("Adding to suites %s" % ", ".join(suites))
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
    print("Architecture %s added" % (args[2]))


def __architecture_rm(d, args):
    die_arglen(args, 3, "E: removing an architecture requires at least a name")
    print("Removing architecture %s" % args[2])
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
    print("Architecture %s removed" % args[2])


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
        print("{0} ordering={1}".format(component.component_name, component.ordering))


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
    for key, value in attributes.items():
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
            print("{0} {1}".format(j.archive.archive_name, j.suite_name))
        else:
            print("{0}".format(j.suite_name))


def __suite_show(d, args):
    if len(args) < 2:
        die("E: showing an suite entry requires a suite")

    s = d.session()
    su = get_suite_or_die(args[2])

    print(su.details())


def __suite_add(d, args, addallarches=False):
    die_arglen(args, 4, "E: adding a suite requires at least a name and a version")
    suite_name = args[2].lower()
    version = args[3]
    kvpairs = __suite_config_set_confing_args_as_dict(args[4:])

    if len(version) == 0:
        version = None

    print("Adding suite %s" % suite_name)
    if not dryrun:
        try:
            s = d.session()
            suite = Suite()
            suite.suite_name = suite_name
            suite.overridecodename = None
            suite.version = version or None
            # Most configurations will be handled by
            # __suite_config_internal_set.  However, a few are managed
            # manually here because __suite_config_internal_set cannot
            # handle them.  Either because they are create-only or
            # because suite-add handled them different (historically)
            suite.codename = kvpairs.pop('codename', None)
            signingkey = kvpairs.pop('signingkey', None)
            if signingkey is not None:
                suite.signingkeys = [signingkey.upper()]
            archive_name = kvpairs.pop('archive', None)
            if archive_name is not None:
                suite.archive = get_archive(archive_name, s)
            else:
                suite.archive = s.query(Archive).filter(~Archive.archive_name.in_(['build-queues', 'new', 'policy'])).one()
            suite.srcformats = s.query(SrcFormat).all()
            __suite_config_internal_set(suite, suite_name, kvpairs,
                                        print_config_set=False)
            s.add(suite)
            s.flush()
        except IntegrityError as e:
            die("E: Integrity error adding suite %s (it probably already exists)" % suite_name)
        except SQLAlchemyError as e:
            die("E: Error adding suite %s (%s)" % (suite_name, e))
    print("Suite %s added" % (suite_name))

    if addallarches:
        arches = []
        q = s.query(Architecture).order_by(Architecture.arch_string)
        for arch in q.all():
            suite.architectures.append(arch)
            arches.append(arch.arch_string)

        print("Architectures %s added to %s" % (','.join(arches), suite_name))

    s.commit()


def __suite_rm(d, args):
    die_arglen(args, 3, "E: removing a suite requires at least a name")
    name = args[2]
    print("Removing suite {0}".format(name))
    if not dryrun:
        try:
            s = d.session()
            su = get_suite_or_die(name, s)
            s.delete(su)
            s.commit()
        except IntegrityError as e:
            die("E: Integrity error removing suite {0} (suite-arch entries probably still exist)".format(name))
        except SQLAlchemyError as e:
            die("E: Error removing suite {0} ({1})".format(name, e))
    print("Suite {0} removed".format(name))


def __suite_add_build_queue(d, args):
    session = d.session()

    die_arglen(args, 6, "E: Adding a build queue needs four parameters.")

    suite_name = args[2]
    build_queue_name = args[3]
    build_queue_codename = args[4]
    build_queue_archive_name = args[5]
    try:
        suite = session.query(Suite).filter_by(suite_name=suite_name).one()
    except NoResultFound:
        die("E: Unknown suite '{0}'".format(suite_name))
    try:
        build_queue_archive = session.query(Archive).filter_by(archive_name=build_queue_archive_name).one()
    except NoResultFound:
        die("E: Unknown archive '{0}'".format(build_queue_archive_name))

    # Create suite
    s = Suite()
    s.suite_name = build_queue_name
    s.origin = suite.origin
    s.label = suite.label
    s.description = "buildd {0} incoming".format(suite_name)
    s.codename = build_queue_codename
    s.notautomatic = suite.notautomatic
    s.overridesuite = suite.overridesuite or suite.suite_name
    s.butautomaticupgrades = suite.butautomaticupgrades
    s.signingkeys = suite.signingkeys
    s.include_long_description = False

    # Do not accept direct uploads to the build queue
    s.accept_source_uploads = False
    s.accept_binary_uploads = False

    s.archive = build_queue_archive
    s.architectures.extend(suite.architectures)
    s.components.extend(suite.components)
    s.srcformats.extend(suite.srcformats)

    session.add(s)
    session.flush()

    bq = BuildQueue()
    bq.queue_name = build_queue_codename
    bq.suite = s

    session.add(bq)
    session.flush()

    suite.copy_queues.append(bq)

    session.commit()


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
    elif mode == 'add-build-queue':
        __suite_add_build_queue(d, args)
    else:
        die("E: suite command unknown")


dispatch['suite'] = suite
dispatch['s'] = suite

################################################################################


def __suite_architecture_list(d, args):
    s = d.session()
    for j in s.query(Suite).order_by(Suite.suite_name):
        architectures = j.get_architectures(skipsrc=True, skipall=True)
        print(j.suite_name + ': '
              + ', '.join([a.arch_string for a in architectures]))


def __suite_architecture_listarch(d, args):
    die_arglen(args, 3, "E: suite-architecture list-arch requires a suite")
    suite = get_suite_or_die(args[2], d.session())
    a = suite.get_architectures(skipsrc=True, skipall=True)
    for j in a:
        print(j.arch_string)


def __suite_architecture_listsuite(d, args):
    die_arglen(args, 3, "E: suite-architecture list-suite requires an arch")
    architecture = get_architecture(args[2].lower(), d.session())
    if architecture is None:
        die("E: architecture %s is invalid" % args[2].lower())
    for j in architecture.suites:
        print(j.suite_name)


def __suite_architecture_add(d, args):
    if len(args) < 3:
        die("E: adding a suite-architecture entry requires a suite and arch")

    s = d.session()

    suite = get_suite_or_die(args[2], s)

    for arch_name in args[3:]:
        arch = get_architecture(arch_name.lower(), s)
        if arch is None:
            die("E: Can't find architecture %s" % args[3].lower())

        try:
            suite.architectures.append(arch)
            s.flush()
        except IntegrityError as e:
            die("E: Can't add suite-architecture entry (%s, %s) - probably already exists" % (args[2].lower(), arch_name))
        except SQLAlchemyError as e:
            die("E: Can't add suite-architecture entry (%s, %s) - %s" % (args[2].lower(), arch_name, e))

        print("Added suite-architecture entry for %s, %s" % (args[2].lower(), arch_name))

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
            suite = get_suite_or_die(suite_name, s)
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

    print("Removed suite-architecture entry for %s, %s" % (args[2].lower(), args[3].lower()))


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
        print(j.suite_name + ': '
              + ', '.join([c.component_name for c in components]))


def __suite_component_listcomponent(d, args):
    die_arglen(args, 3, "E: suite-component list-component requires a suite")
    suite = get_suite_or_die(args[2], d.session())
    for c in suite.components:
        print(c.component_name)


def __suite_component_listsuite(d, args):
    die_arglen(args, 3, "E: suite-component list-suite requires an component")
    component = get_component(args[2].lower(), d.session())
    if component is None:
        die("E: component %s is invalid" % args[2].lower())
    for s in component.suites:
        print(s.suite_name)


def __suite_component_add(d, args):
    if len(args) < 3:
        die("E: adding a suite-component entry requires a suite and component")

    s = d.session()

    suite = get_suite_or_die(args[2], s)

    for component_name in args[3:]:
        component = get_component(component_name.lower(), s)
        if component is None:
            die("E: Can't find component %s" % args[3].lower())

        try:
            suite.components.append(component)
            s.flush()
        except IntegrityError as e:
            die("E: Can't add suite-component entry (%s, %s) - probably already exists" % (args[2].lower(), component_name))
        except SQLAlchemyError as e:
            die("E: Can't add suite-component entry (%s, %s) - %s" % (args[2].lower(), component_name, e))

        print("Added suite-component entry for %s, %s" % (args[2].lower(), component_name))

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
            suite = get_suite_or_die(suite_name, s)
            component_string = args[3].lower()
            component = get_component(component_string, s)
            if component not in suite.components:
                die("E: component %s not found in suite %s" % (component_string, suite_name))
            suite.components.remove(component)
            s.commit()
        except IntegrityError as e:
            die("E: Can't remove suite-component entry (%s, %s) - it's probably referenced" % (args[2].lower(), args[3].lower()))
        except SQLAlchemyError as e:
            die("E: Can't remove suite-component entry (%s, %s) - %s" % (args[2].lower(), args[3].lower(), e))

    print("Removed suite-component entry for %s, %s" % (args[2].lower(), args[3].lower()))


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

# Sentinel for detecting read-only configurations
SUITE_CONFIG_READ_ONLY = object()
SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON = object()


SuiteConfigSerializer = collections.namedtuple('SuiteConfigSerializer', ['db_name', 'serialize', 'deserialize'])


def _serialize_suite(x):
    if x is None:
        return None
    return Suite.get(x).suite_name


def _deserialize_suite(x):
    if x is None:
        return None
    return get_suite_or_die(x).suite_id


@session_wrapper
def _serialize_policy_queue(x, session=None):
    if x is None:
        return None
    try:
        policy_obj = session.query(PolicyQueue).filter_by(policy_queue_id=x).one()
    except NoResultFound:
        return None
    return policy_obj.queue_name


def _deserialize_policy_queue(x):
    if x is None:
        return None
    policy_queue = get_policy_queue(x)
    if policy_queue is None:
        raise ValueError("There is no policy queue with name %s" % x)
    return policy_queue.policy_queue_id


@session_wrapper
def _serialize_archive(x, session=None):
    if x is None:
        return None
    try:
        archive_obj = session.query(Archive).filter_by(archive_id=x).one()
    except NoResultFound:
        return None
    return archive_obj.archive_name


CUSTOM_SUITE_CONFIG_SERIALIZERS = {
    'archive': SuiteConfigSerializer(db_name='archive_id', serialize=_serialize_archive,
                                     deserialize=None),
    'debugsuite': SuiteConfigSerializer(db_name='debugsuite_id', serialize=_serialize_suite,
                                        deserialize=_deserialize_suite),
    'new_queue': SuiteConfigSerializer(db_name='new_queue_id', serialize=_serialize_policy_queue,
                                       deserialize=_deserialize_policy_queue),
    'policy_queue': SuiteConfigSerializer(db_name='policy_queue_id', serialize=_serialize_policy_queue,
                                          deserialize=_deserialize_policy_queue),
}


ALLOWED_SUITE_CONFIGS = {
    'accept_binary_uploads': utils.parse_boolean_from_user,
    'accept_source_uploads': utils.parse_boolean_from_user,
    'allowcsset': utils.parse_boolean_from_user,
    'announce': SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON,
    'archive': SUITE_CONFIG_READ_ONLY,
    'butautomaticupgrades': utils.parse_boolean_from_user,
    'byhash': utils.parse_boolean_from_user,
    'changelog': str,
    'changelog_url': str,
    'checksums': SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON,
    'codename': SUITE_CONFIG_READ_ONLY,
    'debugsuite': str,
    'description': str,
    'include_long_description': utils.parse_boolean_from_user,
    'indices_compression': SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON,
    'label': str,
    'mail_whitelist': str,
    'merged_pdiffs': utils.parse_boolean_from_user,
    'new_queue': str,
    'notautomatic': utils.parse_boolean_from_user,
    'origin': str,
    'overridecodename': str,
    'overrideorigin': str,
    'overrideprocess': utils.parse_boolean_from_user,
    'overridesuite': str,
    'policy_queue': str,
    'priority': int,
    'separate_contents_architecture_all': utils.parse_boolean_from_user,
    # We do not support separate Packages-all, so do not let people set it.
    'separate_packages_architecture_all': SUITE_CONFIG_READ_ONLY,
    'signingkeys': SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON,
    'suite_name': SUITE_CONFIG_READ_ONLY,
    'untouchable': utils.parse_boolean_from_user,
    'validtime': int,
}


def _get_suite_value(suite, conf_name):
    serial_config = CUSTOM_SUITE_CONFIG_SERIALIZERS.get(conf_name)
    if serial_config is None:
        return getattr(suite, conf_name)
    db_value = getattr(suite, serial_config.db_name)
    return serial_config.serialize(db_value)


def _set_suite_value(suite, conf_name, new_value):
    serial_config = CUSTOM_SUITE_CONFIG_SERIALIZERS.get(conf_name)
    db_name = conf_name
    if serial_config is not None:
        assert serial_config.deserialize is not None, "Changing %s is not supported!" % conf_name
        new_value = serial_config.deserialize(new_value)
        db_name = serial_config.db_name
    setattr(suite, db_name, new_value)


def __suite_config_get(d, args, direct_value=False, json_format=False):
    die_arglen(args, 4, "E: suite-config get needs the name of a configuration")
    session = d.session()
    suite_name = args[2]
    suite = get_suite_or_die(suite_name, session)
    values = {}
    for arg in args[3:]:
        if arg not in ALLOWED_SUITE_CONFIGS:
            die("Unknown (or unsupported) suite configuration variable")
        value = _get_suite_value(suite, arg)
        if json_format:
            values[arg] = value
        elif direct_value:
            print(value)
        else:
            print("%s=%s" % (arg, value))
    if json_format:
        print(json.dumps(values, indent=2, sort_keys=True))


def __suite_config_set(d, args):
    die_arglen(args, 4, "E: suite-config set needs the name of a configuration")
    session = d.session()
    suite_name = args[2]
    suite = get_suite_or_die(suite_name, session)
    args_as_kvpairs = __suite_config_set_confing_args_as_dict(args[3:])
    __suite_config_internal_set(suite, suite_name, args_as_kvpairs,
                                print_config_set=True
                                )
    if dryrun:
        session.rollback()
        print()
        print("This was a dryrun; changes have been rolled back")
    else:
        session.commit()


def __suite_config_set_confing_args_as_dict(args):
    # Use OrderedDict to preserve order (makes "dak admin suite-config set ..."
    # less confusing when things are processed in the input order)
    kvpairs = collections.OrderedDict()
    for arg in args:
        if '=' not in arg:
            die("Missing value for configuration %s: Use key=value format" % arg)
        conf_name, new_value_str = arg.split('=', 1)
        kvpairs[conf_name] = new_value_str
    return kvpairs


def __suite_config_internal_set(suite, suite_name, kvpairs, print_config_set=True):
    for kvpair in kvpairs.items():
        conf_name, new_value_str = kvpair
        cli_parser = ALLOWED_SUITE_CONFIGS.get(conf_name)
        if cli_parser is None:
            die("Unknown (or unsupported) suite configuration variable")
        if cli_parser in (SUITE_CONFIG_READ_ONLY, SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON):
            if cli_parser == SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON:
                msg = "Cannot parse value for %s" \
                      ''' - set via echo '{"%s": <...>}' | dak suite-config set-json %s instead'''
                warn(msg % (conf_name, conf_name, suite_name))
            die("Cannot change %s from the command line" % conf_name)
        try:
            new_value = cli_parser(new_value_str)
        except (RuntimeError, ValueError, TypeError) as e:
            warn("Could not parse new value for %s (given: %s)" % (conf_name, new_value_str))
            raise e
        try:
            _set_suite_value(suite, conf_name, new_value)
        except (RuntimeError, ValueError, TypeError) as e:
            warn("Could not set new value for %s (given: %s)" % (conf_name, new_value))
            raise e
        if print_config_set:
            print("%s=%s" % (conf_name, _get_suite_value(suite, conf_name)))


def __suite_config_set_json(d, args):
    session = d.session()
    suite_name = args[2]
    suite = get_suite_or_die(suite_name, session)
    filename = '-'
    if len(args) > 3:
        if len(args) > 4:
            warn("W: Ignoring extra argument after the json file name")
        filename = args[3]
    if filename != '-':
        with open(filename) as fd:
            update_config = json.load(fd)
    else:
        update_config = json.load(sys.stdin)
    if update_config is None or not isinstance(update_config, dict):
        die("E: suite-config set-json expects a dictionary (json object), got %s" % type(update_config))

    for conf_name in sorted(update_config):
        new_value = update_config[conf_name]
        cli_parser = ALLOWED_SUITE_CONFIGS.get(conf_name)
        if cli_parser is None:
            die("Unknown (or unsupported) suite configuration variable: %s" % conf_name)
        if cli_parser is SUITE_CONFIG_READ_ONLY:
            die("Cannot change %s via JSON" % conf_name)
        try:
            _set_suite_value(suite, conf_name, new_value)
        except (RuntimeError, ValueError, TypeError) as e:
            warn("Could not set new value for %s (given: %s)" % (conf_name, new_value))
            raise e
        print("%s=%s" % (conf_name, _get_suite_value(suite, conf_name)))
    if dryrun:
        session.rollback()
        print()
        print("This was a dryrun; changes have been rolled back")
    else:
        session.commit()


def __suite_config_list(d, args, json_format=False):
    suite = None
    session = d.session()
    if len(args) > 3:
        warn("W: Ignoring extra argument after the suite name")
    if len(args) == 3:
        suite_name = args[2]
        suite = get_suite_or_die(suite_name, session)
    else:
        if json_format:
            die("E: suite-config list-json requires a suite name!")
        print("Valid suite-config options manageable by this command:")
        print()
    values = {}

    for arg in sorted(ALLOWED_SUITE_CONFIGS):
        mode = 'writable'
        if suite is not None:
            value = _get_suite_value(suite, arg)
            if json_format:
                values[arg] = value
            else:
                print("%s=%s" % (arg, value))
        else:
            converter = ALLOWED_SUITE_CONFIGS[arg]
            if converter is SUITE_CONFIG_READ_ONLY:
                mode = 'read-only'
            elif converter is SUITE_CONFIG_WRITABLE_ONLY_VIA_JSON:
                mode = 'writeable (via set-json only)'
            print(" * %s (%s)" % (arg, mode))
    if json_format:
        print(json.dumps(values, indent=2, sort_keys=True))


def suite_config(command):
    args = [six.ensure_text(x) for x in command]
    Cnf = utils.get_conf()
    d = DBConn()

    die_arglen(args, 2, "E: suite-config needs a command")
    mode = args[1].lower()

    if mode in {'get', 'get-value', 'get-json'}:
        direct_value = False
        json_format = mode == 'get-json'
        if mode == 'get-value':
            direct_value = True
            if len(args) > 4:
                die("E: get-value must receive exactly one key to lookup")
        __suite_config_get(d, args, direct_value=direct_value, json_format=json_format)
    elif mode == 'set':
        __suite_config_set(d, args)
    elif mode == 'set-json':
        __suite_config_set_json(d, args)
    elif mode in {'list', 'list-json'}:
        json_format = mode == 'list-json'
        __suite_config_list(d, args, json_format=json_format)
    else:
        suite = get_suite(mode, d.session())
        if suite is not None:
            warn("Did you get the order of the suite and the subcommand wrong?")
        warn("Syntax: dak admin %s {get,set,...} <suite>" % args[0])
        die("E: suite-config command unknown")


dispatch['suite-config'] = suite_config
dispatch['suite-cfg'] = suite_config
dispatch['s-cfg'] = suite_config


################################################################################


def archive_list():
    session = DBConn().session()
    for archive in session.query(Archive).order_by(Archive.archive_name):
        print("{0} path={1} description={2} tainted={3}".format(archive.archive_name, archive.path, archive.description, archive.tainted))


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
    for key, value in attributes.items():
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
        print("%s %s %s" % (suite_name, vc.check, vc.reference.suite_name))


def __version_check_add(d, suite_name, check, reference_name):
    suite = get_suite_or_die(suite_name,
                             error_message="E: Could not find suite %(suite_name)s")
    reference = get_suite_or_die(reference_name,
                             error_message="E: Could not find reference suite %(suite_name)s")

    session = d.session()
    vc = VersionCheck()
    vc.suite = suite
    vc.check = check
    vc.reference = reference
    session.add(vc)
    session.commit()


def __version_check_rm(d, suite_name, check, reference_name):
    suite = get_suite_or_die(suite_name,
                             error_message="E: Could not find suite %(suite_name)s")
    reference = get_suite_or_die(reference_name,
                             error_message="E: Could not find reference suite %(suite_name)s")

    session = d.session()
    try:
        vc = session.query(VersionCheck).filter_by(suite=suite, check=check, reference=reference).one()
        session.delete(vc)
        session.commit()
    except NoResultFound:
        print("W: version-check not found.")


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
        if "DB::Service" in cnf:
            # Service mode
            connstr = "postgresql://service=%s" % cnf["DB::Service"]
        elif "DB::Host" in cnf:
            # TCP/IP
            connstr = "postgresql://%s" % cnf["DB::Host"]
            if "DB::Port" in cnf and cnf["DB::Port"] != "-1":
                connstr += ":%s" % cnf["DB::Port"]
            connstr += "/%s" % cnf["DB::Name"]
        else:
            # Unix Socket
            connstr = "postgresql:///%s" % cnf["DB::Name"]
            if cnf["DB::Port"] and cnf["DB::Port"] != "-1":
                connstr += "?port=%s" % cnf["DB::Port"]
        print(connstr)
    elif mode == 'db-shell':
        e = []
        if "DB::Service" in cnf:
            e.append('PGSERVICE')
            print("PGSERVICE=%s" % cnf["DB::Service"])
        if "DB::Name" in cnf:
            e.append('PGDATABASE')
            print("PGDATABASE=%s" % cnf["DB::Name"])
        if "DB::Host" in cnf:
            print("PGHOST=%s" % cnf["DB::Host"])
            e.append('PGHOST')
        if "DB::Port" in cnf and cnf["DB::Port"] != "-1":
            print("PGPORT=%s" % cnf["DB::Port"])
            e.append('PGPORT')
        print("export " + " ".join(e))
    elif mode == 'get':
        print(cnf.get(args[2]))
    else:
        session = DBConn().session()
        try:
            o = session.query(DBConfig).filter_by(name=mode).one()
            print(o.value)
        except NoResultFound:
            print("W: option '%s' not set" % mode)


dispatch['config'] = show_config
dispatch['c'] = show_config

################################################################################


def show_keyring(command):
    args = [str(x) for x in command]
    cnf = utils.get_conf()

    die_arglen(args, 2, "E: keyring needs at least a command")

    mode = args[1].lower()

    d = DBConn()

    q = d.session().query(Keyring).filter(Keyring.active == True)  # noqa:E712

    if mode == 'list-all':
        pass
    elif mode == 'list-binary':
        q = q.join(Keyring.acl).filter(ACL.allow_source == False)  # noqa:E712
    elif mode == 'list-source':
        q = q.join(Keyring.acl).filter(ACL.allow_source == True)  # noqa:E712
    else:
        die("E: keyring command unknown")

    for k in q.all():
        print(k.keyring_name)


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


def change_component_source(transaction, suite, component, source_names):
    session = transaction.session

    overrides = session.query(Override).filter(Override.package.in_(source_names)).filter_by(suite=suite).join(OverrideType).filter_by(overridetype='dsc')
    for override in overrides:
        print("Changing override for {0}".format(override.package))
        override.component = component
    session.flush()

    sources = session.query(DBSource).filter(DBSource.source.in_(source_names)).filter(DBSource.suites.contains(suite))
    for source in sources:
        print("Copying {0}={1}".format(source.source, source.version))
        transaction.copy_source(source, suite, component)


def change_component_binary(transaction, suite, component, binary_names):
    session = transaction.session

    overrides = session.query(Override).filter(Override.package.in_(binary_names)).filter_by(suite=suite).join(OverrideType).filter(OverrideType.overridetype.in_(['deb', 'udeb']))
    for override in overrides:
        print("Changing override for {0}".format(override.package))
        override.component = component
    session.flush()

    binaries = session.query(DBBinary).filter(DBBinary.package.in_(binary_names)).filter(DBBinary.suites.contains(suite))
    for binary in binaries:
        print("Copying {0}={1} [{2}]".format(binary.package, binary.version, binary.architecture.arch_string))
        transaction.copy_binary(binary, suite, component)
    pass


def change_component(args):
    with daklib.archive.ArchiveTransaction() as transaction:
        session = transaction.session

        suite = session.query(Suite).filter_by(suite_name=args[1]).one()
        component = session.query(Component).filter_by(component_name=args[2]).one()

        if args[3] == 'source':
            change_component_source(transaction, suite, component, args[4:])
        elif args[3] == 'binary':
            change_component_binary(transaction, suite, component, args[4:])
        else:
            raise Exception("Can only move source or binary, not {0}".format(args[3]))

        transaction.commit()


dispatch['change-component'] = change_component

################################################################################


def forget_signature(args):
    filename = args[1]
    with open(filename, 'rb') as fh:
        data = fh.read()

    session = DBConn().session()
    keyrings = [k.keyring_name for k in session.query(Keyring).filter_by(active=True).order_by(Keyring.priority)]
    signed_file = daklib.gpg.SignedFile(data, keyrings)
    history = SignatureHistory.from_signed_file(signed_file).query(session)
    if history is not None:
        session.delete(history)
        session.commit()
    else:
        print("Signature was not known to dak.")
    session.rollback()


dispatch['forget-signature'] = forget_signature

################################################################################


def main():
    """Perform administrative work on the dak database"""
    global dryrun
    Cnf = utils.get_conf()
    arguments = [('h', "help", "Admin::Options::Help"),
                 ('n', "dry-run", "Admin::Options::Dry-Run")]
    for i in ["help", "dry-run"]:
        key = "Admin::Options::%s" % i
        if key not in Cnf:
            Cnf[key] = ""

    arguments = apt_pkg.parse_commandline(Cnf, arguments, sys.argv)

    options = Cnf.subtree("Admin::Options")
    if options["Help"] or len(arguments) < 1:
        usage()
    if options["Dry-Run"]:
        dryrun = True

    subcommand = str(arguments[0])

    if subcommand in dispatch:
        dispatch[subcommand](arguments)
    else:
        die("E: Unknown command")

################################################################################


if __name__ == '__main__':
    main()
