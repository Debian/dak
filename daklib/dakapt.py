# -*- coding: utf-8 -*-

"""
interfaces around python-apt

@copyright: 2020 😸 <😸@43-1.org>
@license: GNU General Public License version 2 or later
"""

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import apt_pkg


class DakHashes(object):
    """
    wrapper around `apt_pkg.Hashes`
    """
    def __init__(self, *args, **kwargs):
        self._apt_hashes = apt_pkg.Hashes(*args, **kwargs)

    # python-apt in Debian 10 (buster) uses
    #   `apt_pkg.Hashes(...).md5`
    # but in Debian bullseye it switched to
    #   `apt_pkg.Hashes(...).find('md5sum').hashvalue`
    def _hashvalue(self, name):
        h = self._apt_hashes.hashes.find(name)
        try:
            return h.hashvalue
        except AttributeError:
            return str(h)[len(name) + 1:]

    @property
    def md5(self):
        return self._hashvalue('md5sum')

    @property
    def sha1(self):
        return self._hashvalue('sha1')

    @property
    def sha256(self):
        return self._hashvalue('sha256')
