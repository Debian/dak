#!/usr/bin/python

"""
Functions related debian binary packages

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2009  Mike O'Connor <stew@debian.org>
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

################################################################################

import os
import shutil
import tempfile
import tarfile
import commands
import traceback
import atexit
from debian_bundle import deb822
from dbconn import DBConn

class Binary(object):
    def __init__(self, filename):
        self.filename = filename
        self.tmpdir = None
        self.chunks = None

    def __del__(self):
        """
        make sure we cleanup when we are garbage collected.
        """
        self._cleanup()

    def _cleanup(self):
        """
        we need to remove the temporary directory, if we created one
        """
        if self.tmpdir and os.path.exists(self.tmpdir):
            self.tmpdir = None
            shutil.rmtree(self.tmpdir)

    def __scan_ar(self):
        # get a list of the ar contents
        if not self.chunks:

            cmd = "ar t %s" % (self.filename)

            (result, output) = commands.getstatusoutput(cmd)
            if result != 0:
                rejected = True
                reject("%s: 'ar t' invocation failed." % (self.filename))
                reject(utils.prefix_multi_line_string(output, " [ar output:] "), "")
            self.chunks = output.split('\n')



    def __unpack(self):
        # Internal function which extracts the contents of the .ar to
        # a temporary directory

        if not self.tmpdir:
            tmpdir = tempfile.mkdtemp()
            cwd = os.getcwd()
            try:
                os.chdir( tmpdir )
                cmd = "ar x %s %s %s" % (os.path.join(cwd,self.filename), self.chunks[1], self.chunks[2])
                (result, output) = commands.getstatusoutput(cmd)
                if result != 0:
                    reject("%s: '%s' invocation failed." % (filename, cmd))
                    reject(utils.prefix_multi_line_string(output, " [ar output:] "), "")
                else:
                    self.tmpdir = tmpdir
                    atexit.register( self._cleanup )

            finally:
                os.chdir( cwd )

    def valid_deb(self):
        """
        Check deb contents making sure the .deb contains:
          1. debian-binary
          2. control.tar.gz
          3. data.tar.gz or data.tar.bz2
        in that order, and nothing else.
        """
        self.__scan_ar()
        rejected = not self.chunks
        if len(self.chunks) != 3:
            rejected = True
            reject("%s: found %d chunks, expected 3." % (self.filename, len(self.chunks)))
        if self.chunks[0] != "debian-binary":
            rejected = True
            reject("%s: first chunk is '%s', expected 'debian-binary'." % (self.filename, self.chunks[0]))
        if self.chunks[1] != "control.tar.gz":
            rejected = True
            reject("%s: second chunk is '%s', expected 'control.tar.gz'." % (self.filename, self.chunks[1]))
        if self.chunks[2] not in [ "data.tar.bz2", "data.tar.gz" ]:
            rejected = True
            reject("%s: third chunk is '%s', expected 'data.tar.gz' or 'data.tar.bz2'." % (self.filename, self.chunks[2]))

        return not rejected

    def scan_package(self):
        """
        Unpack the .deb, do sanity checking, and gather info from it.

        Currently information gathering consists of getting the contents list. In
        the hopefully near future, it should also include gathering info from the
        control file.

        @return True if the deb is valid and contents were imported
        """
        rejected = not self.valid_deb()
        self.__unpack()

        if not rejected and self.tmpdir:
            cwd = os.getcwd()
            try:
                os.chdir(self.tmpdir)
                if self.chunks[1] == "control.tar.gz":
                    control = tarfile.open(os.path.join(self.tmpdir, "control.tar.gz" ), "r:gz")

                pkg = deb822.Packages.iter_paragraphs( control.extractfile('./control') ).next()

                if self.chunks[2] == "data.tar.gz":
                    data = tarfile.open(os.path.join(self.tmpdir, "data.tar.gz"), "r:gz")
                elif self.chunks[2] == "data.tar.bz2":
                    data = tarfile.open(os.path.join(self.tmpdir, "data.tar.bz2" ), "r:bz2")

                return DBConn().insert_content_paths(pkg, [ tarinfo.name for tarinfo in data if tarinfo.isdir()])

            except:
                traceback.print_exc()

                return False

            finally:
                os.chdir( cwd )




if __name__ == "__main__":
    Binary( "/srv/ftp.debian.org/queue/accepted/halevt_0.1.3-2_amd64.deb" ).scan_package()

