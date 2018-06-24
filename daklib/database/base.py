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

from sqlalchemy import Column, DateTime
from sqlalchemy.event import listen
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import DDL, Table
from sqlalchemy.sql import func


Base = declarative_base()


class BaseMethods(Base):
    __abstract__ = True

    @classmethod
    def get(cls, primary_key, session):
        '''
        This is a support function that allows getting an object by its primary
        key.

        Architecture.get(3[, session])

        instead of the more verbose

        session.query(Architecture).get(3)
        '''
        return session.query(cls).get(primary_key)


class BaseTimestamp(BaseMethods):
    __abstract__ = True

    created = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    modified = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    modified_trigger_function = DDL("""
CREATE OR REPLACE FUNCTION tfunc_set_modified() RETURNS trigger
LANGUAGE plpgsql
AS $$
    BEGIN NEW.modified = now(); return NEW; END;
$$
    """)

    modified_trigger = DDL("""
CREATE TRIGGER %(table)s_modified BEFORE UPDATE ON %(fullname)s
FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified()
    """)

    @classmethod
    def __table_cls__(cls, *arg, **kw):
        table = Table(*arg, **kw)
        listen(
            table,
            'after_create',
            cls.modified_trigger_function.execute_if(dialect='postgresql'),
        )
        listen(
            table,
            'after_create',
            cls.modified_trigger.execute_if(dialect='postgresql'),
        )
        return table
