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
import tarfile
import commands
import traceback
import atexit

from debian_bundle import deb822

from dbconn import *
from config import Config
import utils

################################################################################

__all__ = []

################################################################################

class Binary(object):
    def __init__(self, filename, reject=None):
        """
        @type filename: string
        @param filename: path of a .deb

        @type reject: function
        @param reject: a function to log reject messages to
        """
        self.filename = filename
        self.tmpdir = None
        self.chunks = None
        self.wrapped_reject = reject
        # Store rejects for later use
        self.rejects = []

    def reject(self, message):
        """
        if we were given a reject function, send the reject message,
        otherwise send it to stderr.
        """
        print >> sys.stderr, message
        self.rejects.append(message)
        if self.wrapped_reject:
            self.wrapped_reject(message)

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
                print("%s: 'ar t' invocation failed." % (self.filename))
                self.reject("%s: 'ar t' invocation failed." % (self.filename))
                self.reject(utils.prefix_multi_line_string(output, " [ar output:] "))
            self.chunks = output.split('\n')



    def __unpack(self):
        # Internal function which extracts the contents of the .ar to
        # a temporary directory

        if not self.tmpdir:
            tmpdir = utils.temp_dirname()
            cwd = os.getcwd()
            try:
                os.chdir( tmpdir )
                cmd = "ar x %s %s %s" % (os.path.join(cwd,self.filename), self.chunks[1], self.chunks[2])
                (result, output) = commands.getstatusoutput(cmd)
                if result != 0:
                    print("%s: '%s' invocation failed." % (self.filename, cmd))
                    self.reject("%s: '%s' invocation failed." % (self.filename, cmd))
                    self.reject(utils.prefix_multi_line_string(output, " [ar output:] "))
                else:
                    self.tmpdir = tmpdir
                    atexit.register( self._cleanup )

            finally:
                os.chdir( cwd )

    def valid_deb(self, relaxed=False):
        """
        Check deb contents making sure the .deb contains:
          1. debian-binary
          2. control.tar.gz
          3. data.tar.gz or data.tar.bz2
        in that order, and nothing else.
        """
        self.__scan_ar()
        rejected = not self.chunks
        if relaxed:
            if len(self.chunks) < 3:
                rejected = True
                self.reject("%s: found %d chunks, expected at least 3." % (self.filename, len(self.chunks)))
        else:
            if len(self.chunks) != 3:
                rejected = True
                self.reject("%s: found %d chunks, expected 3." % (self.filename, len(self.chunks)))
        if self.chunks[0] != "debian-binary":
            rejected = True
            self.reject("%s: first chunk is '%s', expected 'debian-binary'." % (self.filename, self.chunks[0]))
        if not rejected and self.chunks[1] != "control.tar.gz":
            rejected = True
            self.reject("%s: second chunk is '%s', expected 'control.tar.gz'." % (self.filename, self.chunks[1]))
        if not rejected and self.chunks[2] not in [ "data.tar.bz2", "data.tar.gz" ]:
            rejected = True
            self.reject("%s: third chunk is '%s', expected 'data.tar.gz' or 'data.tar.bz2'." % (self.filename, self.chunks[2]))

        return not rejected

    def scan_package(self, bootstrap_id=0, relaxed=False, session=None):
        """
        Unpack the .deb, do sanity checking, and gather info from it.

        Currently information gathering consists of getting the contents list. In
        the hopefully near future, it should also include gathering info from the
        control file.

        @type bootstrap_id: int
        @param bootstrap_id: the id of the binary these packages
          should be associated or zero meaning we are not bootstrapping
          so insert into a temporary table

        @return: True if the deb is valid and contents were imported
        """
        result = False
        rejected = not self.valid_deb(relaxed)
        if not rejected:
            self.__unpack()


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
                        result = insert_content_paths(bootstrap_id, [tarinfo.name for tarinfo in data if not tarinfo.isdir()], session)
                    else:
                        pkgs = deb822.Packages.iter_paragraphs(file(os.path.join(self.tmpdir,'control')))
                        pkg = pkgs.next()
                        result = insert_pending_content_paths(pkg,
                                                              self.filename.endswith('.udeb'),
                                                              [tarinfo.name for tarinfo in data if not tarinfo.isdir()],
                                                              session)

                except:
                    traceback.print_exc()

            os.chdir(cwd)
        self._cleanup()
        return result

    def check_utf8_package(self, package):
        """
        Unpack the .deb, do sanity checking, and gather info from it.

        Currently information gathering consists of getting the contents list. In
        the hopefully near future, it should also include gathering info from the
        control file.

        @type package: string
        @param package: the name of the package to be checked

        @rtype: boolean
        @return: True if the deb is valid and contents were imported
        """
        rejected = not self.valid_deb(True)
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

                result = True

            except:
                traceback.print_exc()
                result = False

            os.chdir(cwd)

        return result

__all__.append('Binary')


def copy_temporary_contents(binary, bin_association, reject, session=None):
    """
    copy the previously stored contents from the temp table to the permanant one

    during process-unchecked, the deb should have been scanned and the
    contents stored in pending_content_associations
    """

    cnf = Config()

    privatetrans = False
    if session is None:
        session = DBConn().session()
        privatetrans = True

    arch = get_architecture(archname, session=session)

    pending = session.query(PendingBinContents).filter_by(package=binary.package,
                                                          version=binary.version,
                                                          arch=binary.arch).first()

    if pending:
        # This should NOT happen.  We should have added contents
        # during process-unchecked.  if it did, log an error, and send
        # an email.
        subst = {
            "__PACKAGE__": package,
            "__VERSION__": version,
            "__ARCH__": arch,
            "__TO_ADDRESS__": cnf["Dinstall::MyAdminAddress"],
            "__DAK_ADDRESS__": cnf["Dinstall::MyEmailAddress"] }

        message = utils.TemplateSubst(subst, cnf["Dir::Templates"]+"/missing-contents")
        utils.send_mail(message)

        # rescan it now
        exists = Binary(deb, reject).scan_package()

        if not exists:
            # LOG?
            return False

    component = binary.poolfile.location.component
    override = session.query(Override).filter_by(package=binary.package,
                                                 suite=bin_association.suite,
                                                 component=component.id).first()
    if not override:
        # LOG?
        return False


    if not override.overridetype.type.endswith('deb'):
        return True

    if override.overridetype.type == "udeb":
        table = "udeb_contents"
    elif override.overridetype.type == "deb":
        table = "deb_contents"
    else:
        return False
    

    if component.name == "main":
        component_str = ""
    else:
        component_str = component.name + "/"
        
    vals = { 'package':binary.package,
             'version':binary.version,
             'arch':binary.architecture,
             'binary_id': binary.id,
             'component':component_str,
             'section':override.section.section
             }

    session.execute( """INSERT INTO %s
    (binary_id,package,version.component,arch,section,filename)
    SELECT :binary_id, :package, :version, :component, :arch, :section
    FROM pending_bin_contents pbc
    WHERE pbc.package=:package
    AND pbc.version=:version
    AND pbc.arch=:arch""" % table, vals )

    session.execute( """DELETE from pending_bin_contents package=:package
    AND version=:version
    AND arch=:arch""", vals )

    if privatetrans:
        session.commit()
        session.close()

    return exists

__all__.append('copy_temporary_contents')


