export GNUPGHOME = $(CURDIR)/gpg
SHELL = /bin/bash

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
	  make -C $$dir -f debian/rules clean; \
	done
	rm -f *.tar.gz *.tar.xz *.buildinfo *.dsc *.changes *.diff.gz *.deb
	rm -f gpg/*~
	rm -f stamp-*

.PRECIOUS: %.orig.tar.gz
