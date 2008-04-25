#
# Makefile for debianqueued -- only targets for package maintainance
#
# $Id: Makefile,v 1.10 1998/03/25 09:21:01 ftplinux Exp $
#
# $Log: Makefile,v $
# Revision 1.10  1998/03/25 09:21:01  ftplinux
# Implemented snapshot target
#
# Revision 1.9  1998/03/23 14:10:28  ftplinux
# $$num in make upload needs braces because _ follows
#
# Revision 1.8  1997/12/16 13:20:57  ftplinux
# add _all to changes name in upload target
#
# Revision 1.7  1997/11/20 15:34:11  ftplinux
# upload target should copy only current release to queue dir
#
# Revision 1.6  1997/09/29 14:28:38  ftplinux
# Also fill in Version: for .changes file
#
# Revision 1.5  1997/09/25 11:33:48  ftplinux
# Added automatic adding of release number to ChangeLog
#
# Revision 1.4  1997/08/18 11:29:11  ftplinux
# Include new release number in message of cvs commits
#
# Revision 1.3  1997/08/12 10:39:08  ftplinux
# Added generation of .changes file in 'dist' target; added 'upload'
# target (using the queue :-)
#
# Revision 1.2  1997/08/12 10:01:32  ftplinux
# Fixed dist target to work (last checkin was needed to test it at all)
#
#

CVS = cvs
RELNUMFILE = release-num
# files that contain the release number
FILES_WITH_NUM = debianqueued dqueued-watcher
# name of cvs module
MODULE = debianqueued

.PHONY: default release dist

default:
	@echo "Nothing to make -- the Makefile is only for maintainance purposes"
	@exit 1

# Usage:
#   make release (use number from file release-num)
#  or
#   make release RELNUM=x.y (writes new number to release-num)

release:
	if cvs status $(RELNUMFILE) | grep -q Up-to-date; then true; else \
		echo "$(RELNUMFILE) needs commit first"; exit 1; \
	fi
ifdef RELNUM
	echo $(RELNUM) >$(RELNUMFILE)
	cvs commit -m "Bumped release number to `cat $(RELNUMFILE)`" $(RELNUMFILE)
endif
	perl -pi -e "s/Release: \S+/Release: `cat $(RELNUMFILE)`/;" \
		$(FILES_WITH_NUM)
	cvs commit -m "Bumped release number to `cat $(RELNUMFILE)`" $(FILES_WITH_NUM)
	if grep -q "Version `cat release-num` released" ChangeLog; then true; else \
		mv ChangeLog ChangeLog.orig; \
		echo "" >ChangeLog; \
		echo "-- Version `cat $(RELNUMFILE)` released" >>ChangeLog; \
		echo "" >>ChangeLog; \
		cat ChangeLog.orig >>ChangeLog; \
		rm ChangeLog.orig; \
		cvs commit -m "Bumped release number to `cat $(RELNUMFILE)`" ChangeLog; \
	fi
	cvs tag release-`cat $(RELNUMFILE) | sed 's/\./-/'`

dist:
	set -e; \
	num=`cat $(RELNUMFILE)`; name=debianqueued-$$num; \
	mkdir tmp; \
	(cd tmp; cvs export -r release-`echo $$num | sed 's/\./-/'` $(MODULE); \
	 mv $(MODULE) $$name; \
	 tar cvf ../../$$name.tar $$name); \
	gzip -9f ../$$name.tar; \
	rm -rf tmp; \
	file=../$$name.tar.gz; \
	md5=`md5sum $$file | awk -e '{print $$1}'`; \
	size=`ls -l $$file | awk -e '{print $$4}'`; \
	chfile=../debianqueued_`cat $(RELNUMFILE)`_all.changes; \
	sed -e "s/^Date: .*/Date: `822-date`/" -e "s/Version: .*/Version: `cat $(RELNUMFILE)`/" <changes-template >$$chfile; \
	echo " $$md5 $$size byhand - $$name.tar.gz" >>$$chfile; \
	pgp -u 'Roman Hodek' +clearsig=on -fast <$$chfile >$$chfile.asc; \
	mv $$chfile.asc $$chfile

# can only be used on ftp.uni-erlangen.de :-)
upload:
	set -e; \
	num=`cat $(RELNUMFILE)`; \
	cp ../debianqueued-$$num.tar.gz ../debianqueued_$${num}_all.changes $$HOME/Linux/debian/UploadQueue

# make snapshot from current sources
snapshot:
	set -e; \
	modified=`cvs status 2>/dev/null | awk '/Status:/ { if ($$4 != "Up-to-date") print $$2 }'`; \
	if [ "x$$modified" != "x" ]; then \
		echo "There are modified files: $$modified"; \
		echo "Commit first"; \
		exit 1; \
	fi; \
	name=debianqueued-snapshot-`date +%y%m%d`; \
	rm -rf tmp; \
	mkdir tmp; \
	(cd tmp; cvs export -D now $(MODULE); \
	 mv $(MODULE) $$name; \
	 tar cvf ../../$$name.tar $$name); \
	gzip -9f ../$$name.tar; \
	rm -rf tmp
