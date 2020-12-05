#! /usr/bin/env python3
#
# Copyright (C) 2017, Niels Thykier <niels@thykier.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import tempfile
import shutil
from base_test import DakTestCase

from daklib.filewriter import (BinaryContentsFileWriter,
                               SourceContentsFileWriter,
                               SourcesFileWriter,
                               PackagesFileWriter,
                               TranslationFileWriter)

SUITE = 'unstable'
COMPONENT = 'main'
ARCH = 'amd64'
LANG = 'en'


class FileWriterTest(DakTestCase):

    def test_writer_test(self):
        tmpdir = tempfile.mkdtemp()
        try:
            dbcfw = BinaryContentsFileWriter(archive=tmpdir,
                                             suite=SUITE,
                                             component=COMPONENT,
                                             architecture=ARCH,
                                             debtype='deb')
            ubcdw = BinaryContentsFileWriter(archive=tmpdir,
                                             suite=SUITE,
                                             component=COMPONENT,
                                             architecture=ARCH,
                                             debtype='udeb')
            scfw = SourceContentsFileWriter(archive=tmpdir,
                                            suite=SUITE,
                                            component=COMPONENT)
            sfw = SourcesFileWriter(archive=tmpdir,
                                    suite=SUITE,
                                    component=COMPONENT)
            dpfw = PackagesFileWriter(archive=tmpdir,
                                      suite=SUITE,
                                      component=COMPONENT,
                                      architecture=ARCH,
                                      debtype='deb')
            upfw = PackagesFileWriter(archive=tmpdir,
                                      suite=SUITE,
                                      component=COMPONENT,
                                      architecture=ARCH,
                                      debtype='udeb')
            tfw = TranslationFileWriter(archive=tmpdir,
                                        suite=SUITE,
                                        component=COMPONENT,
                                        language=LANG)
            file_writers = [
                dbcfw,
                ubcdw,
                scfw,
                sfw,
                dpfw,
                upfw,
                tfw,
            ]
            for writer in file_writers:
                fd = writer.open()
                fd.write('hallo world')
                writer.close()
                # TODO, verify that it created the correct files.
                # (currently we just test it does not crash).
        finally:
            shutil.rmtree(tmpdir)
