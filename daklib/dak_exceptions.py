#!/usr/bin/env python

"""
Exception classes used in dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008  Mark Hymers <mhy@debian.org>
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


class DakError(Exception):
    """
    Base class for all simple errors in this module.

    """

    def __init__(self, message=""):
        """
        @type message: string
        @param message: explanation of the error

        """
        Exception.__init__(self)
        self.args = str(message)
        self.message = str(message)

    def __str__(self):
        return self.message


class ParseMaintError(DakError):
    "Exception raised for errors in parsing a maintainer field."
    pass


class ParseChangesError(DakError):
    "Exception raised for errors in parsing a changes file."
    pass


class InvalidDscError(DakError):
    "Exception raised for invalid dsc files."
    pass


class UnknownFormatError(DakError):
    "Exception raised for unknown Format: lines in changes files."
    pass


class NoFilesFieldError(DakError):
    """Exception raised for missing files field in dsc/changes."""
    pass


class CantOpenError(DakError):
    """Exception raised when files can't be opened."""
    pass


class CantOverwriteError(DakError):
    "Exception raised when files can't be overwritten."
    pass


class FileExistsError(DakError):
    "Exception raised when destination file exists."
    pass


class SendmailFailedError(DakError):
    "Exception raised when Sendmail invocation failed."
    pass


class NoFreeFilenameError(DakError):
    "Exception raised when no alternate filename was found."
    pass


class TransitionsError(DakError):
    "Exception raised when transitions file can't be parsed."
    pass


class NoSourceFieldError(DakError):
    "Exception raised - we cant find the source - wtf?"
    pass


class MissingContents(DakError):
    "Exception raised - we could not determine contents for this deb"
    pass


class DBUpdateError(DakError):
    "Exception raised - could not update the database"
    pass


class ChangesUnicodeError(DakError):
    "Exception raised - changes file not properly utf-8 encoded"
    pass


class AlreadyLockedError(DakError):
    "Exception raised - package already locked by someone else"
    pass


class CantGetLockError(DakError):
    "Exception raised - lockfile already in use"
    pass
