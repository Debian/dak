#!/bin/bash

set -e
set -u

QUEUEHOSTS="queue-coccia"
FTPDIR="/srv/upload.debian.org/ftp/pub/UploadQueue/"
SSHDIR="/srv/upload.debian.org/UploadQueue/"
PROCESSDELAYED=1
HOST=$(hostname -s)

# Only one of me should ever run.
FLOCKER=${FLOCKER:-""}
[[ ${FLOCKER} != $0 ]] && exec env FLOCKER="$0" flock -E 0 -en "$0" "$0" "$@" || :

# For usper, targetdir is the sshdir, everywhere else, its a separate
# one, so we avoid fetching partial uploads from their sshdir.
if [[ ${HOST} == usper ]]; then
    TARGETDIR="${SSHDIR}"
    TOPROCESS="${FTPDIR}"
elif [[ ${HOST} == suchon ]]; then
    TARGETDIR=/srv/security.upload.debian.org/SecurityUploadQueue/
    TOPROCESS=/srv/security.upload.debian.org/ftp/pub/SecurityUploadQueue/
    PROCESSDELAYED=
else
    TARGETDIR="/srv/upload.debian.org/mergedtree"
    TOPROCESS="${FTPDIR} ${SSHDIR}"
fi

# This runs on all queue hosts - merge ftp and ssh together. (The queued on usper only processes
# the TARGETDIR)
for sourcedir in ${TOPROCESS}; do
    find ${sourcedir} -maxdepth 1 -type f -mmin +5 -print0 -exec mv --no-clobber --target-directory=${TARGETDIR} -- "{}" +
    if [[ -n "${PROCESSDELAYED}" ]]; then
        for defdir in {0..15}; do
            find ${sourcedir}/DELAYED/${defdir}-day -maxdepth 1 -type f -mmin +5 -print0 -exec mv --no-clobber --target-directory=${TARGETDIR}/DELAYED/${defdir}-day -- "{}" +
        done
    fi
done

# If we are the master host, we have a little extra work to do, collect all
# files from other queue hosts.
if [[ ${HOST} == usper ]]; then
    # And now fetch all files from the queue hosts
    cd ${SSHDIR}
    for host in ${QUEUEHOSTS}; do
        rsync -aOq --ignore-existing --remove-source-files -e 'ssh -F /srv/ftp-master.debian.org/dak/config/homedir/ssh/usper-config'  ${host}:/does/not/matter . || true
    done
fi
