#!/usr/bin/python

"""
Generate file lists for apt-ftparchive.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Torsten Werner <twerner@debian.org>
@copyright: 2011  Ansgar Burchardt <ansgar@debian.org>
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

# Ganneff> Please go and try to lock mhy now. After than try to lock NEW.
# twerner> !lock mhy
# dak> twerner: You suck, this is already locked by Ganneff
# Ganneff> now try with NEW
# twerner> !lock NEW
# dak> twerner: also locked NEW
# mhy> Ganneff: oy, stop using me for locks and highlighting me you tall muppet
# Ganneff> hehe :)

################################################################################

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils, daklog
from daklib.dakmultiprocessing import DakProcessPool, PROC_STATUS_SUCCESS, PROC_STATUS_SIGNALRAISED
import apt_pkg, os, stat, sys

from daklib.lists import getSources, getBinaries, getArchAll

def listPath(suite, component, architecture = None, type = None,
        incremental_mode = False):
    """returns full path to the list file"""
    suffixMap = { 'deb': "binary-",
                  'udeb': "debian-installer_binary-" }
    if architecture:
        suffix = suffixMap[type] + architecture.arch_string
    else:
        suffix = "source"
    filename = "%s_%s_%s.list" % \
        (suite.suite_name, component.component_name, suffix)
    pathname = os.path.join(Config()["Dir::Lists"], filename)
    file = utils.open_file(pathname, "a")
    timestamp = None
    if incremental_mode:
        timestamp = os.fstat(file.fileno())[stat.ST_MTIME]
    else:
        file.seek(0)
        file.truncate()
    return (file, timestamp)

def writeSourceList(suite_id, component_id, incremental_mode):
    session = DBConn().session()
    suite = Suite.get(suite_id, session)
    component = Component.get(component_id, session)
    (file, timestamp) = listPath(suite, component,
            incremental_mode = incremental_mode)

    message = "sources list for %s %s" % (suite.suite_name, component.component_name)

    for _, filename in getSources(suite, component, session, timestamp):
        file.write(filename + '\n')
    session.rollback()
    file.close()
    return (PROC_STATUS_SUCCESS, message)

def writeAllList(suite_id, component_id, architecture_id, type, incremental_mode):
    session = DBConn().session()
    suite = Suite.get(suite_id, session)
    component = Component.get(component_id, session)
    architecture = Architecture.get(architecture_id, session)
    (file, timestamp) = listPath(suite, component, architecture, type,
            incremental_mode)

    message = "all list for %s %s (arch=%s, type=%s)" % (suite.suite_name, component.component_name, architecture.arch_string, type)

    for _, filename in getArchAll(suite, component, architecture, type,
            session, timestamp):
        file.write(filename + '\n')
    session.rollback()
    file.close()
    return (PROC_STATUS_SUCCESS, message)

def writeBinaryList(suite_id, component_id, architecture_id, type, incremental_mode):
    session = DBConn().session()
    suite = Suite.get(suite_id, session)
    component = Component.get(component_id, session)
    architecture = Architecture.get(architecture_id, session)
    (file, timestamp) = listPath(suite, component, architecture, type,
            incremental_mode)

    message = "binary list for %s %s (arch=%s, type=%s)" % (suite.suite_name, component.component_name, architecture.arch_string, type)

    for _, filename in getBinaries(suite, component, architecture, type,
            session, timestamp):
        file.write(filename + '\n')
    session.rollback()
    file.close()
    return (PROC_STATUS_SUCCESS, message)

def usage():
    print """Usage: dak generate_filelist [OPTIONS]
Create filename lists for apt-ftparchive.

  -s, --suite=SUITE            act on this suite
  -c, --component=COMPONENT    act on this component
  -a, --architecture=ARCH      act on this architecture
  -h, --help                   show this help and exit
  -i, --incremental            activate incremental mode

ARCH, COMPONENT and SUITE can be comma (or space) separated list, e.g.
    --suite=testing,unstable

Incremental mode appends only newer files to existing lists."""
    sys.exit()

def main():
    cnf = Config()
    Logger = daklog.Logger('generate-filelist')
    Arguments = [('h', "help",         "Filelist::Options::Help"),
                 ('s', "suite",        "Filelist::Options::Suite", "HasArg"),
                 ('c', "component",    "Filelist::Options::Component", "HasArg"),
                 ('a', "architecture", "Filelist::Options::Architecture", "HasArg"),
                 ('i', "incremental",  "Filelist::Options::Incremental")]
    session = DBConn().session()
    query_suites = session.query(Suite)
    suites = [suite.suite_name for suite in query_suites]
    if not cnf.has_key('Filelist::Options::Suite'):
        cnf['Filelist::Options::Suite'] = ','.join(suites).encode()
    query_components = session.query(Component)
    components = \
        [component.component_name for component in query_components]
    if not cnf.has_key('Filelist::Options::Component'):
        cnf['Filelist::Options::Component'] = ','.join(components).encode()
    query_architectures = session.query(Architecture)
    architectures = \
        [architecture.arch_string for architecture in query_architectures]
    if not cnf.has_key('Filelist::Options::Architecture'):
        cnf['Filelist::Options::Architecture'] = ','.join(architectures).encode()
    cnf['Filelist::Options::Help'] = ''
    cnf['Filelist::Options::Incremental'] = ''
    apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("Filelist::Options")
    if Options['Help']:
        usage()
    pool = DakProcessPool()
    query_suites = query_suites. \
        filter(Suite.suite_name.in_(utils.split_args(Options['Suite'])))
    query_components = query_components. \
        filter(Component.component_name.in_(utils.split_args(Options['Component'])))
    query_architectures = query_architectures. \
        filter(Architecture.arch_string.in_(utils.split_args(Options['Architecture'])))

    def parse_results(message):
        # Split out into (code, msg)
        code, msg = message
        if code == PROC_STATUS_SUCCESS:
            Logger.log([msg])
        elif code == PROC_STATUS_SIGNALRAISED:
            Logger.log(['E: Subprocess recieved signal ', msg])
        else:
            Logger.log(['E: ', msg])

    for suite in query_suites:
        suite_id = suite.suite_id
        for component in query_components:
            component_id = component.component_id
            for architecture in query_architectures:
                architecture_id = architecture.arch_id
                if architecture not in suite.architectures:
                    pass
                elif architecture.arch_string == 'source':
                    pool.apply_async(writeSourceList,
                        (suite_id, component_id, Options['Incremental']), callback=parse_results)
                elif architecture.arch_string == 'all':
                    pool.apply_async(writeAllList,
                        (suite_id, component_id, architecture_id, 'deb',
                            Options['Incremental']), callback=parse_results)
                    pool.apply_async(writeAllList,
                        (suite_id, component_id, architecture_id, 'udeb',
                            Options['Incremental']), callback=parse_results)
                else: # arch any
                    pool.apply_async(writeBinaryList,
                        (suite_id, component_id, architecture_id, 'deb',
                            Options['Incremental']), callback=parse_results)
                    pool.apply_async(writeBinaryList,
                        (suite_id, component_id, architecture_id, 'udeb',
                            Options['Incremental']), callback=parse_results)
    pool.close()
    pool.join()

    # this script doesn't change the database
    session.close()

    Logger.close()

    sys.exit(pool.overall_status())

if __name__ == '__main__':
    main()

