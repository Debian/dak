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
    pass


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


class CantOverwriteError(DakError):
    "Exception raised when files can't be overwritten."
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


class DBUpdateError(DakError):
    "Exception raised - could not update the database"
    pass


class AlreadyLockedError(DakError):
    "Exception raised - package already locked by someone else"
    pass
