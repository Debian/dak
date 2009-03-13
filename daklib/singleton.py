#!/usr/bin/env python
# vim:set et ts=4 sw=4:

"""
Singleton pattern code

Inspiration for this very simple ABC was taken from various documents /
tutorials / mailing lists.  This may not be thread safe but given that
(as I write) large chunks of dak aren't even type-safe, I'll live with
it for now

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2008  Mark Hymers <mhy@debian.org>
@license: GNU General Public License version 2 or later
"""

################################################################################

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

# < sgran> NCommander: in SQL, it's better to join than to repeat information
# < tomv_w> that makes SQL the opposite to Debian mailing lists!

################################################################################

"""
This class set implements objects that may need to be instantiated multiple
times, but we don't want the overhead of actually creating and init'ing
them more than once.  It also saves us using globals all over the place
"""

class Singleton(object):
    """This is the ABC for other dak Singleton classes"""
    __single = None
    def __new__(cls, *args, **kwargs):
        # Check to see if a __single exists already for this class
        # Compare class types instead of just looking for None so
        # that subclasses will create their own __single objects
        if cls != type(cls.__single):
            cls.__single = object.__new__(cls, *args, **kwargs)
            cls.__single._startup(*args, **kwargs)
        return cls.__single

    def __init__(self, *args, **kwargs):
        if type(self) == "Singleton":
            raise NotImplementedError("Singleton is an ABC")

    def _startup(self):
        """
        _startup is a private method used instead of __init__ due to the way
        we instantiate this object
        """
        raise NotImplementedError("Singleton is an ABC")

