import bottle
import json

from daklib.ls import list_packages
from dakweb.webregister import QueryRegister

@bottle.route('/madison')
def madison():
    """
    Display information about packages.

    b=TYPE      only show info for binary TYPE
    c=COMPONENT only show info for COMPONENT(s)
    s=SUITE     only show info for this suite
    S=true      show info for the binary children of source pkgs
    f=json      output json format
    """

    r = bottle.request

    packages = r.query.get('package', '').split()
    kwargs = dict()

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
    #if 'r' in r.query:
    #    kwargs['regex'] = True
    format = r.query.get('f', None)
    if format is not None:
        kwargs['format'] = 'python'

    result = list_packages(packages, **kwargs)

    if format is None:
        bottle.response.content_type = 'text/plain'
        for row in result:
            yield row
            yield "\n"
    else:
        yield json.dumps(list(result))


QueryRegister().register_path('/madison', madison)
