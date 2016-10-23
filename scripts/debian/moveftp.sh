#!/bin/bash

set -e
set -u

FTPDIR="/srv/upload.debian.org/ftp/pub/UploadQueue/"
SSHDIR="/srv/upload.debian.org/UploadQueue/"
HOST=$(hostname -s)

if [[ ${HOST} == coccia ]]; then
    find ${FTPDIR} -type f -mmin +15 -print0 -exec mv --no-clobber --target-directory=${SSHDIR} -- "{}" +
elif [[ ${HOST} == usper ]]; then
    find ${FTPDIR} -maxdepth 1 -type f -mmin +15 -print0 -exec mv --no-clobber --target-directory=${SSHDIR} -- "{}" +
    for defdir in {1..15}; do
        find ${FTPDIR}/DELAYED/${defdir}-day -maxdepth 1 -type f -mmin +15 -print0 -exec mv --no-clobber --target-directory=${SSHDIR}/DELAYED/${defdir}-day -- "{}" +
    done
fi
