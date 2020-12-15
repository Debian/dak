# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

################################################################################

import pytest

from .architecture import Architecture


def test_Architecture(session):
    obj = Architecture('arch', 'description')
    session.add(obj)
    session.flush()

    get = Architecture.get(1, session)
    assert get
    assert get.arch_string == 'arch'
    assert get.description == 'description'


def test_Architecture___eq__():
    obj = Architecture('arch')

    with pytest.warns(DeprecationWarning):
        assert obj == 'arch'
    with pytest.warns(DeprecationWarning):
        assert 'arch' == obj


def test_Architecture___ne__():
    obj = Architecture('arch')

    with pytest.warns(DeprecationWarning):
        assert obj != 'zzzz'
    with pytest.warns(DeprecationWarning):
        assert 'zzzz' != obj
