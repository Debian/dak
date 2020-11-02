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

import warnings

from sqlalchemy import Column, Integer, Text
from sqlalchemy.schema import Index

from .base import BaseTimestamp


class Section(BaseTimestamp):
    __tablename__ = 'section'

    section_id = Column('id', Integer, primary_key=True)
    section = Column(Text, nullable=False)

    # indexes where not created as constraints, need to do as well
    __table_args__ = (Index('section_section_key', 'section', unique=True), )

    def __init__(self, section=None):
        self.section = section

    def __str__(self):
        return self.section

    def __repr__(self):
        return '<{} {}>'.format(
            self.__class__.__name__,
            self.section,
        )

    def __eq__(self, val):
        if isinstance(val, str):
            warnings.warn("comparison with a `str` is deprecated", DeprecationWarning, stacklevel=2)
            return (self.section == val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            warnings.warn("comparison with a `str` is deprecated", DeprecationWarning, stacklevel=2)
            return (self.section != val)
        # This signals to use the normal comparison operator
        return NotImplemented

    __hash__ = BaseTimestamp.__hash__
