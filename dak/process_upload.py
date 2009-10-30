#!/usr/bin/env python

"""
Checks Debian packages from Incoming
@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@copyright: 2009  Joerg Jaspert <joerg@debian.org>
@copyright: 2009  Mark Hymers <mhy@debian.org>
@copyright: 2009  Frank Lichtenheld <djpig@debian.org>
@license: GNU General Public License version 2 or later
"""

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

# based on process-unchecked and process-accepted

## pu|pa: locking (daily.lock)
## pu|pa: parse arguments -> list of changes files
## pa: initialize urgency log
## pu|pa: sort changes list

## foreach changes:
###  pa: load dak file
##   pu: copy CHG to tempdir
##   pu: check CHG signature
##   pu: parse changes file
##   pu: checks:
##     pu: check distribution (mappings, rejects)
##     pu: copy FILES to tempdir
##     pu: check whether CHG already exists in CopyChanges
##     pu: check whether FILES already exist in one of the policy queues
##     for deb in FILES:
##       pu: extract control information
##       pu: various checks on control information
##       pu|pa: search for source (in CHG, projectb, policy queues)
##       pu|pa: check whether "Version" fulfills target suite requirements/suite propagation
##       pu|pa: check whether deb already exists in the pool
##     for src in FILES:
##       pu: various checks on filenames and CHG consistency
##       pu: if isdsc: check signature
##     for file in FILES:
##       pu: various checks
##       pu: NEW?
##       //pu: check whether file already exists in the pool
##       pu: store what "Component" the package is currently in
##     pu: check whether we found everything we were looking for in CHG
##     pu: check the DSC:
##       pu: check whether we need and have ONE DSC
##       pu: parse the DSC
##       pu: various checks //maybe drop some of the in favor of lintian
##       pu|pa: check whether "Version" fulfills target suite requirements/suite propagation
##       pu: check whether DSC_FILES is consistent with "Format"
##       for src in DSC_FILES:
##         pu|pa: check whether file already exists in the pool (with special handling for .orig.tar.gz)
##     pu: create new tempdir
##     pu: create symlink mirror of source
##     pu: unpack source
##     pu: extract changelog information for BTS
##     //pu: create missing .orig symlink
##     pu: check with lintian
##     for file in FILES:
##       pu: check checksums and sizes
##     for file in DSC_FILES:
##       pu: check checksums and sizes
##     pu: CHG: check urgency
##     for deb in FILES:
##       pu: extract contents list and check for dubious timestamps
##     pu: check that the uploader is actually allowed to upload the package
###  pa: install:
###    if stable_install:
###      pa: remove from p-u
###      pa: add to stable
###      pa: move CHG to morgue
###      pa: append data to ChangeLog
###      pa: send mail
###      pa: remove .dak file
###    else:
###      pa: add dsc to db:
###        for file in DSC_FILES:
###          pa: add file to file
###          pa: add file to dsc_files
###        pa: create source entry
###        pa: update source associations
###        pa: update src_uploaders
###      for deb in FILES:
###        pa: add deb to db:
###          pa: add file to file
###          pa: find source entry
###          pa: create binaries entry
###          pa: update binary associations
###      pa: .orig component move
###      pa: move files to pool
###      pa: save CHG
###      pa: move CHG to done/
###      pa: change entry in queue_build
##   pu: use dispatch table to choose target queue:
##     if NEW:
##       pu: write .dak file
##       pu: move to NEW
##       pu: send mail
##     elsif AUTOBYHAND:
##       pu: run autobyhand script
##       pu: if stuff left, do byhand or accept
##     elsif targetqueue in (oldstable, stable, embargo, unembargo):
##       pu: write .dak file
##       pu: check overrides
##       pu: move to queue
##       pu: send mail
##     else:
##       pu: write .dak file
##       pu: move to ACCEPTED
##       pu: send mails
##       pu: create files for BTS
##       pu: create entry in queue_build
##       pu: check overrides
