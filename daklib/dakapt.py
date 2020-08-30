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

"""
wrapper around `apt_pkg.Hashes`
"""
class DakHashes(object):
    def __init__(self, *args, **kwargs):
        self._apt_hashes = apt_pkg.Hashes(*args, **kwargs)

    # python-apt in Debian 10 (buster) uses
    #   `apt_pkg.Hashes(...).md5`
    # but in Debian bullseye it switched to
    #   `apt_pkg.Hashes(...).find('md5sum').hashvalue`
    def _hashvalue(self, attr, name):
        if hasattr(self._apt_hashes, attr):
            return getattr(self._apt_hashes, attr)
        else:
            return self._apt_hashes.hashes.find(name).hashvalue

    @property
    def md5(self):
        return self._hashvalue('md5', 'md5sum')

    @property
    def sha1(self):
        return self._hashvalue('sha1', 'sha1')

    @property
    def sha256(self):
        return self._hashvalue('sha256', 'sha256')
