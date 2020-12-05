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
from sqlalchemy.orm import object_session, aliased


def newer_version(lowersuite_name, highersuite_name, session, include_equal=False):
    '''
    Finds newer versions in lowersuite_name than in highersuite_name. Returns a
    list of tuples (source, higherversion, lowerversion) where higherversion is
    the newest version from highersuite_name and lowerversion is the newest
    version from lowersuite_name.
    '''

    lowersuite = get_suite(lowersuite_name, session)
    highersuite = get_suite(highersuite_name, session)

    def get_suite_sources(suite):
        q1 = session.query(DBSource.source,
                           func.max(DBSource.version).label('version')). \
            with_parent(suite). \
            group_by(DBSource.source). \
            subquery()

        return aliased(q1)

    def get_suite_binaries(suite):
        q1 = session.query(DBBinary.package,
                           DBSource.source,
                           func.max(DBSource.version).label('version'),
                           Architecture.arch_string,
                           func.max(DBBinary.version).label('binversion')). \
            join(DBSource). \
            with_parent(suite). \
            join(Architecture). \
            group_by(
                DBBinary.package,
                DBSource.source,
                Architecture.arch_string,
            ). \
            subquery()

        return aliased(q1)

    highq = get_suite_sources(highersuite)
    lowq = get_suite_sources(lowersuite)

    query = session.query(
            highq.c.source,
            highq.c.version.label('higherversion'),
            lowq.c.version.label('lowerversion')
            ). \
        join(lowq, highq.c.source == lowq.c.source)

    if include_equal:
        query = query.filter(highq.c.version <= lowq.c.version)
    else:
        query = query.filter(highq.c.version < lowq.c.version)

    list = []
    # get all sources that have a higher version in lowersuite than in
    # highersuite
    for (source, higherversion, lowerversion) in query:
        q1 = session.query(DBBinary.package,
                           DBSource.source,
                           DBSource.version,
                           Architecture.arch_string
            ). \
            join(DBSource). \
            with_parent(highersuite). \
            join(Architecture). \
            filter(DBSource.source == source). \
            subquery()
        q2 = session.query(q1.c.arch_string).group_by(q1.c.arch_string)
        # all architectures for which source has binaries in highersuite
        archs_high = set(x[0] for x in q2.all())

        highq = get_suite_binaries(highersuite)
        lowq = get_suite_binaries(lowersuite)

        query = session.query(highq.c.arch_string). \
            join(lowq, highq.c.source == lowq.c.source). \
            filter(highq.c.arch_string == lowq.c.arch_string). \
            filter(highq.c.package == lowq.c.package). \
            filter(highq.c.source == source)

        if include_equal:
            query = query. \
                filter(highq.c.binversion <= lowq.c.binversion). \
                filter(highq.c.version <= lowq.c.version)
        else:
            query = query. \
                filter(highq.c.binversion < lowq.c.binversion). \
                filter(highq.c.version < lowq.c.version)

        query = query.group_by(highq.c.arch_string)

        # all architectures for which source has a newer binary in lowersuite
        archs_newer = set(x[0] for x in query.all())

        # if has at least one binary in lowersuite which is newer than the one
        # in highersuite on each architecture for which source has binaries in
        # highersuite, we know that the builds for all relevant architecture
        # are done, so we can remove the old source with it's binaries
        if (archs_newer >= archs_high):
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
        query = suite.sources.filter_by(source=source). \
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
        bin_query = suite.binaries.filter_by(package=package).subquery()
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

    print("Built from multiple source packages")
    print("-----------------------------------")
    print()
    for package, in get_package_names(suite):
        binary = DejavuBinary(suite, package)
        if binary.has_multiple_sources():
            print(binary)
    print()


def query_without_source(suite_id, session):
    """searches for arch: all packages from suite that do no longer
    reference a source package in the same suite

    subquery unique_binaries: selects all packages with only 1 version
    in suite since 'dak rm' does not allow to specify version numbers"""

    query = """
    with unique_binaries as
        (select package, max(version) as version, max(source) as source
            from bin_associations_binaries
        where architecture = 2 and suite = :suite_id
            group by package having count(*) = 1)
    select ub.package, ub.version
        from unique_binaries ub
        left join src_associations_src sas
        on ub.source = sas.src and sas.suite = :suite_id
        where sas.id is null
        order by ub.package"""
    return session.execute(query, {'suite_id': suite_id})


def queryNBS(suite_id, session):
    """This one is really complex. It searches arch != all packages that
    are no longer built from current source packages in suite.

    temp table unique_binaries: will be populated with packages that
    have only one version in suite because 'dak rm' does not allow
    specifying version numbers

    temp table newest_binaries: will be populated with packages that are
    built from current sources

    subquery uptodate_arch: returns all architectures built from current
    sources

    subquery unique_binaries_uptodate_arch: returns all packages in
    architectures from uptodate_arch

    subquery unique_binaries_uptodate_arch_agg: same as
    unique_binaries_uptodate_arch but with column architecture
    aggregated to array

    subquery uptodate_packages: similar to uptodate_arch but returns all
    packages built from current sources

    subquery outdated_packages: returns all packages with architectures
    no longer built from current source
    """

    query = """
with
    unique_binaries as
    (select
        bab.package,
        bab.architecture,
        max(bab.source) as source
        from bin_associations_binaries bab
        where bab.suite = :suite_id and bab.architecture > 2
        group by package, architecture having count(*) = 1),
    newest_binaries as
    (select ub.package, ub.architecture, nsa.source, nsa.version
        from unique_binaries ub
        join newest_src_association nsa
            on ub.source = nsa.src and nsa.suite = :suite_id),
    uptodate_arch as
    (select architecture, source, version
        from newest_binaries
        group by architecture, source, version),
    unique_binaries_uptodate_arch as
    (select ub.package, ub.architecture, ua.source, ua.version
        from unique_binaries ub
        join source s
            on ub.source = s.id
        join uptodate_arch ua
            on ub.architecture = ua.architecture and s.source = ua.source),
    unique_binaries_uptodate_arch_agg as
    (select ubua.package,
        array(select unnest(array_agg(a.arch_string)) order by 1) as arch_list,
        ubua.source, ubua.version
        from unique_binaries_uptodate_arch ubua
        join architecture a
            on ubua.architecture = a.id
        group by ubua.source, ubua.version, ubua.package),
    uptodate_packages as
    (select package, source, version
        from newest_binaries
        group by package, source, version),
    outdated_packages as
    (select array(select unnest(array_agg(package)) order by 1) as pkg_list,
        arch_list, source, version
        from unique_binaries_uptodate_arch_agg
        where package not in
            (select package from uptodate_packages)
        group by arch_list, source, version)
    select * from outdated_packages order by source"""
    return session.execute(query, {'suite_id': suite_id})


def queryNBS_metadata(suite_id, session):
    """searches for NBS packages based on metadata extraction of the
       newest source for a given suite"""

    query = """
    select string_agg(bin.package, ' ' order by bin.package), (
      select arch_string
      from architecture
      where id = bin.architecture) as architecture, src.source, newsrc.version
    from bin_associations_binaries bin
    join src_associations_src src
    on src.src = bin.source
    and src.suite = bin.suite
    join newest_src_association newsrc
    on newsrc.source = src.source
    and newsrc.version != src.version
    and newsrc.suite = bin.suite
    where bin.suite = :suite_id
    and bin.package not in (
      select trim(' \n' from unnest(string_to_array(meta.value, ',')))
      from source_metadata meta
      where meta.src_id = (
        select newsrc.src
        from newest_src_association newsrc
        where newsrc.source = (
          select s.source
          from source s
          where s.id = bin.source)
        and newsrc.suite = bin.suite)
      and key_id = (
        select key_id
        from metadata_keys
        where key = 'Binary'))
    group by src.source, newsrc.version, architecture
    order by src.source, newsrc.version, bin.architecture"""
    return session.execute(query, {'suite_id': suite_id})
