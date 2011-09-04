#!/usr/bin/python

""" Helper functions for the various source formats

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

# <sgran> hey, I think something's wrong with your git repo
# <sgran> when I git pulled this last time, I got something that looked almost
#         like python instead of dak
# <mhy> sgran: slander
# <sgran> sorry, I take it back, I've had a better look now

################################################################################
import re

from dak_exceptions import UnknownFormatError

srcformats = []

def get_format_from_string(txt):
    """
    Returns the SourceFormat class that corresponds to the specified .changes
    Format value. If the string does not match any class, UnknownFormatError
    is raised.
    """

    for format in srcformats:
        if format.re_format.match(txt):
            return format

    raise UnknownFormatError("Unknown format %r" % txt)

class SourceFormat(type):
    def __new__(cls, name, bases, attrs):
        klass = super(SourceFormat, cls).__new__(cls, name, bases, attrs)
        srcformats.append(klass)

        assert str(klass.name)
        assert iter(klass.requires)
        assert iter(klass.disallowed)

        klass.re_format = re.compile(klass.format)

        return klass

    @classmethod
    def reject_msgs(cls, has):
        if len(cls.requires) != len([x for x in cls.requires if has[x]]):
            yield "lack of required files for format %s" % cls.name

        for key in cls.disallowed:
            if has[key]:
                yield "contains source files not allowed in format %s" % cls.name

class FormatOne(SourceFormat):
    __metaclass__ = SourceFormat

    name = '1.0'
    format = r'1.0'

    requires = ()
    disallowed = ('debian_tar', 'more_orig_tar')

    @classmethod
    def reject_msgs(cls, has):
        if not (has['native_tar_gz'] or (has['orig_tar_gz'] and has['debian_diff'])):
            yield "no .tar.gz or .orig.tar.gz+.diff.gz in 'Files' field."
        if has['native_tar_gz'] and has['debian_diff']:
            yield "native package with diff makes no sense"
        if (has['orig_tar_gz'] != has['orig_tar']) or \
           (has['native_tar_gz'] != has['native_tar']):
            yield "contains source files not allowed in format %s" % cls.name

        for msg in super(FormatOne, cls).reject_msgs(has):
            yield msg

class FormatThree(SourceFormat):
    __metaclass__ = SourceFormat

    name = '3.x (native)'
    format = r'3\.\d+ \(native\)'

    requires = ('native_tar',)
    disallowed = ('orig_tar', 'debian_diff', 'debian_tar', 'more_orig_tar')

class FormatThreeQuilt(SourceFormat):
    __metaclass__ = SourceFormat

    name = '3.x (quilt)'
    format = r'3\.\d+ \(quilt\)'

    requires = ('orig_tar', 'debian_tar')
    disallowed = ('debian_diff', 'native_tar')
