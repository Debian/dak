#!/bin/bash

set -e

LANG=C
LC_ALL=C

echo "Regenerating \"public\" mirror/ hardlink fun"
date -u > /srv/security-master.debian.org/ftp/project/trace/security-master.debian.org
echo "Using dak v1" >> /srv/security-master.debian.org/ftp/project/trace/security-master.debian.org
echo "Running on host: $(hostname -f)" >> /srv/security-master.debian.org/ftp/project/trace/security-master.debian.org
cd /srv/security.debian.org/archive/debian-security/
rsync -aH --link-dest /srv/security-master.debian.org/ftp/ --exclude Archive_Maintenance_In_Progress --delete --delete-after --ignore-errors /srv/security-master.debian.org/ftp/. .
