#!/bin/bash

# Copyright (C) 2008,2010 Joerg Jaspert <joerg@debian.org>

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

# This script can be called as `import_dataset.sh --from-ssh-command`.
# In this case SSH_ORIGINAL_COMMAND is expected to be of the form
#     import_dataset.sh <suite> <md5sum>
if [ "${1}" = "--from-ssh-command" ]; then
    set -- ${SSH_ORIGINAL_COMMAND}
    if [ $1 != "import_dataset.sh" ]; then
        echo >&2 "E: expect to be called as 'import_dataset.sh <suite> <md5sum>'"
        exit 1
    fi
    shift
    if [ $# -ne 2 ]; then
        echo >&2 "E: expect exacly two arguments (suite, md5sum)"
        exit 1
    fi
    SSH_ORIGINAL_COMMAND="${2}"
fi

IMPORTSUITE=${1:-"testing"}
BRITNEY=""
MD5SUM="${SSH_ORIGINAL_COMMAND}"

case "${IMPORTSUITE}" in
    testing)
        DO_CHANGELOG="true"
        ;;
    testing-debug|testing-proposed-updates|wheezy-updates|jessie-updates|stretch-updates|buster-updates)
        DO_CHANGELOG="false"
        ;;
    *)
        echo "You are so wrong here that I can't even believe it. Sod off."
        exit 42
        ;;
esac

# Change to a known safe location
cd $masterdir

echo "Importing new data for ${IMPORTSUITE} into database"

if [ "x${DO_CHANGELOG}x" = "xtruex" ]; then
    rm -f ${ftpdir}/dists/${IMPORTSUITE}/ChangeLog
    BRITNEY=" --britney"
fi

tmpfile=$(mktemp)
trap "rm -f ${tmpfile}" EXIT
cat > ${tmpfile}
if ! echo "${MD5SUM}  ${tmpfile}" | md5sum -c --quiet; then
    exit 42
fi
dak control-suite --set ${IMPORTSUITE} ${BRITNEY} < ${tmpfile}

if [ "x${DO_CHANGELOG}x" = "xtruex" ]; then
    NOW=$(date "+%Y%m%d%H%M")
    cd ${ftpdir}/dists/${IMPORTSUITE}/
    mv ChangeLog ChangeLog.${NOW}
    ln -s ChangeLog.${NOW} ChangeLog
    find . -maxdepth 1 -mindepth 1 -type f -mmin +2880 -name 'ChangeLog.*' -delete
fi

#echo "Regenerating Packages/Sources files, be patient"
#dak generate-packages-sources2 -s ${IMPORTSUITE} >/dev/null

echo "Done"

exit 0
