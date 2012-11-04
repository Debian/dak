#!/bin/bash

set -e
set -u
set -E

export SCRIPTVARS=/srv/security-master.debian.org/dak/config/debian-security/vars
. $SCRIPTVARS

# Make sure we start out with a sane umask setting
umask 022

# And use one locale, no matter what the caller has set
export LANG=C
export LC_ALL=C

. "${configdir}/../debian/common"

# extract changelogs and stuff
function changelogs() {
    log "Extracting changelogs"
    dak make-changelog -e -a security
    mkdir -p ${exportpublic}/changelogs
    cd ${exportpublic}/changelogs
    rsync -aHW --delete --delete-after --ignore-errors ${exportdir}/changelogs/. .
    sudo -H -u archvsync /home/archvsync/runmirrors metasdo > ~dak/runmirrors-metadata.log 2>&1 &
}

changelogs
