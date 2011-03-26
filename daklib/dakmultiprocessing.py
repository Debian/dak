#!/usr/bin/env python
# vim:set et sw=4:

"""
multiprocessing for DAK

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2011  Ansgar Burchardt <ansgar@debian.org>
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

import multiprocessing
import sqlalchemy.orm.session

def _func_wrapper(func, *args, **kwds):
    try:
        return func(*args, **kwds)
    finally:
        # Make sure connections are closed. We might die otherwise.
        sqlalchemy.orm.session.Session.close_all()

class Pool():
    def __init__(self, *args, **kwds):
        self.pool = multiprocessing.Pool(*args, **kwds)
        self.results = []

    def apply_async(self, func, args=(), kwds={}, callback=None):
        wrapper_args = list(args)
        wrapper_args.insert(0, func)
        self.results.append(self.pool.apply_async(_func_wrapper, wrapper_args, kwds, callback))

    def close(self):
        self.pool.close()

    def join(self):
        self.pool.join()
        for r in self.results:
            # return values were already handled in the callbacks, but asking
            # for them might raise exceptions which would otherwise be lost
            r.get()
