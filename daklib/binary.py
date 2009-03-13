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

# <Ganneff> are we going the xorg way?
# <Ganneff> a dak without a dak.conf?
# <stew> automatically detect the wrong settings at runtime?
# <Ganneff> yes!
# <mhy> well, we'll probably always need dak.conf (how do you get the database setting
# <mhy> but removing most of the config into the database seems sane
# <Ganneff> mhy: dont spoil the fun
# <Ganneff> mhy: and i know how. we nmap localhost and check all open ports
# <Ganneff> maybe one answers to sql
# <stew> we will discover projectb via avahi
# <mhy> you're both sick
# <mhy> really fucking sick

################################################################################

import os
import sys
import shutil
import tempfile
import tarfile
import commands
import traceback
import atexit
from debian_bundle import deb822
from dbconn import DBConn
from config import Config
import logging
import utils

class Binary(object):
    def __init__(self, filename, reject=None):
        """
        @ptype filename: string
        @param filename: path of a .deb

        @ptype reject: function
        @param reject: a function to log reject messages to
        """
        self.filename = filename
        self.tmpdir = None
        self.chunks = None
        self.wrapped_reject = reject

    def reject(self, message):
        """
        if we were given a reject function, send the reject message,
        otherwise send it to stderr.
        """
        if self.wrapped_reject:
            self.wrapped_reject(message)
        else:
            print >> sys.stderr, message

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
            shutil.rmtree(self.tmpdir)
            self.tmpdir = None

    def __scan_ar(self):
        # get a list of the ar contents
        if not self.chunks:

            cmd = "ar t %s" % (self.filename)
            (result, output) = commands.getstatusoutput(cmd)
            if result != 0:
                rejected = True
                self.reject("%s: 'ar t' invocation failed." % (self.filename))
                self.reject(utils.prefix_multi_line_string(output, " [ar output:] "), "")
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
                    self.reject("%s: '%s' invocation failed." % (self.filename, cmd))
                    self.reject(utils.prefix_multi_line_string(output, " [ar output:] "))
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
            self.reject("%s: found %d chunks, expected 3." % (self.filename, len(self.chunks)))
        if self.chunks[0] != "debian-binary":
            rejected = True
            self.reject("%s: first chunk is '%s', expected 'debian-binary'." % (self.filename, self.chunks[0]))
        if self.chunks[1] != "control.tar.gz":
            rejected = True
            self.reject("%s: second chunk is '%s', expected 'control.tar.gz'." % (self.filename, self.chunks[1]))
        if self.chunks[2] not in [ "data.tar.bz2", "data.tar.gz" ]:
            rejected = True
            self.reject("%s: third chunk is '%s', expected 'data.tar.gz' or 'data.tar.bz2'." % (self.filename, self.chunks[2]))

        return not rejected

    def scan_package(self, bootstrap_id=0):
        """
        Unpack the .deb, do sanity checking, and gather info from it.

        Currently information gathering consists of getting the contents list. In
        the hopefully near future, it should also include gathering info from the
        control file.

        @ptype bootstrap_id: int
        @param bootstrap_id: the id of the binary these packages
          should be associated or zero meaning we are not bootstrapping
          so insert into a temporary table

        @return True if the deb is valid and contents were imported
        """
        rejected = not self.valid_deb()
        self.__unpack()

        result = False

        cwd = os.getcwd()
        if not rejected and self.tmpdir:
            try:
                os.chdir(self.tmpdir)
                if self.chunks[1] == "control.tar.gz":
                    control = tarfile.open(os.path.join(self.tmpdir, "control.tar.gz" ), "r:gz")
                    control.extract('./control', self.tmpdir )
                if self.chunks[2] == "data.tar.gz":
                    data = tarfile.open(os.path.join(self.tmpdir, "data.tar.gz"), "r:gz")
                elif self.chunks[2] == "data.tar.bz2":
                    data = tarfile.open(os.path.join(self.tmpdir, "data.tar.bz2" ), "r:bz2")

                if bootstrap_id:
                    result = DBConn().insert_content_paths(bootstrap_id, [tarinfo.name for tarinfo in data if not tarinfo.isdir()])
                else:
                    pkg = deb822.Packages.iter_paragraphs(file(os.path.join(self.tmpdir,'control'))).next()
                    result = DBConn().insert_pending_content_paths(pkg, [tarinfo.name for tarinfo in data if not tarinfo.isdir()])

            except:
                traceback.print_exc()

        os.chdir(cwd)
        return result

    def check_utf8_package(self, package):
        """
        Unpack the .deb, do sanity checking, and gather info from it.

        Currently information gathering consists of getting the contents list. In
        the hopefully near future, it should also include gathering info from the
        control file.

        @ptype bootstrap_id: int
        @param bootstrap_id: the id of the binary these packages
          should be associated or zero meaning we are not bootstrapping
          so insert into a temporary table

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
                    control.extract('control', self.tmpdir )
                if self.chunks[2] == "data.tar.gz":
                    data = tarfile.open(os.path.join(self.tmpdir, "data.tar.gz"), "r:gz")
                elif self.chunks[2] == "data.tar.bz2":
                    data = tarfile.open(os.path.join(self.tmpdir, "data.tar.bz2" ), "r:bz2")

                for tarinfo in data:
                    try:
                        unicode( tarinfo.name )
                    except:
                        print >> sys.stderr, "E: %s has non-unicode filename: %s" % (package,tarinfo.name)

            except:
                traceback.print_exc()
                result = False

            os.chdir(cwd)

if __name__ == "__main__":
    Binary( "/srv/ftp.debian.org/queue/accepted/halevt_0.1.3-2_amd64.deb" ).scan_package()

