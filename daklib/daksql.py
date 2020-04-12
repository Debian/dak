"""SQLAlchemy extensions for dak

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

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement, ClauseElement, ClauseList, literal
from sqlalchemy.types import Text
from sqlalchemy.util import to_list


class array_agg(ColumnElement):
    def __init__(self, expr, order_by=None):
        self.expr = ClauseElement(expr)
        self.order_by = None
        if order_by is not None:
            self.order_by = ClauseList(*to_list(order_by))


@compiles(array_agg)
def compile_array_agg(element, compiler, **kw):
    if element.order_by is not None:
        return "ARRAY_AGG({0} ORDER BY {1})".format(compiler.process(element.expr), compiler.process(element.order_by))
    return "ARRAY_AGG({0})".format(compiler.process(element.expr))


class string_agg(ColumnElement):
    type = Text()

    def __init__(self, column, seperator, order_by=None):
        self.column = ClauseList(*to_list(column))
        self.seperator = literal(seperator, type_=Text)
        self.order_by = None
        if order_by is not None:
            self.order_by = ClauseList(*to_list(order_by))


@compiles(string_agg)
def compile_string_agg(element, compiler, **kw):
    if element.order_by is not None:
        return "STRING_AGG({0}, {1} ORDER BY {2})".format(compiler.process(element.column), compiler.process(element.seperator), compiler.process(element.order_by))
    return "STRING_AGG({0}, {1})".format(compiler.process(element.column), compiler.process(element.seperator))
