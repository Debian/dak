# vim:set et sw=4:
"""
TermColor utils for dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2019 Mo Zhou <lumin@debian.org>
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

###############################################################################

__all__ = []

###############################################################################

_COLORS_ = ('red', 'green', 'yellow', 'blue', 'violet', 'cyan', 'white')
_COLOR_CODES_ = {k: 31 + _COLORS_.index(k) for k in _COLORS_}


def colorize(s, fg, bg=None, bold=False, ul=False):
    '''
    s: str -- string to be colorized
    fg: str/int -- foreground color. See _COLORS_ for choices
    bg: str/int -- background color. See _COLORS_ for choices
    bold: bool -- bold font?
    ul: bool -- underline?
    '''
    if fg not in _COLORS_:
        raise ValueError("Unsupported foreground Color!")
    if (bg is not None) or any((bold, ul)):
        raise NotImplementedError
    return "\x1b[{}m{}\x1b[0;m".format(_COLOR_CODES_[fg], s)
