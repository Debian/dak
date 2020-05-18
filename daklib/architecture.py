"""architecture matching

@copyright: 2014, Ansgar Burchardt <ansgar@debian.org>
@license: GPL-2+
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
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import errno


def _load_table(path):
    table = []
    with open(path, 'r') as fh:
        for line in fh:
            if not line or line.startswith('#'):
                continue
            table.append(line.split())
    return table


_cached_cputable = None


def _cputable():
    global _cached_cputable
    if _cached_cputable is None:
        _cached_cputable = _load_table('/usr/share/dpkg/cputable')
    return _cached_cputable


_cached_arch2tuple = None
_cached_tuple2arch = None


def _tupletable():
    global _cached_arch2tuple, _cached_tuple2arch
    if _cached_arch2tuple is None or _cached_tuple2arch is None:
        try:
            tripletable = False
            table = _load_table('/usr/share/dpkg/tupletable')
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise
            tripletable = True
            table = _load_table('/usr/share/dpkg/triplettable')

        arch2tuple = {}
        tuple2arch = {}

        def add_tuple(tuple, arch):
            if tripletable:
                tuple = "base-{}".format(tuple)
            arch2tuple[arch] = tuple
            tuple2arch[tuple] = arch

        for row in table:
            if '<cpu>' in row[0] or '<cpu>' in row[1]:
                for cpu in _cputable():
                    replaced_row = [column.replace('<cpu>', cpu[0]) for column in row]
                    add_tuple(replaced_row[0], replaced_row[1])
            else:
                add_tuple(row[0], row[1])

        _cached_arch2tuple = arch2tuple
        _cached_tuple2arch = tuple2arch
    return _cached_tuple2arch, _cached_arch2tuple


class InvalidArchitecture(Exception):
    pass


def Debian_arch_to_Debian_tuple(arch):
    parts = arch.split('-')

    # Handle architecture wildcards
    if 'any' in parts:
        if len(parts) == 4:
            return parts
        elif len(parts) == 3:
            return 'any', parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            return 'any', 'any', parts[0], parts[1]
        else:
            return 'any', 'any', 'any', 'any'

    if len(parts) == 2 and parts[0] == 'linux':
        arch = parts[1]

    tuple = _tupletable()[1].get(arch, None)
    if tuple is None:
        return None
    return tuple.split('-', 3)


def match_architecture(arch, wildcard):
    # 'all' has no valid tuple
    if arch == 'all' or wildcard == 'all':
        return arch == wildcard
    if wildcard == 'any' or arch == wildcard:
        return True

    tuple_arch = Debian_arch_to_Debian_tuple(arch)
    tuple_wildcard = Debian_arch_to_Debian_tuple(wildcard)

    if tuple_arch is None or len(tuple_arch) != 4:
        raise InvalidArchitecture('{0} is not a valid architecture name'.format(arch))
    if tuple_wildcard is None or len(tuple_wildcard) != 4:
        raise InvalidArchitecture('{0} is not a valid architecture name or wildcard'.format(wildcard))

    for i in range(0, 4):
        if tuple_arch[i] != tuple_wildcard[i] and tuple_wildcard[i] != 'any':
            return False
    return True
