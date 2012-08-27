#!/usr/bin/env python
# vim:set et ts=4 sw=4:

"""Text utility functions

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
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

import email.Header

from dak_exceptions import *
from regexes import re_parse_maintainer

################################################################################

def force_to_utf8(s):
    """
    Forces a string to UTF-8.  If the string isn't already UTF-8,
    it's assumed to be ISO-8859-1.
    """
    if isinstance(s, unicode):
        return s
    try:
        unicode(s, 'utf-8')
        return s
    except UnicodeError:
        latin1_s = unicode(s,'iso8859-1')
        return latin1_s.encode('utf-8')

def rfc2047_encode(s):
    """
    Encodes a (header) string per RFC2047 if necessary.  If the
    string is neither ASCII nor UTF-8, it's assumed to be ISO-8859-1.
    """
    for enc in ['ascii', 'utf-8', 'iso-8859-1']:
        try:
            h = email.Header.Header(s, enc, 998)
            return str(h)
        except UnicodeError:
            pass

    # If we get here, we're boned beyond belief
    return ''

################################################################################

# <Culus> 'The standard sucks, but my tool is supposed to interoperate
#          with it. I know - I'll fix the suckage and make things
#          incompatible!'

def fix_maintainer(maintainer):
    """
    Parses a Maintainer or Changed-By field and returns:
      1. an RFC822 compatible version,
      2. an RFC2047 compatible version,
      3. the name
      4. the email

    The name is forced to UTF-8 for both 1. and 3..  If the name field
    contains '.' or ',' (as allowed by Debian policy), 1. and 2. are
    switched to 'email (name)' format.

    """
    maintainer = maintainer.strip()
    if not maintainer:
        return ('', '', '', '')

    if maintainer.find("<") == -1:
        email = maintainer
        name = ""
    elif (maintainer[0] == "<" and maintainer[-1:] == ">"):
        email = maintainer[1:-1]
        name = ""
    else:
        m = re_parse_maintainer.match(maintainer)
        if not m:
            raise ParseMaintError("Doesn't parse as a valid Maintainer field.")
        name = m.group(1)
        email = m.group(2)

    # Get an RFC2047 compliant version of the name
    rfc2047_name = rfc2047_encode(name)

    # Force the name to be UTF-8
    name = force_to_utf8(name)

    if name.find(',') != -1 or name.find('.') != -1:
        rfc822_maint = "%s (%s)" % (email, name)
        rfc2047_maint = "%s (%s)" % (email, rfc2047_name)
    else:
        rfc822_maint = "%s <%s>" % (name, email)
        rfc2047_maint = "%s <%s>" % (rfc2047_name, email)

    if email.find("@") == -1 and email.find("buildd_") != 0:
        raise ParseMaintError("No @ found in email address part.")

    return (rfc822_maint, rfc2047_maint, name, email)

################################################################################

def split_uploaders(field):
    import re
    for u in re.sub(">[ ]*,", ">\t", field).split("\t"):
        yield u.strip()
