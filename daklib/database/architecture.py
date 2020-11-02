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


class Architecture(BaseTimestamp):
    __tablename__ = 'architecture'

    arch_id = Column('id', Integer, primary_key=True)
    arch_string = Column(Text, nullable=False)
    description = Column(Text)

    # indexes where not created as constraints, need to do as well
    __table_args__ = (Index('architecture_arch_string_key', 'arch_string', unique=True), )

    def __init__(self, arch_string=None, description=None):
        self.arch_string = arch_string
        self.description = description

    def __str__(self):
        return self.arch_string

    def __repr__(self):
        return '<{} {}>'.format(
            self.__class__.__name__,
            self.arch_string,
        )

    def __eq__(self, val):
        if isinstance(val, str):
            warnings.warn("comparison with a `str` is deprecated", DeprecationWarning, stacklevel=2)
            return (self.arch_string == val)
        # This signals to use the normal comparison operator
        return NotImplemented

    def __ne__(self, val):
        if isinstance(val, str):
            warnings.warn("comparison with a `str` is deprecated", DeprecationWarning, stacklevel=2)
            return (self.arch_string != val)
        # This signals to use the normal comparison operator
        return NotImplemented

    __hash__ = BaseTimestamp.__hash__
