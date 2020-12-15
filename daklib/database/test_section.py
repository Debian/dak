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

from .section import Section


def test_Section(session):
    obj = Section('section')
    session.add(obj)
    session.flush()

    get = Section.get(1, session)
    assert get
    assert get.section == 'section'


def test_Section___eq__():
    obj = Section('section')

    with pytest.warns(DeprecationWarning):
        assert obj == 'section'
    with pytest.warns(DeprecationWarning):
        assert 'section' == obj


def test_Section___ne__():
    obj = Section('section')

    with pytest.warns(DeprecationWarning):
        assert obj != 'zzzz'
    with pytest.warns(DeprecationWarning):
        assert 'zzzz' != obj
