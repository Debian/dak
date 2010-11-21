#!/bin/bash

dak make-pkg-file-mapping | bzip2 -9 > /org/security-master.debian.org/ftp/indices/package-file.map.bz2
