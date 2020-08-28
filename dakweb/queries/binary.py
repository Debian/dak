"""Debian binary package related queries.

@copyright: 2017 Michael Stapelberg <stapelberg@debian.org>
@copyright: 2017 Joerg Jaspert <joerg@debian.org>
@license: GNU General Public License version 2 or later
"""

import bottle
import json

from daklib.dbconn import DBConn, DBBinary, DBSource, SourceMetadata, MetadataKey
from dakweb.webregister import QueryRegister


@bottle.route('/binary/metadata_keys/')
def binary_metadata_keys():
    """
    List all possible metadata keys

    @rtype: dictionary
    @return: A list of metadata keys
    """
    s = DBConn().session()
    q = s.query(MetadataKey)
    ret = []
    for p in q:
        ret.append(p.key)

    s.close()

    bottle.response.content_type = 'application/json; charset=UTF-8'
    return json.dumps(ret)


QueryRegister().register_path('/metadata_keys', binary_metadata_keys)


@bottle.route('/binary/by_metadata/<key>')
def binary_by_metadata(key=None):
    """

    Finds all Debian binary packages which have the specified metadata set
    in their correspondig source package.

    E.g., to find out the Go import paths of all Debian Go packages, query
    /binary/by_metadata/Go-Import-Path.

    @type key: string
    @param key: Metadata key of the source package to search for.

    @rtype: dictionary
    @return: A list of dictionaries of
             - binary
             - source
             - metadata value
    """

    if not key:
        return bottle.HTTPError(503, 'Metadata key not specified.')

    s = DBConn().session()
    q = s.query(DBBinary.package, DBSource.source, SourceMetadata.value)
    q = q.join(DBSource).join(SourceMetadata).join(MetadataKey)
    q = q.filter(MetadataKey.key == key)
    q = q.group_by(DBBinary.package, DBSource.source, SourceMetadata.value)
    ret = []
    for p in q:
        ret.append({'binary': p.package,
                    'source': p.source,
                    'metadata_value': p.value})
    s.close()

    bottle.response.content_type = 'application/json; charset=UTF-8'
    return json.dumps(ret)


QueryRegister().register_path('/binary/by_metadata', binary_by_metadata)
