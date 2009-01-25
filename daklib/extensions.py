#!/usr/bin/env python

""" Utility functions for extensions """
# Copyright (C) 2008 Anthony Towns <ajt@dbeian.org>

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

dak_functions_to_replace = {}
dak_replaced_functions = {}

def replace_dak_function(module,name):
    """Decorator to make a function replace a standard dak function
       in a given module. The replaced function will be provided as
       the first argument."""

    def x(f):
        def myfunc(*a,**kw):
            global replaced_funcs
            f(dak_replaced_functions[name], *a, **kw)
        myfunc.__name__ = f.__name__
        myfunc.__doc__ = f.__doc__
        myfunc.__dict__.update(f.__dict__)

        fnname = "%s:%s" % (module, name)
        if fnname in dak_functions_to_replace:
            raise Exception, \
                "%s in %s already marked to be replaced" % (name, module)
        dak_functions_to_replace["%s:%s" % (module,name)] = myfunc
        return f
    return x

################################################################################

def init(name, module, userext):
    global dak_replaced_functions

    # This bit should be done automatically too
    dak_replaced_functions = {}
    for f,newfunc in dak_functions_to_replace.iteritems():
        m,f = f.split(":",1)
        if len(f) > 0 and m == name:
            dak_replaced_functions[f] = module.__dict__[f]
            module.__dict__[f] = newfunc
