#!/usr/bin/python

""" Helper functions for the various changes formats

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2009, 2010  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Chris Lamb <lamby@debian.org>
@license: GNU General Public License version 2 or later
"""

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

# <mhy> !!!!11111iiiiiioneoneoneone
# <dak> mhy: Error: "!!!11111iiiiiioneoneoneone" is not a valid command.
# <mhy> dak: oh shut up
# <dak> mhy: Error: "oh" is not a valid command.

################################################################################

from regexes import re_verwithext
from dak_exceptions import UnknownFormatError

def parse_format(txt):
    """
    Parse a .changes Format string into a tuple representation for easy
    comparison.

    >>> parse_format('1.0')
    (1, 0)
    >>> parse_format('8.4 (hardy)')
    (8, 4, 'hardy')

    If the format doesn't match these forms, raises UnknownFormatError.

    @type txt: string
    @param txt: Format string to parse

    @rtype: tuple
    @return: Parsed format

    @raise UnknownFormatError: Unknown Format: line
    """

    format = re_verwithext.search(txt)

    if format is None:
        raise UnknownFormatError(txt)

    format = format.groups()

    if format[1] is None:
        format = int(float(format[0])), 0, format[2]
    else:
        format = int(format[0]), int(format[1]), format[2]

    if format[2] is None:
        format = format[:2]

    return format

def validate_changes_format(format, field):
    """
    Validate a tuple-representation of a .changes Format: field. Raises
    UnknownFormatError if the field is invalid, otherwise return type is
    undefined.
    """

    if (format < (1, 5) or format > (1, 8)):
        raise UnknownFormatError(repr(format))

    if field != 'files' and format < (1, 8):
        raise UnknownFormatError(repr(format))
