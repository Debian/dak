# $Id: $

LATEX = latex
PDFLATEX = pdflatex
DVIPS = dvips
BIBTEX = bibtex
PDFVIEW = xpdf -fullscreen

SRC := $(shell egrep -l '^[^%]*\\begin\{document\}' *.tex)
DVI = $(SRC:%.tex=%.dvi)
PDF = $(SRC:%.tex=%.pdf)
PS  = $(SRC:%.tex=%.ps)

all: pdf

$(PDF): %.pdf : %.tex
	# call two time because of toc etc
	@$(PDFLATEX) $<
	@$(PDFLATEX) $<
	@$(PDFLATEX) $<

show:
	$(PDFVIEW) $(PDF)

pdf: $(PDF)

clean:
	-rm -f $(DVI) $(PDF) $(DVI:%.dvi=%.aux) $(DVI:%.dvi=%.log) $(DVI:%.dvi=%.out) $(DVI:%.dvi=%.toc) $(DVI:%.dvi=%.nav) $(DVI:%.dvi=%.snm)
