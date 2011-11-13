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

PROCESSDIR="/srv/morgue.debian.org"
FARMBASE="/srv/snapshot.debian.org/farm"

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
    if [ -f "${FARMBASE}/${LVL1}/${LVL2}/${mshasum}" ]; then
        # Yes, lets symlink it
        log "Symlinking ${mfile} to ${FARMBASE}/${LVL1}/${LVL2}/${mshasum}"
        ln -sf "${FARMBASE}/${LVL1}/${LVL2}/${mshasum}" "${mfile}"
    else
        # No, just tell
        log "No symlink target for ${mfile}"
    fi
done # mfile read mfile
