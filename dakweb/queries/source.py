#!/usr/bin/python

from sqlalchemy import or_
import bottle
import json

from daklib.dbconn import DBConn, DBSource, Suite, DSCFile, PoolFile
from dakweb.webregister import QueryRegister

@bottle.route('/dsc_in_suite/<suite>/<source>')
def dsc_in_suite(suite=None, source=None):
    """
    Find all dsc files for a given source package name in a given suite.

    suite and source must be supplied
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
        ret.append({'version': p.source.version,
                    'component': p.poolfile.component.component_name,
                    'filename': p.poolfile.filename})

    return json.dumps(ret)

QueryRegister().register_path('/dsc_in_suite', dsc_in_suite)

