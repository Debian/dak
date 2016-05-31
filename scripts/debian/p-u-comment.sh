#!/bin/bash

# Copyright © 2016 Emilio Pozuelo Monfort <pochu@debian.org>

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

. "${configdir}/common"

CMD=(${SSH_ORIGINAL_COMMAND})
COMMAND="${CMD[0]^^}"
QUEUE="${CMD[1]}"
PACKAGE="${CMD[2]}"

case "${QUEUE}" in
    p-u-new|o-p-u-new|o-o-p-u-new)
        ;;
    *)
        echo "Invalid policy queue ${QUEUE}."
        exit 42
        ;;
esac

case "${COMMAND}" in
    ACCEPT|REJECT)
        ;;
    *)
        echo "Invalid command ${COMMAND}."
        exit 42
        ;;
esac

destdir=${queuedir}/${QUEUE}/COMMENTS/
cd $destdir

echo "Importing new ${COMMAND} comment file for ${PACKAGE} into ${QUEUE}"

trap cleanup EXIT

tmpfile=$( gettempfile )
destfile=${COMMAND}.${PACKAGE}

cat > ${tmpfile}
chmod a+r ${tmpfile}

mv ${tmpfile} ${destfile}

echo "Done"

exit 0
