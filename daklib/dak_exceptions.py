#!/usr/bin/env python

""" Exception classes used in dak """

# Copyright (C) 2008  Mark Hymers <mhy@debian.org>

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

class DakError(Exception):
    """Base class for all simple errors in this module.

    Attributes:

       message -- explanation of the error
    """

    def __init__(self, message=""):
        Exception.__init__(self)
        self.args = str(message)
        self.message = str(message)

    def __str__(self):
        return self.message

__all__ = ['DakError']

dakerrors = {
    "ParseMaintError":     """Exception raised for errors in parsing a maintainer field.""",
    "ParseChangesError":   """Exception raised for errors in parsing a changes file.""",
    "InvalidDscError":     """Exception raised for invalid dsc files.""",
    "UnknownFormatError":  """Exception raised for unknown Format: lines in changes files.""",
    "NoFilesFieldError":   """Exception raised for missing files field in dsc/changes.""",
    "CantOpenError":       """Exception raised when files can't be opened.""",
    "CantOverwriteError":  """Exception raised when files can't be overwritten.""",
    "FileExistsError":     """Exception raised when destination file exists.""",
    "SendmailFailedError": """Exception raised when Sendmail invocation failed.""",
    "NoFreeFilenameError": """Exception raised when no alternate filename was found.""",
    "TransitionsError":    """Exception raised when transitions file can't be parsed.""",
    "NoSourceFieldError":  """Exception raised - we cant find the source - wtf?"""
}

def construct_dak_exception(name, description):
    class Er(DakError):
        __doc__ = description
    setattr(Er, "__name__", name)
    return Er

for e in dakerrors.keys():
    globals()[e] = construct_dak_exception(e, dakerrors[e])
    __all__ += [e]



################################################################################
