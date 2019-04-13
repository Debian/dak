"""List packages according to various criteria

@copyright: 2014, Ansgar Burchardt <ansgar@debian.org>
@license: GPL-2+
"""

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import sqlalchemy.sql as sql
import daklib.daksql as daksql

from daklib.dbconn import DBConn
from collections import defaultdict


def list_packages(packages, suites=None, components=None, architectures=None, binary_types=None,
                  source_and_binary=False, regex=False,
                  format=None, highest=None):
    session = DBConn().session()
    try:
        t = DBConn().view_package_list

        comparison_operator = "~" if regex else "="

        where = sql.false()
        for package in packages:
            where = where | t.c.package.op(comparison_operator)(package)
            if source_and_binary:
                where = where | t.c.source.op(comparison_operator)(package)

        if suites is not None:
            where = where & (t.c.suite.in_(suites) | t.c.codename.in_(suites))
        if components is not None:
            where = where & t.c.component.in_(components)
        if architectures is not None:
            where = where & t.c.architecture.in_(architectures)
        if binary_types is not None:
            where = where & t.c.type.in_(binary_types)

        if format is None:
            c_architectures = daksql.string_agg(t.c.architecture, ', ', order_by=[t.c.architecture_is_source.desc(), t.c.architecture])
            query = sql.select([t.c.package, t.c.version, t.c.display_suite, c_architectures]) \
                       .where(where) \
                       .group_by(t.c.package, t.c.version, t.c.display_suite) \
                       .order_by(t.c.package, t.c.version, t.c.display_suite)
            result = session.execute(query).fetchall()

            if len(result) == 0:
                return

            lengths = {
                'package': max(10, max(len(row[t.c.package]) for row in result)),
                'version': max(13, max(len(row[t.c.version]) for row in result)),
                'suite':   max(10, max(len(row[t.c.display_suite]) for row in result))
            }
            format = "{0:{lengths[package]}} | {1:{lengths[version]}} | {2:{lengths[suite]}} | {3}"

            for row in result:
                yield format.format(row[t.c.package], row[t.c.version], row[t.c.display_suite], row[c_architectures], lengths=lengths)
        elif format in ('control-suite', 'heidi'):
            query = sql.select([t.c.package, t.c.version, t.c.architecture]).where(where)
            result = session.execute(query)
            for row in result:
                yield "{0} {1} {2}".format(row[t.c.package], row[t.c.version], row[t.c.architecture])
        elif format == "python":
            c_architectures = daksql.string_agg(t.c.architecture, ',', order_by=[t.c.architecture_is_source.desc(), t.c.architecture])
            query = sql.select([t.c.package,
                                t.c.version,
                                t.c.display_suite,
                                c_architectures,
                                t.c.source,
                                t.c.source_version,
                                t.c.component]) \
                .where(where) \
                .group_by(t.c.package,
                          t.c.version,
                          t.c.display_suite,
                          t.c.source,
                          t.c.component,
                          t.c.source_version)
            result = session.execute(query).fetchall()

            if len(result) == 0:
                return

            def val():
                return defaultdict(val)
            ret = val()
            for row in result:
                ret[row[t.c.package]][row[t.c.display_suite]][row[t.c.version]] = {'component':      row[t.c.component],
                                       'architectures':  row[c_architectures].split(','),
                                       'source':         row[t.c.source],
                                       'source_version': row[t.c.source_version]
                                   }

            yield ret
            return
        else:
            raise ValueError("Unknown output format requested.")

        if highest is not None:
            query = sql.select([t.c.package, sql.func.max(t.c.version)]).where(where) \
                       .group_by(t.c.package).order_by(t.c.package)
            result = session.execute(query)
            yield ""
            for row in result:
                yield "{0} ({1} {2})".format(row[0], highest, row[1])
    finally:
        session.close()
