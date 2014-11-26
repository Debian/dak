import bottle
import json

from daklib.ls import list_packages
from dakweb.webregister import QueryRegister

@bottle.route('/madison')
def madison():
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

    result = list_packages(packages, **kwargs)
    return "\n".join(result) + "\n"

QueryRegister().register_path('/madison', madison)
