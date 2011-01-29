"""
helper functions for cruft-report

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright 2011 Torsten Werner <twerner@debian.org>
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

################################################################################

from daklib.dbconn import *

from sqlalchemy import func

def newer_version(lowersuite_name, highersuite_name, session):
    '''
    Finds newer versions in lowersuite_name than in highersuite_name. Returns a
    list of tuples (source, higherversion, lowerversion) where higherversion is
    the newest version from highersuite_name and lowerversion is the newest
    version from lowersuite_name.
    '''

    lowersuite = get_suite(lowersuite_name, session)
    highersuite = get_suite(highersuite_name, session)

    query = session.query(DBSource.source, func.max(DBSource.version)). \
        with_parent(highersuite).group_by(DBSource.source)

    list = []
    for (source, higherversion) in query:
        lowerversion = session.query(func.max(DBSource.version)). \
            filter_by(source = source).filter(DBSource.version > higherversion). \
            with_parent(lowersuite).group_by(DBSource.source).scalar()
        if lowerversion is not None:
            list.append((source, higherversion, lowerversion))
    return list

