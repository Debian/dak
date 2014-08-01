#!/bin/bash

set -e
set -u

FTPDIR="/srv/upload.debian.org/ftp/pub/UploadQueue/"
SSHDIR="/srv/upload.debian.org/UploadQueue/"

find ${FTPDIR} -type f -mmin +15 -print0 -exec mv --no-clobber --target-directory=${SSHDIR} -- "{}" +
