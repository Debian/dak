#!/bin/bash

set -e
set -u

FTPDIR="/org/upload.debian.org/ftp/pub/UploadQueue/"
SSHDIR="/org/upload.debian.org/UploadQueue/"

yes n | find ${FTPDIR} -type f -mmin +15 -print0 -exec mv -i --target-directory=${SSHDIR} "{}" +
