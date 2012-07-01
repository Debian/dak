export GNUPGHOME = $(CURDIR)/gpg
SHELL = /bin/bash

TAR = nonfree-package_0.1 package_0.1 package-built-using_0.1
PACKAGES = $(TAR) package_0.1-2 package_0.1-3

all: packages

tarballs: stamp-tarballs
stamp-tarballs:
	set -e; for t in $(TAR); do \
          if [ ! -f $$t.orig.tar.gz ]; then \
	    tar -czf $$t.orig.tar.gz --exclude=debian $${t/_/-}; \
	  fi; \
	done
	touch $@

packages: stamp-packages
stamp-packages: stamp-tarballs
	set -e; for p in $(PACKAGES); do \
	  (cd $${p/_/-}; dpkg-buildpackage); \
	done
	touch $@

clean:
	set -e; for p in $(PACKAGES); do \
	  make -C $${p/_/-} -f debian/rules clean; \
	done
	rm -f *.tar.gz *.dsc *.changes *.diff.gz *.deb
	rm -f gpg/*~
	rm -f stamp-*
