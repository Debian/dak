#!/usr/bin/python

import bottle
import json

from daklib.dbconn import DBConn, Archive
from dakweb.webregister import QueryRegister

@bottle.route('/archives')
def archives():
    """
    Returns a list of supported archives
    """

    s = DBConn().session()
    q = s.query(Archive)
    q = q.order_by(Archive.archive_name)
    ret = []
    for a in q:
        ret.append({'name':      a.archive_name,
                    'suites':    [x.suite_name for x in a.suites]})

    return json.dumps(ret)

QueryRegister().register_path('/archives', archives)

