#!/usr/bin/python

from daklib.dbconn import *
from daklib.config import Config
from daklib import utils
import apt_pkg, os, sys

def fetch(query, args, session):
  return [path + filename for (path, filename) in \
    session.execute(query, args).fetchall()]

def getSources(suite, component, session):
  query = """
    SELECT path, filename
      FROM srcfiles_suite_component
      WHERE suite = :suite AND component = :component
  """
  args = { 'suite': suite.suite_id,
           'component': component.component_id }
  return fetch(query, args, session)

def getBinaries(suite, component, architecture, type, session):
  query = """
    SELECT path, filename
      FROM binfiles_suite_component_arch
      WHERE suite = :suite AND component = :component AND type = :type AND
            (architecture = :architecture OR architecture = 2)
  """
  args = { 'suite': suite.suite_id,
           'component': component.component_id,
           'architecture': architecture.arch_id,
           'type': type }
  return fetch(query, args, session)

def listPath(suite, component, architecture = None, type = None):
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
  return utils.open_file(pathname, "w")

def writeSourceList(suite, component, session):
  file = listPath(suite, component)
  for filename in getSources(suite, component, session):
    file.write(filename + '\n')
  file.close()

def writeBinaryList(suite, component, architecture, type, session):
  file = listPath(suite, component, architecture, type)
  for filename in getBinaries(suite, component, architecture, type, session):
    file.write(filename + '\n')
  file.close()

def usage():
  print """Usage: dak generate_filelist [OPTIONS]
Create filename lists for apt-ftparchive.

  -s, --suite=SUITE          act on this suite
  -c, --component=COMPONENT  act on this component
  -a, --architecture=ARCH    act on this architecture
  -h, --help                 show this help and exit

ARCH, COMPONENT and SUITE can be comma (or space) separated list, e.g.
    --suite=testing,unstable"""
  sys.exit()

def main():
  cnf = Config()
  Arguments = [('h', "help",         "Filelist::Options::Help"),
               ('s', "suite",        "Filelist::Options::Suite", "HasArg"),
               ('c', "component",    "Filelist::Options::Component", "HasArg"),
               ('a', "architecture", "Filelist::Options::Architecture", "HasArg")]
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
  apt_pkg.ParseCommandLine(cnf.Cnf, Arguments, sys.argv)
  Options = cnf.SubTree("Filelist::Options")
  if Options['Help']:
    usage()
  session = DBConn().session()
  suite_arch = session.query(SuiteArchitecture)
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
            writeSourceList(suite, component, session)
          elif architecture_name != 'all':
            writeBinaryList(suite, component, architecture, 'deb', session)
            writeBinaryList(suite, component, architecture, 'udeb', session)
        except:
          pass
  # this script doesn't change the database
  session.rollback()

if __name__ == '__main__':
  main()

