"""
@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2014  Mark Hymers <mhy@debian.org>
@license: GNU General Public License version 2 or later
"""


class QueryRegister(object):
    __shared_state = {}

    def __init__(self, *args, **kwargs):
        self.__dict__ = self.__shared_state

        if not getattr(self, 'initialised', False):
            self.initialised = True

            # Dictionary of query paths to help mappings
            self.queries = {}

    def register_path(self, path, func):
        self.queries[path] = func.__module__

    def get_paths(self):
        return sorted(self.queries.keys())

    def get_path_help(self, path):
        # We always register with the leading /
        if not path.startswith('/'):
            path = '/' + path
        return self.queries.get(path, '/')


__all__ = ['QueryRegister']
