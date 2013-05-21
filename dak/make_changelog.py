#!/usr/bin/env python

"""
Generate changelog entry between two suites

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2010 Luca Falavigna <dktrkranz@debian.org>
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

# <bdefreese> !dinstall
# <dak> bdefreese: I guess the next dinstall will be in 0hr 1min 35sec
# <bdefreese> Wow I have great timing
# <DktrKranz> dating with dinstall, part II
# <bdefreese> heh
# <Ganneff> dating with that monster? do you have good combat armor?
# <bdefreese> +5 Plate :)
# <Ganneff> not a good one then
# <Ganneff> so you wont even manage to bypass the lesser monster in front, unchecked
# <DktrKranz> asbesto belt
# <Ganneff> helps only a step
# <DktrKranz> the Ultimate Weapon: cron_turned_off
# <bdefreese> heh
# <Ganneff> thats debadmin limited
# <Ganneff> no option for you
# <DktrKranz> bdefreese: it seems ftp-masters want dinstall to sexual harass us, are you good in running?
# <Ganneff> you can run but you can not hide
# <bdefreese> No, I'm old and fat :)
# <Ganneff> you can roll but you can not hide
# <Ganneff> :)
# <bdefreese> haha
# <DktrKranz> damn dinstall, you racist bastard

################################################################################

import os
import sys
import apt_pkg
from glob import glob
from shutil import rmtree
from yaml import safe_dump
from daklib.dbconn import *
from daklib import utils
from daklib.contents import UnpackedSource
from daklib.regexes import re_no_epoch

################################################################################

filelist = 'filelist.yaml'

def usage (exit_code=0):
    print """Generate changelog between two suites

       Usage:
       make-changelog -s <suite> -b <base_suite> [OPTION]...
       make-changelog -e -a <archive>

Options:

  -h, --help                show this help and exit
  -s, --suite               suite providing packages to compare
  -b, --base-suite          suite to be taken as reference for comparison
  -n, --binnmu              display binNMUs uploads instead of source ones

  -e, --export              export interesting files from source packages
  -a, --archive             archive to fetch data from
  -p, --progress            display progress status"""

    sys.exit(exit_code)

def get_source_uploads(suite, base_suite, session):
    """
    Returns changelogs for source uploads where version is newer than base.
    """

    query = """WITH base AS (
                 SELECT source, max(version) AS version
                 FROM source_suite
                 WHERE suite_name = :base_suite
                 GROUP BY source
                 UNION (SELECT source, CAST(0 AS debversion) AS version
                 FROM source_suite
                 WHERE suite_name = :suite
                 EXCEPT SELECT source, CAST(0 AS debversion) AS version
                 FROM source_suite
                 WHERE suite_name = :base_suite
                 ORDER BY source)),
               cur_suite AS (
                 SELECT source, max(version) AS version
                 FROM source_suite
                 WHERE suite_name = :suite
                 GROUP BY source)
               SELECT DISTINCT c.source, c.version, c.changelog
               FROM changelogs c
               JOIN base b ON b.source = c.source
               JOIN cur_suite cs ON cs.source = c.source
               WHERE c.version > b.version
               AND c.version <= cs.version
               AND c.architecture LIKE '%source%'
               ORDER BY c.source, c.version DESC"""

    return session.execute(query, {'suite': suite, 'base_suite': base_suite})

def get_binary_uploads(suite, base_suite, session):
    """
    Returns changelogs for binary uploads where version is newer than base.
    """

    query = """WITH base as (
                 SELECT s.source, max(b.version) AS version, a.arch_string
                 FROM source s
                 JOIN binaries b ON b.source = s.id
                 JOIN bin_associations ba ON ba.bin = b.id
                 JOIN architecture a ON a.id = b.architecture
                 WHERE ba.suite = (
                   SELECT id
                   FROM suite
                   WHERE suite_name = :base_suite)
                 GROUP BY s.source, a.arch_string),
               cur_suite as (
                 SELECT s.source, max(b.version) AS version, a.arch_string
                 FROM source s
                 JOIN binaries b ON b.source = s.id
                 JOIN bin_associations ba ON ba.bin = b.id
                 JOIN architecture a ON a.id = b.architecture
                 WHERE ba.suite = (
                   SELECT id
                   FROM suite
                   WHERE suite_name = :suite)
                 GROUP BY s.source, a.arch_string)
               SELECT DISTINCT c.source, c.version, c.architecture, c.changelog
               FROM changelogs c
               JOIN base b on b.source = c.source
               JOIN cur_suite cs ON cs.source = c.source
               WHERE c.version > b.version
               AND c.version <= cs.version
               AND c.architecture = b.arch_string
               AND c.architecture = cs.arch_string
               ORDER BY c.source, c.version DESC, c.architecture"""

    return session.execute(query, {'suite': suite, 'base_suite': base_suite})

def display_changes(uploads, index):
    prev_upload = None
    for upload in uploads:
        if prev_upload and prev_upload != upload[0]:
            print
        print upload[index]
        prev_upload = upload[0]

def export_files(session, archive, clpool, progress=False):
    """
    Export interesting files from source packages.
    """
    pool = os.path.join(archive.path, 'pool')

    sources = {}
    unpack = {}
    files = ('changelog', 'copyright', 'NEWS.Debian', 'README.Debian')
    stats = {'unpack': 0, 'created': 0, 'removed': 0, 'errors': 0, 'files': 0}
    query = """SELECT DISTINCT s.source, su.suite_name AS suite, s.version, c.name || '/' || f.filename AS filename
               FROM source s
               JOIN newest_source n ON n.source = s.source AND n.version = s.version
               JOIN src_associations sa ON sa.source = s.id
               JOIN suite su ON su.id = sa.suite
               JOIN files f ON f.id = s.file
               JOIN files_archive_map fam ON f.id = fam.file_id AND fam.archive_id = su.archive_id
               JOIN component c ON fam.component_id = c.id
               WHERE su.archive_id = :archive_id
               ORDER BY s.source, suite"""

    for p in session.execute(query, {'archive_id': archive.archive_id}):
        if not sources.has_key(p[0]):
            sources[p[0]] = {}
        sources[p[0]][p[1]] = (re_no_epoch.sub('', p[2]), p[3])

    for p in sources.keys():
        for s in sources[p].keys():
            path = os.path.join(clpool, '/'.join(sources[p][s][1].split('/')[:-1]))
            if not os.path.exists(path):
                os.makedirs(path)
            if not os.path.exists(os.path.join(path, \
                   '%s_%s_changelog' % (p, sources[p][s][0]))):
                if not unpack.has_key(os.path.join(pool, sources[p][s][1])):
                    unpack[os.path.join(pool, sources[p][s][1])] = (path, set())
                unpack[os.path.join(pool, sources[p][s][1])][1].add(s)
            else:
                for file in glob('%s/%s_%s_*' % (path, p, sources[p][s][0])):
                    link = '%s%s' % (s, file.split('%s_%s' \
                                      % (p, sources[p][s][0]))[1])
                    try:
                        os.unlink(os.path.join(path, link))
                    except OSError:
                        pass
                    os.link(os.path.join(path, file), os.path.join(path, link))

    for p in unpack.keys():
        package = os.path.splitext(os.path.basename(p))[0].split('_')
        try:
            unpacked = UnpackedSource(p, clpool)
            tempdir = unpacked.get_root_directory()
            stats['unpack'] += 1
            if progress:
                if stats['unpack'] % 100 == 0:
                    sys.stderr.write('%d packages unpacked\n' % stats['unpack'])
                elif stats['unpack'] % 10 == 0:
                    sys.stderr.write('.')
            for file in files:
                for f in glob(os.path.join(tempdir, 'debian', '*%s' % file)):
                    for s in unpack[p][1]:
                        suite = os.path.join(unpack[p][0], '%s_%s' \
                                % (s, os.path.basename(f)))
                        version = os.path.join(unpack[p][0], '%s_%s_%s' % \
                                  (package[0], package[1], os.path.basename(f)))
                        if not os.path.exists(version):
                            os.link(f, version)
                            stats['created'] += 1
                        try:
                            os.unlink(suite)
                        except OSError:
                            pass
                        os.link(version, suite)
                        stats['created'] += 1
            unpacked.cleanup()
        except Exception as e:
            print 'make-changelog: unable to unpack %s\n%s' % (p, e)
            stats['errors'] += 1

    for root, dirs, files in os.walk(clpool, topdown=False):
        files = [f for f in files if f != filelist]
        if len(files):
            if root != clpool:
                if root.split('/')[-1] not in sources.keys():
                    if os.path.exists(root):
                        stats['removed'] += len(os.listdir(root))
                        rmtree(root)
            for file in files:
                if os.path.exists(os.path.join(root, file)):
                    if os.stat(os.path.join(root, file)).st_nlink ==  1:
                        stats['removed'] += 1
                        os.unlink(os.path.join(root, file))
        for dir in dirs:
            try:
                os.rmdir(os.path.join(root, dir))
            except OSError:
                pass
        stats['files'] += len(files)
    stats['files'] -= stats['removed']

    print 'make-changelog: file exporting finished'
    print '  * New packages unpacked: %d' % stats['unpack']
    print '  * New files created: %d' % stats['created']
    print '  * New files removed: %d' % stats['removed']
    print '  * Unpack errors: %d' % stats['errors']
    print '  * Files available into changelog pool: %d' % stats['files']

def generate_export_filelist(clpool):
    clfiles = {}
    for root, dirs, files in os.walk(clpool):
        for file in [f for f in files if f != filelist]:
            clpath = os.path.join(root, file).replace(clpool, '').strip('/')
            source = clpath.split('/')[2]
            elements = clpath.split('/')[3].split('_')
            if source not in clfiles:
                clfiles[source] = {}
            if elements[0] == source:
                if elements[1] not in clfiles[source]:
                    clfiles[source][elements[1]] = []
                clfiles[source][elements[1]].append(clpath)
            else:
                if elements[0] not in clfiles[source]:
                    clfiles[source][elements[0]] = []
                clfiles[source][elements[0]].append(clpath)
    with open(os.path.join(clpool, filelist), 'w+') as fd:
        safe_dump(clfiles, fd, default_flow_style=False)

def main():
    Cnf = utils.get_conf()
    Arguments = [('h','help','Make-Changelog::Options::Help'),
                 ('a','archive','Make-Changelog::Options::Archive','HasArg'),
                 ('s','suite','Make-Changelog::Options::Suite','HasArg'),
                 ('b','base-suite','Make-Changelog::Options::Base-Suite','HasArg'),
                 ('n','binnmu','Make-Changelog::Options::binNMU'),
                 ('e','export','Make-Changelog::Options::export'),
                 ('p','progress','Make-Changelog::Options::progress')]

    for i in ['help', 'suite', 'base-suite', 'binnmu', 'export', 'progress']:
        if not Cnf.has_key('Make-Changelog::Options::%s' % (i)):
            Cnf['Make-Changelog::Options::%s' % (i)] = ''

    apt_pkg.parse_commandline(Cnf, Arguments, sys.argv)
    Options = Cnf.subtree('Make-Changelog::Options')
    suite = Cnf['Make-Changelog::Options::Suite']
    base_suite = Cnf['Make-Changelog::Options::Base-Suite']
    binnmu = Cnf['Make-Changelog::Options::binNMU']
    export = Cnf['Make-Changelog::Options::export']
    progress = Cnf['Make-Changelog::Options::progress']

    if Options['help'] or not (suite and base_suite) and not export:
        usage()

    for s in suite, base_suite:
        if not export and not get_suite(s):
            utils.fubar('Invalid suite "%s"' % s)

    session = DBConn().session()

    if export:
        archive = session.query(Archive).filter_by(archive_name=Options['Archive']).one()
        exportpath = archive.changelog
        if exportpath:
            export_files(session, archive, exportpath, progress)
            generate_export_filelist(exportpath)
        else:
            utils.fubar('No changelog export path defined')
    elif binnmu:
        display_changes(get_binary_uploads(suite, base_suite, session), 3)
    else:
        display_changes(get_source_uploads(suite, base_suite, session), 2)

    session.commit()

if __name__ == '__main__':
    main()
