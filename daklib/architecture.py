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

_cached_arch2triplet = None
_cached_triplet2arch = None
def _triplettable():
    global _cached_arch2triplet, _cached_triplet2arch
    if _cached_arch2triplet is None or _cached_triplet2arch is None:
        table = _load_table('/usr/share/dpkg/triplettable')
        arch2triplet = {}
        triplet2arch = {}
        for row in table:
            if '<cpu>' in row[0] or '<cpu>' in row[1]:
                for cpu in _cputable():
                    replaced_row = [ column.replace('<cpu>', cpu[0]) for column in row ]
                    arch2triplet[replaced_row[1]] = replaced_row[0]
                    triplet2arch[replaced_row[0]] = replaced_row[1]
            else:
                arch2triplet[row[1]] = row[0]
                triplet2arch[row[0]] = row[1]
        _cached_arch2triplet = arch2triplet
        _cached_triplet2arch = triplet2arch
    return _cached_triplet2arch, _cached_arch2triplet

class InvalidArchitecture(Exception):
    pass

def Debian_arch_to_Debian_triplet(arch):
    parts = arch.split('-')

    # Handle architecture wildcards
    if 'any' in parts:
        if len(parts) == 3:
            return parts
        elif len(parts) == 2:
            return 'any', parts[0], parts[1]
        else:
            return 'any', 'any', 'any'

    if len(parts) == 2 and parts[0] == 'linux':
        arch = parts[1]

    triplet = _triplettable()[1].get(arch, None)
    if triplet is None:
        return None
    return triplet.split('-', 2)

def match_architecture(arch, wildcard):
    # 'all' has no valid triplet
    if arch == 'all' or wildcard == 'all':
        return arch == wildcard
    if wildcard is 'any' or arch == wildcard:
        return True

    triplet_arch = Debian_arch_to_Debian_triplet(arch)
    triplet_wildcard = Debian_arch_to_Debian_triplet(wildcard)

    if triplet_arch is None or len(triplet_arch) != 3:
        raise InvalidArchitecture('{0} is not a valid architecture name'.format(arch))
    if triplet_wildcard is None or len(triplet_wildcard) != 3:
        raise InvalidArchitecture('{0} is not a valid architecture name or wildcard'.format(wildcard))

    for i in range(0,3):
        if triplet_arch[i] != triplet_wildcard[i] and triplet_wildcard[i] != 'any':
            return False
    return True
