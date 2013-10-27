#!/usr/bin/env python
"""
Helper code for file writing with optional compression.

@contact: Debian FTPMaster <ftpmaster@debian.org>
@copyright: 2011 Torsten Werner <twerner@debian.org>
@license: GNU General Public License version 2 or later
"""

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

from daklib.config import Config

from daklib.daksubprocess import check_call

import os, os.path

class BaseFileWriter(object):
    '''
    Base class for compressed and uncompressed file writing.
    '''
    def __init__(self, template, **keywords):
        '''
        The template argument is a string template like
        "dists/%(suite)s/%(component)s/Contents-%(architecture)s.gz" that
        should be relative to the archive's root directory. The keywords
        include strings for suite, component, architecture and booleans
        uncompressed, gzip, bzip2.
        '''
        compression = keywords.get('compression', ['none'])
        self.uncompressed = 'none' in compression
        self.gzip = 'gzip' in compression
        self.bzip2 = 'bzip2' in compression
        self.xz = 'xz' in compression
        self.path = template % keywords

    def open(self):
        '''
        Returns a file object for writing.
        '''
        # create missing directories
        try:
            os.makedirs(os.path.dirname(self.path))
        except:
            pass
        self.file = open(self.path + '.new', 'w')
        return self.file

    # internal helper function
    def rename(self, filename):
        tempfilename = filename + '.new'
        os.chmod(tempfilename, 0o644)
        os.rename(tempfilename, filename)

    # internal helper function to compress output
    def compress(self, cmd, suffix, path):
        in_filename = "{0}.new".format(path)
        out_filename = "{0}.{1}.new".format(path, suffix)
        with open(in_filename, 'r') as in_fh, open(out_filename, 'w') as out_fh:
            check_call(cmd, stdin=in_fh, stdout=out_fh)
        self.rename("{0}.{1}".format(path, suffix))

    def close(self):
        '''
        Closes the file object and does the compression and rename work.
        '''
        self.file.close()
        if self.gzip:
            self.compress(['gzip', '-9cn', '--rsyncable'], 'gz', self.path)
        if self.bzip2:
            self.compress(['bzip2', '-9'], 'bz2', self.path)
        if self.xz:
            self.compress(['xz', '-c'], 'xz', self.path)
        if self.uncompressed:
            self.rename(self.path)
        else:
            os.unlink(self.path + '.new')

class BinaryContentsFileWriter(BaseFileWriter):
    def __init__(self, **keywords):
        '''
        The value of the keywords suite, component, and architecture are
        strings. The value of component may be omitted if not applicable.
        Output files are gzip compressed only.
        '''
        flags = {
            'compression': ['gzip'],
        }
        flags.update(keywords)
        if flags['debtype'] == 'deb':
            template = "%(archive)s/dists/%(suite)s/%(component)s/Contents-%(architecture)s"
        else: # udeb
            template = "%(archive)s/dists/%(suite)s/%(component)s/Contents-udeb-%(architecture)s"
        BaseFileWriter.__init__(self, template, **flags)

class SourceContentsFileWriter(BaseFileWriter):
    def __init__(self, **keywords):
        '''
        The value of the keywords suite and component are strings.
        Output files are gzip compressed only.
        '''
        flags = {
            'compression': ['gzip'],
        }
        flags.update(keywords)
        template = "%(archive)s/dists/%(suite)s/%(component)s/Contents-source"
        BaseFileWriter.__init__(self, template, **flags)

class PackagesFileWriter(BaseFileWriter):
    def __init__(self, **keywords):
        '''
        The value of the keywords suite, component, debtype and architecture
        are strings.  Output files are gzip compressed only.
        '''
        flags = {
            'compression': ['gzip', 'xz'],
        }
        flags.update(keywords)
        if flags['debtype'] == 'deb':
            template = "%(archive)s/dists/%(suite)s/%(component)s/binary-%(architecture)s/Packages"
        else: # udeb
            template = "%(archive)s/dists/%(suite)s/%(component)s/debian-installer/binary-%(architecture)s/Packages"
        BaseFileWriter.__init__(self, template, **flags)

class SourcesFileWriter(BaseFileWriter):
    def __init__(self, **keywords):
        '''
        The value of the keywords suite and component are strings. Output
        files are gzip compressed only.
        '''
        flags = {
            'compression': ['gzip', 'xz'],
        }
        flags.update(keywords)
        template = "%(archive)s/dists/%(suite)s/%(component)s/source/Sources"
        BaseFileWriter.__init__(self, template, **flags)

class TranslationFileWriter(BaseFileWriter):
    def __init__(self, **keywords):
        '''
        The value of the keywords suite, component and language are strings.
        Output files are bzip2 compressed only.
        '''
        flags = {
            'compression': ['bzip2'],
            'language':     'en',
        }
        flags.update(keywords)
        template = "%(archive)s/dists/%(suite)s/%(component)s/i18n/Translation-%(language)s"
        super(TranslationFileWriter, self).__init__(template, **flags)
