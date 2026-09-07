# Single entry point for the no-gauss paper.
# Compiles sections/main.tex with latexmk; aux/PDF go to build/, the
# finished PDF is moved to the project root as main.pdf.
MAIN := main
PAPER_DIR := sections
PDF := $(MAIN).pdf
BUILD_DIR := $(CURDIR)/build

SECTION_SOURCES := $(addprefix $(PAPER_DIR)/,\
	section1.tex section2.tex section3.tex section4.tex section5.tex)
SOURCES := $(PAPER_DIR)/$(MAIN).tex $(SECTION_SOURCES) \
	$(PAPER_DIR)/references.bib

LATEXMK ?= latexmk
LATEXMK_FLAGS := -pdf -interaction=nonstopmode -halt-on-error \
	-file-line-error -outdir="$(BUILD_DIR)"

.PHONY: all clean

all: $(PDF)

$(PDF): $(SOURCES)
	@mkdir -p "$(BUILD_DIR)"
	cd "$(PAPER_DIR)" && $(LATEXMK) $(LATEXMK_FLAGS) "$(MAIN).tex"
	mv -f "$(BUILD_DIR)/$(PDF)" "$(PDF)"

clean:
	rm -rf "$(BUILD_DIR)"
	rm -f "$(PDF)"
