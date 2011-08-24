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

from multiprocessing.pool import Pool
from signal import signal, SIGHUP, SIGTERM, SIGPIPE, SIGALRM

import sqlalchemy.orm.session

__all__ = []

PROC_STATUS_SUCCESS      = 0  # Everything ok
PROC_STATUS_EXCEPTION    = 1  # An exception was caught
PROC_STATUS_SIGNALRAISED = 2  # A signal was generated
PROC_STATUS_MISCFAILURE  = 3  # Process specific error; see message

__all__.extend(['PROC_STATUS_SUCCESS',      'PROC_STATUS_EXCEPTION',
                'PROC_STATUS_SIGNALRAISED', 'PROC_STATUS_MISCFAILURE'])

class SignalException(Exception):
    def __init__(self, signum):
        self.signum = signum

    def __str__(self):
        return "<SignalException: %d>" % self.signum

__all__.append('SignalException')

def signal_handler(signum, info):
    raise SignalException(signum)

def _func_wrapper(func, *args, **kwds):
    # We need to handle signals to avoid hanging
    signal(SIGHUP, signal_handler)
    signal(SIGTERM, signal_handler)
    signal(SIGPIPE, signal_handler)
    signal(SIGALRM, signal_handler)

    # We expect our callback function to return:
    # (status, messages)
    # Where:
    #  status is one of PROC_STATUS_*
    #  messages is a string used for logging
    try:
        return (func(*args, **kwds))
    except SignalException as e:
        return (PROC_STATUS_SIGNALRAISED, e.signum)
    except Exception as e:
        return (PROC_STATUS_EXCEPTION, str(e))
    finally:
        # Make sure connections are closed. We might die otherwise.
        sqlalchemy.orm.session.Session.close_all()


class DakProcessPool(Pool):
    def __init__(self, *args, **kwds):
        Pool.__init__(self, *args, **kwds)
        self.results = []
        self.int_results = []

    def apply_async(self, func, args=(), kwds={}, callback=None):
        wrapper_args = list(args)
        wrapper_args.insert(0, func)
        self.int_results.append(Pool.apply_async(self, _func_wrapper, wrapper_args, kwds, callback))

    def join(self):
        Pool.join(self)
        for r in self.int_results:
            # return values were already handled in the callbacks, but asking
            # for them might raise exceptions which would otherwise be lost
            self.results.append(r.get())

    def overall_status(self):
        # Return the highest of our status results
        # This basically allows us to do sys.exit(overall_status()) and have us
        # exit 0 if everything was good and non-zero if not
        status = 0
        for r in self.results:
            if r[0] > status:
                status = r[0]
        return status

__all__.append('DakProcessPool')
