#!/bin/bash

set -e
set -u

QUEUEHOSTS="queue-coccia"
FTPDIR="/srv/upload.debian.org/ftp/pub/UploadQueue/"
SSHDIR="/srv/upload.debian.org/UploadQueue/"
HOST=$(hostname -s)

# This runs on all queue hosts - merge ftp and ssh together. (The queued on usper only processes
# the SSHDIR)
find ${FTPDIR} -maxdepth 1 -type f -mmin +5 -print0 -exec mv --no-clobber --target-directory=${SSHDIR} -- "{}" +
for defdir in {1..15}; do
    find ${FTPDIR}/DELAYED/${defdir}-day -maxdepth 1 -type f -mmin +5 -print0 -exec mv --no-clobber --target-directory=${SSHDIR}/DELAYED/${defdir}-day -- "{}" +
done

# If we are the master host, we have a little extrawork to do, collect all
# files from other queue hosts.
if [[ ${HOST} == usper ]]; then
    # And now fetch all files from the queue hosts
    cd ${SSHDIR}
    for host in ${QUEUEHOSTS}; do
        rsync -aOq --ignore-existing --remove-source-files -e 'ssh -F /srv/ftp-master.debian.org/dak/config/homedir/ssh/usper-config'  ${host}:/does/not/matter . || true
    done
fi
