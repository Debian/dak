#!/bin/bash

# Copyright (C) 2008,2010 Joerg Jaspert <joerg@debian.org>
# Copyright (C) 2011 Mark Hymers <mhy@debian.org>

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


set -e
set -u

# Load up some standard variables
export SCRIPTVARS=/srv/ftp-master.debian.org/dak/config/debian/vars
. $SCRIPTVARS

tempfile=$(mktemp)
trap "rm -f ${tempfile}" EXIT

cat > ${tempfile}
expected_checksum="${SSH_ORIGINAL_COMMAND}"
if ! echo "${expected_checksum} ${tempfile}" | md5sum --check --quiet; then
    exit 1
fi

# Change to a known safe location
cd $masterdir

SUITE="testing-proposed-updates"

echo "Performing cleanup on ${SUITE}"

dak control-suite --remove ${SUITE} < ${tempfile}

echo "Done"

exit 0
