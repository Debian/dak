#!/usr/bin/python

"""
Generate file lists for apt-ftparchive.

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2009  Torsten Werner <twerner@debian.org>
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
from daklib.threadpool import ThreadPool
from daklib import utils
import apt_pkg, os, stat, sys

def fetch(query, args, session):
    return [path + filename for (path, filename) in \
        session.execute(query, args).fetchall()]

def getSources(suite, component, session, timestamp):
    extra_cond = ""
    if timestamp:
        extra_cond = "AND extract(epoch from sa.created) > %d" % timestamp
    query = """
        SELECT l.path, f.filename
            FROM source s
            JOIN src_associations sa
                ON s.id = sa.source AND sa.suite = :suite %s
            JOIN files f
                ON s.file = f.id
            JOIN location l
                ON f.location = l.id AND l.component = :component
            ORDER BY filename
    """ % extra_cond
    args = { 'suite': suite.suite_id,
             'component': component.component_id }
    return fetch(query, args, session)

def getBinaries(suite, component, architecture, type, session, timestamp):
    extra_cond = ""
    if timestamp:
        extra_cond = "AND extract(epoch from ba.created) > %d" % timestamp
    query = """
CREATE TEMP TABLE b_candidates (
    source integer,
    file integer,
    architecture integer);

INSERT INTO b_candidates (source, file, architecture)
    SELECT b.source, b.file, b.architecture
        FROM binaries b
        JOIN bin_associations ba ON b.id = ba.bin
        WHERE b.type = :type AND ba.suite = :suite AND
            b.architecture IN (2, :architecture) %s;

CREATE TEMP TABLE gf_candidates (
    filename text,
    path text,
    architecture integer,
    src integer,
    source text);

INSERT INTO gf_candidates (filename, path, architecture, src, source)
    SELECT f.filename, l.path, bc.architecture, bc.source as src, s.source
        FROM b_candidates bc
        JOIN source s ON bc.source = s.id
        JOIN files f ON bc.file = f.id
        JOIN location l ON f.location = l.id
        WHERE l.component = :component;

WITH arch_any AS

    (SELECT path, filename FROM gf_candidates
        WHERE architecture > 2),

     arch_all_with_any AS
    (SELECT path, filename FROM gf_candidates
        WHERE architecture = 2 AND
              src IN (SELECT src FROM gf_candidates WHERE architecture > 2)),

     arch_all_without_any AS
    (SELECT path, filename FROM gf_candidates
        WHERE architecture = 2 AND
              source NOT IN (SELECT DISTINCT source FROM gf_candidates WHERE architecture > 2)),

     filelist AS
    (SELECT * FROM arch_any
    UNION
    SELECT * FROM arch_all_with_any
    UNION
    SELECT * FROM arch_all_without_any)

    SELECT * FROM filelist ORDER BY filename
    """ % extra_cond
    args = { 'suite': suite.suite_id,
             'component': component.component_id,
             'architecture': architecture.arch_id,
             'type': type }
    return fetch(query, args, session)

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

def writeSourceList(args):
    (suite, component, incremental_mode) = args
    (file, timestamp) = listPath(suite, component,
            incremental_mode = incremental_mode)
    session = DBConn().session()
    for filename in getSources(suite, component, session, timestamp):
        file.write(filename + '\n')
    session.close()
    file.close()

def writeBinaryList(args):
    (suite, component, architecture, type, incremental_mode) = args
    (file, timestamp) = listPath(suite, component, architecture, type,
            incremental_mode)
    session = DBConn().session()
    for filename in getBinaries(suite, component, architecture, type,
            session, timestamp):
        file.write(filename + '\n')
    session.close()
    file.close()

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

Incremental mode appends only newer files to exising lists."""
    sys.exit()

def main():
    cnf = Config()
    Arguments = [('h', "help",         "Filelist::Options::Help"),
                 ('s', "suite",        "Filelist::Options::Suite", "HasArg"),
                 ('c', "component",    "Filelist::Options::Component", "HasArg"),
                 ('a', "architecture", "Filelist::Options::Architecture", "HasArg"),
                 ('i', "incremental",  "Filelist::Options::Incremental")]
    query_suites = DBConn().session().query(Suite)
    suites = [suite.suite_name for suite in query_suites.all()]
    if not cnf.has_key('Filelist::Options::Suite'):
        cnf['Filelist::Options::Suite'] = ','.join(suites)
    # we can ask the database for components if 'mixed' is gone
    if not cnf.has_key('Filelist::Options::Component'):
        cnf['Filelist::Options::Component'] = 'main,contrib,non-free'
    query_architectures = DBConn().session().query(Architecture)
    architectures = \
        [architecture.arch_string for architecture in query_architectures.all()]
    if not cnf.has_key('Filelist::Options::Architecture'):
        cnf['Filelist::Options::Architecture'] = ','.join(architectures)
    cnf['Filelist::Options::Help'] = ''
    cnf['Filelist::Options::Incremental'] = ''
    apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.SubTree("Filelist::Options")
    if Options['Help']:
        usage()
    session = DBConn().session()
    suite_arch = session.query(SuiteArchitecture)
    threadpool = ThreadPool()
    for suite_name in utils.split_args(Options['Suite']):
        suite = query_suites.filter_by(suite_name = suite_name).one()
        join = suite_arch.filter_by(suite_id = suite.suite_id)
        for component_name in utils.split_args(Options['Component']):
            component = session.query(Component).\
                filter_by(component_name = component_name).one()
            for architecture_name in utils.split_args(Options['Architecture']):
                architecture = query_architectures.\
                    filter_by(arch_string = architecture_name).one()
                try:
                    join.filter_by(arch_id = architecture.arch_id).one()
                    if architecture_name == 'source':
                        threadpool.queueTask(writeSourceList,
                            (suite, component, Options['Incremental']))
                    elif architecture_name != 'all':
                        threadpool.queueTask(writeBinaryList,
                            (suite, component, architecture, 'deb',
                                Options['Incremental']))
                        threadpool.queueTask(writeBinaryList,
                            (suite, component, architecture, 'udeb',
                                Options['Incremental']))
                except:
                    pass
    threadpool.joinAll()
    # this script doesn't change the database
    session.close()

if __name__ == '__main__':
    main()

