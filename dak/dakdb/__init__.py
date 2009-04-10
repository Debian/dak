"""
Database update scripts for usage with B{dak update-db}

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2008  Michael Casadevall <mcasadevall@debian.org>
@license: GNU General Public License version 2 or later

Update scripts have to C{import psycopg2} and
C{from daklib.dak_exceptions import DBUpdateError}.

There has to be B{at least} the function C{do_update(self)} to be
defined. It should take all neccessary steps to update the
database. If the update fails the changes have to be rolled back and the
C{DBUpdateError} exception raised to properly halt the execution of any
other update.

Example::
 def do_update(self):
     print "Doing something"

     try:
         c = self.db.cursor()
         c.execute("SOME SQL STATEMENT")
         self.db.commit()

     except psycopg2.ProgrammingError, msg:
         self.db.rollback()
         raise DBUpdateError, "Unable to do whatever, rollback issued. Error message : %s" % (str(msg))

This function can do whatever it wants and use everything from dak and
daklib.

"""
