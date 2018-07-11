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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from daklib.database.all import Base


Session = sessionmaker()


@pytest.fixture(scope='session')
def engine():
    engine = create_engine('sqlite://', echo=True)
    Base.metadata.create_all(engine)
    return engine


@pytest.yield_fixture
def session(engine):
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    trans.rollback()
    connection.close()
