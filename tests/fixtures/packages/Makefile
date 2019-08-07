export GNUPGHOME = $(CURDIR)/gpg
SHELL = /bin/bash

# List of packages to build
# for each of these, the source must be available in a directory
# $PACKAGE_$VERSION
#
# if the directory doesn't exist, but there is a directory
# overlays/$PACKAGE and a directory overlays/$PACKAGE_$VERSION,
# the contents of both directories will be copied sequentially to
# $PACKAGE_$VERSION, allowing identical data for similar packages (eg.
# multiple versions of the same packages) to be stored only once
#
# the suffix (_F, _A, _B or _S) specifies the type of build

PACKAGES = \
linux_42.0_F \
nonfree-package_0.1_F \
package_0.1_F \
package_0.2_F \
package-built-using_0.1_F \
main-contrib-with-debug_0.1_F \
main-contrib-with-debug_0.2_F \

ALL = $(PACKAGES)

stamp-all: $(ALL)
	touch $@

%.orig.tar.gz:
	t=$*; \
	dir=$${t/_/-}; \
	base=$${t%_*}; \
	if [ ! -d $$dir ] ; then\
		cp -rv overlays/$$base/ ./$$dir/; \
		cp -Trv overlays/$$dir/ ./$$dir; \
	fi; \
	if [ ! -f $$t.orig.tar.gz ]; then \
		tar -czf $$t.orig.tar.gz --exclude=debian $${t/_/-}; \
	fi

%_F: %.orig.tar.gz
	p=$*; (cd $${p/_/-}; dpkg-buildpackage -F)

%_A: %.orig.tar.gz
	p=$*; (cd $${p/_/-}; dpkg-buildpackage -A)

%_B: %.orig.tar.gz
	p=$*; (cd $${p/_/-}; dpkg-buildpackage -B)

%_S: %.orig.tar.gz
	p=$*; (cd $${p/_/-}; dpkg-buildpackage -S)

clean:
	set -e; for j in $(ALL); do \
	  p=$${j%_*}; \
	  dir=$${p/_/-}; \
	  if [ -d overlays/$$dir ]; then rm -rf ./$$dir; \
	    else make -C $$dir -f debian/rules clean; fi; \
	done
	rm -f *.tar.gz *.tar.xz *.buildinfo *.dsc *.changes *.diff.gz *.deb
	rm -f gpg/*~
	rm -f stamp-*

.PRECIOUS: %.orig.tar.gz
