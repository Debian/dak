#!/usr/bin/make -f

SGMLMANPAGES	= catherine.1.sgml katie.1.sgml melanie.1.sgml natalie.1.sgml

MANPAGES	= $(patsubst %.sgml, %, $(SGMLMANPAGES))


all: $(MANPAGES)

%: %.sgml
	nsgmls $< | sgmlspl /usr/lib/perl5/sgmlspl-specs/docbook2man-spec.pl

clean:
	rm -f $(MANPAGES) manpage.lings manpage.log manpage.refs
