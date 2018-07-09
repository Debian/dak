# Copyright (C) 2018, Ansgar Burchardt <ansgar@debian.org>
# License: GPL-2+
#
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


class AptVersion(object):
    def __init__(self, version):
        self.version = version

    def __str__(self):
        return str(self.version)

    def __eq__(self, other):
        return apt_pkg.version_compare(self.version, other.version) == 0

    def __lt__(self, other):
        return apt_pkg.version_compare(self.version, other.version) < 0

    def __le__(self, other):
        return apt_pkg.version_compare(self.version, other.version) <= 0

    def __gt__(self, other):
        return apt_pkg.version_compare(self.version, other.version) > 0

    def __ge__(self, other):
        return apt_pkg.version_compare(self.version, other.version) >= 0
