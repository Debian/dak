""" Archive related queries

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2014  Mark Hymers <mhy@debian.org>
@license: GNU General Public License version 2 or later
"""

import bottle
import json

from daklib.dbconn import DBConn, Archive
from dakweb.webregister import QueryRegister


@bottle.route('/archives')
def archives():
    """
    Give information about all known archives (sets of suites)

    @rtype: dict
    return: list of dictionaries
    """

    s = DBConn().session()
    q = s.query(Archive)
    q = q.order_by(Archive.archive_name)
    ret = []
    for a in q:
        ret.append({'name':      a.archive_name,
                    'suites':    [x.suite_name for x in a.suites]})

    s.close()

    bottle.response.content_type = 'application/json; charset=UTF-8'
    return json.dumps(ret)


QueryRegister().register_path('/archives', archives)
