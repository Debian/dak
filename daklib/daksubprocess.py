"""subprocess management for dak

@copyright: 2013, Ansgar Burchardt <ansgar@debian.org>
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

import signal
import subprocess

#
def fix_signal_handlers():
    """reset signal handlers to default action.

    Python changes the signal handler to SIG_IGN for a few signals which
    causes unexpected behaviour in child processes. This function resets
    them to their default action.

    Reference: http://bugs.python.org/issue1652
    """
    for signal_name in ('SIGPIPE', 'SIGXFZ', 'SIGXFSZ'):
        try:
            signal_number = getattr(signal, signal_name)
            signal.signal(signal_number, signal.SIG_DFL)
        except AttributeError:
            pass

def _generate_preexec_fn(other_preexec_fn=None):
    def preexec_fn():
        fix_signal_handlers()
        if other_preexec_fn is not None:
            other_preexec_fn()
    return preexec_fn

def call(*args, **kwargs):
    """wrapper around subprocess.call that fixes signal handling"""
    preexec_fn = _generate_preexec_fn(kwargs.get('preexec_fn'))
    kwargs['preexec_fn'] = preexec_fn
    return subprocess.call(*args, **kwargs)

def check_call(*args, **kwargs):
    """wrapper around subprocess.check_call that fixes signal handling"""
    preexec_fn = _generate_preexec_fn(kwargs.get('preexec_fn'))
    kwargs['preexec_fn'] = preexec_fn
    return subprocess.check_call(*args, **kwargs)

def check_output(*args, **kwargs):
    """wrapper around subprocess.check_output that fixes signal handling"""
    preexec_fn = _generate_preexec_fn(kwargs.get('preexec_fn'))
    kwargs['preexec_fn'] = preexec_fn
    return subprocess.check_output(*args, **kwargs)

def Popen(*args, **kwargs):
    """wrapper around subprocess.Popen that fixes signal handling"""
    preexec_fn = _generate_preexec_fn(kwargs.get('preexec_fn'))
    kwargs['preexec_fn'] = preexec_fn
    return subprocess.Popen(*args, **kwargs)
