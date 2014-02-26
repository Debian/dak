"""
helper functions for cruft-report

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright 2011 Torsten Werner <twerner@debian.org>
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

from daklib.dbconn import *

from sqlalchemy import func
from sqlalchemy.orm import object_session

def newer_version(lowersuite_name, highersuite_name, session):
    '''
    Finds newer versions in lowersuite_name than in highersuite_name. Returns a
    list of tuples (source, higherversion, lowerversion) where higherversion is
    the newest version from highersuite_name and lowerversion is the newest
    version from lowersuite_name.
    '''

    lowersuite = get_suite(lowersuite_name, session)
    highersuite = get_suite(highersuite_name, session)

    query = session.query(DBSource.source, func.max(DBSource.version)). \
        with_parent(highersuite).group_by(DBSource.source)

    list = []
    for (source, higherversion) in query:
        lowerversion = session.query(func.max(DBSource.version)). \
            filter_by(source = source).filter(DBSource.version > higherversion). \
            with_parent(lowersuite).group_by(DBSource.source).scalar()
        if lowerversion is not None:
            list.append((source, higherversion, lowerversion))

    list.sort()
    return list

def get_package_names(suite):
    '''
    Returns a query that selects all distinct package names from suite ordered
    by package name.
    '''

    session = object_session(suite)
    return session.query(DBBinary.package).with_parent(suite). \
        group_by(DBBinary.package).order_by(DBBinary.package)

class NamedSource(object):
    '''
    A source package identified by its name with all of its versions in a
    suite.
    '''
    def __init__(self, suite, source):
        self.source = source
        query = suite.sources.filter_by(source = source). \
            order_by(DBSource.version)
        self.versions = [src.version for src in query]

    def __str__(self):
        return "%s(%s)" % (self.source, ", ".join(self.versions))

class DejavuBinary(object):
    '''
    A binary package identified by its name which gets built by multiple source
    packages in a suite. The architecture is ignored which leads to the
    following corner case, e.g.:

    If a source package 'foo-mips' that builds a binary package 'foo' on mips
    and another source package 'foo-mipsel' builds a binary package with the
    same name 'foo' on mipsel then the binary package 'foo' will be reported as
    built from multiple source packages.
    '''

    def __init__(self, suite, package):
        self.package = package
        session = object_session(suite)
        # We need a subquery to make sure that both binary and source packages
        # are in the right suite.
        bin_query = suite.binaries.filter_by(package = package).subquery()
        src_query = session.query(DBSource.source).with_parent(suite). \
            join(bin_query).order_by(DBSource.source).group_by(DBSource.source)
        self.sources = []
        if src_query.count() > 1:
            for source, in src_query:
                self.sources.append(str(NamedSource(suite, source)))

    def has_multiple_sources(self):
        'Has the package been built by multiple sources?'
        return len(self.sources) > 1

    def __str__(self):
        return "%s built by: %s" % (self.package, ", ".join(self.sources))

def report_multiple_source(suite):
    '''
    Reports binary packages built from multiple source package with different
    names.
    '''

    print "Built from multiple source packages"
    print "-----------------------------------"
    print
    for package, in get_package_names(suite):
        binary = DejavuBinary(suite, package)
        if binary.has_multiple_sources():
            print binary
    print
