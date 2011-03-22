#!/bin/bash

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


set -e
set -u
set -E

export LANG=C
export LC_ALL=C

export SCRIPTVARS=/srv/ftp-master.debian.org/dak/config/debian/vars
. $SCRIPTVARS

cleanup() {
    rm -f "${HOME}/sync.lock"
}
trap cleanup EXIT TERM HUP INT QUIT

# not using $lockdir as thats inside the rsync dir, and --delete would
# kick the lock away. Yes we could exclude it, but wth bother?
#
# Also, NEVER use --delete-excluded!
if lockfile -r3 ${HOME}/sync.lock; then
    cd $base/
    rsync -aH -B8192 \
	    --exclude backup/*.xz \
	    --exclude backup/dump* \
	    --exclude ftp/ \
	    --exclude mirror/ \
	    --exclude morgue/ \
	    --exclude=lost+found/ \
	    --exclude .da-backup.trace \
	    --delete \
	    --delete-after \
	    --timeout 3600 \
	    -e 'ssh -o ConnectTimeout=30 -o SetupTimeout=30' \
	    ftpmaster-sync:/srv/ftp-master.debian.org/ .

    cd $public/
    rsync -avH -B8192 \
	    --exclude mirror \
	    --exclude rsync/ \
	    --exclude=lost+found/ \
	    --exclude .da-backup.trace \
	    --exclude web-users/ \
	    --delete \
	    --delete-after \
	    --timeout 3600 \
	    -e 'ssh -o ConnectTimeout=30 -o SetupTimeout=30' \
	    ftpmaster-sync2:/srv/ftp.debian.org/ .

else
    echo "Couldn't get the lock, not syncing"
    exit 0
fi


## ftpmaster-sync is defined in .ssh/config as:
# Host ftpmaster-sync
#   Hostname franck.debian.org
#   User dak
#   IdentityFile ~dak/.ssh/syncftpmaster
#   ForwardX11 no
#   ForwardAgent no
#   StrictHostKeyChecking yes
#   PasswordAuthentication no
#   BatchMode yes

## ftpmaster-sync2 is the same, just a second ssh key
