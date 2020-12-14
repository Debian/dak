""" "Madison" interface

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2014  Ansgar Burchardt <ansgar@debian.org>
@copyright: 2014  Joerg Jaspert <joerg@debian.org>
@license: GNU General Public License version 2 or later
"""

import bottle
import json

from daklib.ls import list_packages
from dakweb.webregister import QueryRegister


@bottle.route('/madison')
def madison():
    """
    Display information about B{package(s)}.

    @since: December 2014

    @keyword package: Space separated list of packages.
    @keyword a: only show info for specified architectures.
    @keyword b: only show info for a binary type. I{deb/udeb/dsc}
    @keyword c: only show info for specified component(s). I{main/contrib/non-free}
    @keyword s: only show info for this suite.
    @keyword S: show info for the binary children of source pkgs. I{true/false}
    @keyword f: output json format. I{json}
    @see: L{I{suites}<dakweb.queries.suite.suites>} on how to receive a list of valid suites.

    @rtype: text/plain or application/json
    @return: Text or Json format of the data
    """

    r = bottle.request

    packages = r.query.get('package', '').split()
    kwargs = dict()

    architectures = r.query.get('a', None)
    if architectures is not None:
        kwargs['architectures'] = architectures.split(",")
    binary_type = r.query.get('b', None)
    if binary_type is not None:
        kwargs['binary_types'] = [binary_type]
    component = r.query.get('c', None)
    if component is not None:
        kwargs['components'] = component.split(",")
    suite = r.query.get('s', None)
    if suite is not None:
        kwargs['suites'] = suite.split(",")
    if 'S' in r.query:
        kwargs['source_and_binary'] = True
    format = r.query.get('f', None)
    if format is not None:
        kwargs['format'] = 'python'

    result = list_packages(packages, **kwargs)

    if format is None:
        bottle.response.content_type = 'text/plain; charset=UTF-8'
        for row in result:
            yield row
            yield "\n"
    else:
        bottle.response.content_type = 'application/json; charset=UTF-8'
        yield json.dumps(list(result))


QueryRegister().register_path('/madison', madison)
