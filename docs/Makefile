#!/usr/bin/make -f

# TODO: alyson andrea charisma claire fernanda jenna neve rene rhona shania tea ziyi

SGMLMANPAGES	= catherine.1.sgml heidi.1.sgml julia.1.sgml katie.1.sgml madison.1.sgml melanie.1.sgml natalie.1.sgml

MANPAGES	= $(patsubst %.sgml, %, $(SGMLMANPAGES))


all: $(MANPAGES)

%: %.sgml
	nsgmls $< | sgmlspl /usr/lib/perl5/sgmlspl-specs/docbook2man-spec.pl

clean:
	rm -f $(MANPAGES) manpage.lings manpage.log manpage.refs
