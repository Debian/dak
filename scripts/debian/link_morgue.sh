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
    franck)
	SCRIPTVARS=/srv/ftp-master.debian.org/dak/config/debian/vars
	archive=ftp-master
        ;;
    chopin)
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

cd "${PROCESSDIR}"
log "Processing ${PROCESSDIR}"
find ${PROCESSDIR} -type f |
while read mfile; do
    # Get the files sha1sum
    mshasum=$(sha1sum ${mfile})
    mshasum=${mshasum%% *}

    # And now get the "levels" of the farm
    if [[ ${mshasum} =~ ([0-9a-z][0-9a-z])([0-9a-z][0-9a-z]).* ]]; then
        LVL1=${BASH_REMATCH[1]}
        LVL2=${BASH_REMATCH[2]}
    else
        log "Ups, unknown error in regex for ${mfile} (${mshasum})"
        continue
    fi

    # See if we have a target
    if [ "$(hostname -s)" = "stabile" ]; then
        # If we run on the snapshot host directly just look locally
        if [ -f "${FARMBASE}/${LVL1}/${LVL2}/${mshasum}" ]; then
            ln -sf "${FARMBASE}/${LVL1}/${LVL2}/${mshasum}" "${mfile}"
        fi
    else
        # If we run wherever, use curl and the http interface
        if curl --fail --silent --max-time 120 --head ${FARMURL}/${mshasum} >/dev/null; then
            # Yes, lets symlink it
            # Yay for tons of dangling symlinks, but when this is done a rsync
            # will run and transfer the whole shitload of links over to the morgue host.
            ln -sf "${FARMBASE}/${LVL1}/${LVL2}/${mshasum}" "${mfile}"
        fi
    fi
done # for mfile in...

# And now, maybe, transfer stuff over to stabile...
if [ "$(hostname -s)" != "stabile" ]; then
    cd "${PROCESSDIR}"
    LISTFILE=$(mktemp -p ${TMPDIR} )

    # We only transfer symlinks or files changed more than 14 days ago
    # (assuming we won't ever find anything on snapshot for them)
    find . \( -type l -o \( -type f -ctime 14 \) \) -print0 >${LISTFILE}

    # morgue-sync has to be setup in ~/.ssh/config and the authorized_keys
    # on the other side should contain (one line, no #)
# command="rsync --server -lHogDtpRe.Lsf --remove-source-files . /srv/morgue.debian.org/sync/ftp-master",
# no-port-forwarding,no-X11-forwarding,no-agent-forwarding,from="ftp-master.debian.org" ssh-rsa...
    rsync -aHq -e "ssh -o Batchmode=yes -o ConnectTimeout=30 -o SetupTimeout=30 " --remove-source-files --from0 --files-from=${LISTFILE} $base/morgue/ morgue-sync:/srv/morgue.debian.org/sync/$archive

    # And remove empty subdirs. To remove entire hierarchies we probably should run this
    # in a loop, but why bother? They'll be gone in a few days then, so meh.
    find "${PROCESSDIR}" -type d -empty -print0 | xargs --no-run-if-empty -0 rmdir
fi
