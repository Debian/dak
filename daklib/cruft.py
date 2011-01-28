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

