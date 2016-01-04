#!/bin/bash

set -e

LANG=C.UTF-8
LC_ALL=C.UTF-8
TRACEFILE=/srv/security-master.debian.org/ftp/project/trace/security-master.debian.org

echo "Regenerating \"public\" mirror/ hardlink fun"

DATE_SERIAL=$(date +"%Y%m%d01")
FILESOAPLUS1=$(awk '/serial/ { print $3+1 }' ${TRACEFILE} || echo ${DATE_SERIAL} )
if [[ ${DATE_SERIAL} -gt ${FILESOAPLUS1}  ]]; then
    SERIAL="${DATE_SERIAL}"
else
    SERIAL="${FILESOAPLUS1}"
fi
date -u > ${TRACEFILE}
rfc822date=$(LC_ALL=POSIX LANG=POSIX date -u -R)
echo "Using dak v1" >> ${TRACEFILE}
echo "Running on host: $(hostname -f)" >> ${TRACEFILE}
echo "Archive serial: ${SERIAL}" >> ${TRACEFILE}
echo "Date: ${rfc822date}"
cd /srv/security-master.debian.org/ftp/project/trace/
ln -sf security-master.debian.org master
cd /srv/security.debian.org/archive/debian-security/
rsync -aH --link-dest /srv/security-master.debian.org/ftp/ --exclude Archive_Maintenance_In_Progress --delete --delete-after --ignore-errors /srv/security-master.debian.org/ftp/. .
