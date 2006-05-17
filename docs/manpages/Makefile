#!/usr/bin/make -f

SGMLMANPAGES	= check-overrides.1.sgml clean-suites.1.sgml control-overrides.1.sgml control-suite.1.sgml import-users-from-passwd.1.sgml ls.1.sgml make-maintainers.1.sgml override.1.sgml poolize.1.sgml process-accepted.1.sgml process-new.1.sgml rm.1.sgml

MANPAGES	= $(patsubst %.sgml, dak_%, $(SGMLMANPAGES))


all: $(MANPAGES)

dak_%: %.sgml
	docbook2man $< > /dev/null

clean:
	rm -f $(MANPAGES) manpage.links manpage.log manpage.refs
