# Single entry point for the no-gauss paper.
# Compiles sections/main.tex with latexmk; aux/PDF go to build/, the
# finished PDF is moved to the project root as main.pdf.
MAIN := main
PAPER_DIR := sections
PDF := $(MAIN).pdf
BUILD_DIR := $(CURDIR)/build

SOURCES := $(wildcard $(PAPER_DIR)/*.tex) $(PAPER_DIR)/references.bib

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
