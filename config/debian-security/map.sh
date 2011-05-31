#!/bin/bash

dak make-pkg-file-mapping | bzip2 -9 > /srv/security-master.debian.org/ftp/indices/package-file.map.bz2
