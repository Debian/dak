#!/usr/bin/make -f

# TODO: alyson andrea claire fernanda jenna neve rene shania tea ziyi

SGMLMANPAGES	= catherine.1.sgml charisma.1.sgml cindy.1.sgml heidi.1.sgml julia.1.sgml kelly.1.sgml lisa.1.sgml madison.1.sgml melanie.1.sgml natalie.1.sgml rhona.1.sgml alicia.1.sgml

MANPAGES	= $(patsubst %.sgml, %, $(SGMLMANPAGES))


all: $(MANPAGES)

%: %.sgml
	docbook2man $< > /dev/null

clean:
	rm -f $(MANPAGES) manpage.lings manpage.log manpage.refs
