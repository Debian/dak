#!/bin/bash

# No way I try to deal with a crippled sh just for POSIX foo.

# Copyright (C) 2011 Joerg Jaspert <joerg@debian.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; version 2.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

# Homer: Are you saying you're never going to eat any animal again? What
#        about bacon?
# Lisa: No.
# Homer: Ham?
# Lisa: No.
# Homer: Pork chops?
# Lisa: Dad, those all come from the same animal.
# Homer: Heh heh heh. Ooh, yeah, right, Lisa. A wonderful, magical animal.

# Let files inside morgue be symlinks to the snapshot farm

# exit on errors
set -e
# make sure to only use defined variables
set -u
# ERR traps should be inherited from functions too. (And command
# substitutions and subshells and whatnot, but for us the functions is
# the important part here)
set -E

# Make sure we start out with a sane umask setting
umask 022

# And use one locale, no matter what the caller has set
export LANG=C
export LC_ALL=C

# log something (basically echo it together with a timestamp)
# Set $PROGRAM to a string to have it added to the output.
function log () {
        local prefix=${PROGRAM:-$0}
        echo "$(date +"%b %d %H:%M:%S") $(hostname -s) ${prefix}[$$]: $@"
}

case "$(hostname)" in
    fasolo)
	SCRIPTVARS=/srv/ftp-master.debian.org/dak/config/debian/vars
	archive=ftp-master
        ;;
    seger)
	SCRIPTVARS=/srv/security-master.debian.org/dak/config/debian-security/vars
	archive=security-master
	;;
    *)
	echo "Unknown host $(hostname)" >&2
	exit 1
	;;
esac

export SCRIPTVARS
. $SCRIPTVARS

function byebye_lock() {
    rm -f $lockdir/link_morgue
}

lockfile -l 3600 $lockdir/link_morgue
trap byebye_lock ERR EXIT TERM HUP INT QUIT

PROCESSDIR="${base}/morgue"
FARMBASE="/srv/snapshot.debian.org/farm"
FARMURL="http://snapshot.debian.org/file/"
PROGRAM="link_morgue"
DBHOST="lw08.debian.org"
HASHFILE="${dbdir}/hashes"
NOW=$(date -Is)

# We have to prepare our file with list of hashes. We get it directly
# from the snapshot db. Thats a costly operation taking some 15 or so
# minutes, but still better than the rate limiting we run into when
# using the web api.
#
# The preparehashes is an otion the ssh forced command on the remote
# host uses to generate a nice file with hashes, one per line. It does
# so by running something like "psql service=snapshot-guest -c "select
# hash from file" > somefile", then packs the file. To not stress the
# db host too much with that query, it only refreshes the file if its
# older than 24 hours.
out=""
out=$(ssh ${DBHOST} preparehashes)

# And now we get us the file here, so we can easily lookup hashes.
# (the rsync uses the same ssh key and runs into the forced command.
# That just knows to send the file for rsync instead of preparing it.)
cd "${dbdir}"
rsync ${DBHOST}:/srv/ftp-master.debian.org/home/hashes.gz ${HASHFILE}.gz

cd "${PROCESSDIR}"
log "Processing ${PROCESSDIR}"
${scriptsdir}/link_morgue \
             --known-hashes ${HASHFILE}.gz \
             --farmdir "${FARMBASE}" \
             --morguedir "${PROCESSDIR}"

# And now, maybe, transfer stuff over to stabile...
if [ "$(hostname -s)" != "stabile" ]; then
    cd "${PROCESSDIR}"
    LISTFILE=$(mktemp -p ${TMPDIR} )

    # We only transfer symlinks or files changed more than 14 days ago
    # (assuming we won't ever find anything on snapshot for them)
    find . \( -type l -o \( -type f -ctime +14 \) \) -print0 >${LISTFILE}

    # morgue-sync has to be setup in ~/.ssh/config and the authorized_keys
    # on the other side should contain (one line, no #)
# command="rsync --server -lHogDtpRe.Lsf --remove-source-files . /srv/morgue.debian.org/sync/ftp-master",
# restrict,from="ftp-master.debian.org" ssh-rsa...
    rsync -aHq -e "ssh -o Batchmode=yes -o ConnectTimeout=30 -o SetupTimeout=30 " --remove-source-files --from0 --files-from=${LISTFILE} $base/morgue/ morgue-sync:/srv/morgue.debian.org/sync/$archive

    # And remove empty subdirs. To remove entire hierarchies we probably should run this
    # in a loop, but why bother? They'll be gone in a few days then, so meh.
    find "${PROCESSDIR}" -type d -empty -print0 | xargs --no-run-if-empty -0 rmdir
fi
