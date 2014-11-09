#!/usr/bin/python

import bottle
import json

from daklib.dbconn import DBConn, Suite
from dakweb.webregister import QueryRegister

@bottle.route('/suites')
def suites():
    """
    suites()

    returns: list of dictionaries

    Give information about all known suites.

    name maps to Suite: in the release file
    codename maps to Codename: in the release file.
    dakname is an internal name and should not be relied upon.
    """

    s = DBConn().session()
    q = s.query(Suite)
    q = q.order_by(Suite.suite_name)
    ret = []
    for p in q:
        ret.append({'name':       p.release_suite_output,
                    'codename':   p.codename,
                    'dakname':    p.suite_name,
                    'archive':    p.archive.archive_name,
                    'architectures': [x.arch_string for x in p.architectures],
                    'components': [x.component_name for x in p.components]})

    return json.dumps(ret)

QueryRegister().register_path('/suites', suites)

@bottle.route('/suite/<suite>')
def suite(suite=None):
    """
    suite(suite)

    returns: dictionary

    Gives information about a single suite.  Note that this routine will look
    up a suite first by the main suite_name, but then also by codename if no
    suite is initially found.  It can therefore be used to canonicalise suite
    names
    """

    if suite is None:
        return bottle.HTTPError(503, 'Suite not specified.')

    # TODO: We should probably stick this logic into daklib/dbconn.py
    so = None

    s = DBConn().session()
    q = s.query(Suite)
    q = q.filter(Suite.suite_name == suite)

    if q.count() > 1:
        # This would mean dak is misconfigured
        return bottle.HTTPError(503, 'Multiple suites found: configuration error')
    elif q.count() == 1:
        so = q[0]
    else:
        # Look it up by suite_name
        q = s.query(Suite).filter(Suite.codename == suite)
        if q.count() > 1:
            # This would mean dak is misconfigured
            return bottle.HTTPError(503, 'Multiple suites found: configuration error')
        elif q.count() == 1:
            so = q[0]

    if so is not None:
        so = {'name':       so.release_suite_output,
              'codename':   so.codename,
              'dakname':    so.suite_name,
              'archive':    so.archive.archive_name,
              'architectures': [x.arch_string for x in so.architectures],
              'components': [x.component_name for x in so.components]}

    return json.dumps(so)

QueryRegister().register_path('/suite', suite)

