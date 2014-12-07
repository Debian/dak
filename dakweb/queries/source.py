""" Queries related to source packages

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2014  Mark Hymers <mhy@debian.org>
@copyright: 2014  Joerg Jaspert <joerg@debian.org>
@license: GNU General Public License version 2 or later
"""

from sqlalchemy import or_
import bottle
import json

from daklib.dbconn import DBConn, DBSource, Suite, DSCFile, PoolFile
from dakweb.webregister import QueryRegister


@bottle.route('/dsc_in_suite/<suite>/<source>')
def dsc_in_suite(suite=None, source=None):
    """
    Find all dsc files for a given source package name in a given suite.

    @since: December 2014

    @type suite: string
    @param suite: Name of the suite.
    @see: L{I{suites}<dakweb.queries.suite.suites>} on how to receive a list of valid suites.

    @type source: string
    @param source: Source package to query for.

    @rtype: list of dictionaries
    @return: Dictionaries made out of
             - version
             - component
             - filename
             - filesize
             - sha256sum
    """
    if suite is None:
        return bottle.HTTPError(503, 'Suite not specified.')
    if source is None:
        return bottle.HTTPError(503, 'Source package not specified.')

    s = DBConn().session()
    q = s.query(DSCFile).join(PoolFile)
    q = q.join(DBSource).join(Suite, DBSource.suites)
    q = q.filter(or_(Suite.suite_name == suite, Suite.codename == suite))
    q = q.filter(DBSource.source == source)
    q = q.filter(PoolFile.filename.endswith('.dsc'))
    ret = []
    for p in q:
        ret.append({'version':   p.source.version,
                    'component': p.poolfile.component.component_name,
                    'filename':  p.poolfile.filename,
                    'filesize':  p.poolfile.filesize,
                    'sha256sum': p.poolfile.sha256sum})

    s.close()

    return json.dumps(ret)

QueryRegister().register_path('/dsc_in_suite', dsc_in_suite)


@bottle.route('/sources_in_suite/<suite>')
def sources_in_suite(suite=None):
    """
    Returns all source packages and their versions in a given suite.

    @since: December 2014

    @type suite: string
    @param suite: Name of the suite.
    @see: L{I{suites}<dakweb.queries.suite.suites>} on how to receive a list of valid suites.

    @rtype: list of dictionaries
    @return: Dictionaries made out of
             - source
             - version
    """
    if suite is None:
        return bottle.HTTPError(503, 'Suite not specified.')

    s = DBConn().session()
    q = s.query(DBSource).join(Suite, DBSource.suites)
    q = q.filter(or_(Suite.suite_name == suite, Suite.codename == suite))
    ret = []
    for p in q:
        ret.append({'source':    p.source,
                    'version':   p.version})

    s.close()

    return json.dumps(ret)

QueryRegister().register_path('/sources_in_suite', sources_in_suite)


@bottle.route('/all_sources')
def all_sources():
    """
    Returns all source packages and their versions known to the archive
    (this includes NEW).

    @rtype: list of dictionaries
    @return: Dictionaries made out of
             - source
             - version
    """

    s = DBConn().session()
    q = s.query(DBSource)
    ret = []
    for p in q:
        ret.append({'source':    p.source,
                    'version':   p.version})

    s.close()

    return json.dumps(ret)

QueryRegister().register_path('/all_sources', all_sources)
