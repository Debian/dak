# Copyright (C) 2015, Ansgar Burchardt <ansgar@debian.org>
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

"""
Helper methods to deal with (de)compressing files
"""

import os
import shutil
import subprocess


def decompress_xz(input, output):
    subprocess.check_call(["xz", "--decompress"], stdin=input, stdout=output)


def decompress_bz2(input, output):
    subprocess.check_call(["bzip2", "--decompress"], stdin=input, stdout=output)


def decompress_gz(input, output):
    subprocess.check_call(["gzip", "--decompress"], stdin=input, stdout=output)


decompressors = {
    '.xz': decompress_xz,
    '.bz2': decompress_bz2,
    '.gz': decompress_gz,
}


def decompress(input, output, filename=None):
    if filename is None:
        filename = input.name

    base, ext = os.path.splitext(filename)
    decompressor = decompressors.get(ext, None)
    if decompressor is not None:
        decompressor(input, output)
    else:
        shutil.copyfileobj(input, output)
