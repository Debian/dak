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

    Give information about all known suites
    """

    s = DBConn().session()
    q = s.query(Suite)
    q = q.order_by(Suite.suite_name)
    ret = []
    for p in q:
        ret.append({'name':       p.suite_name,
                    'codename':   p.codename,
                    'archive':    p.archive.archive_name,
                    'architectures': [x.arch_string for x in p.architectures],
                    'components': [x.component_name for x in p.components]})

    return json.dumps(ret)

QueryRegister().register_path('/suites', suites)

