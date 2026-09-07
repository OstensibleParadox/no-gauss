#!/usr/bin/env python3
"""Inventory manuscript notation and enforce its load-bearing threshold.

The audit is intentionally lexical rather than a TeX parser.  It distinguishes
exported notation/terminology from proof-local binders, and it counts both
literal appearances in formal results and explicitly configured macro-expanded
carriers.  Run with ``--check`` for a read-only CI check.  With no option (or
with ``--write``), the current inventory is written to ``audit/``.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ROOT / "sections"
MAIN = SECTIONS / "main.tex"
EXPECTED_INPUTS = (
    "01-introduction-and-main-results",
    "02-rotational-fourier-defect-and-gaussian-characterization",
    "03-finite-dimensional-hellinger-coercivity",
    "04-measurable-realization-and-dichotomy",
    "05-finite-variance-equivalence-and-global-rigidity",
    "06-symmetric-stable-products-and-anisotropic-geometry",
    "07-zero-set-row-condition-and-linear-equivalence",
    "08-scope-of-the-finite-variance-hypotheses",
)

RESULT_RE = re.compile(
    r"\\begin\{(?P<env>theorem|lemma|proposition|corollary)\}"
    r"(?:\[[^]]*\])?.*?\\end\{(?P=env)\}",
    re.S,
)
EQUATION_RE = re.compile(
    r"\\begin\{(?P<env>equation\*?|align\*?|gather\*?|multline\*?)\}"
    r".*?\\end\{(?P=env)\}",
    re.S,
)
REF_RE = re.compile(r"\\(?:[eE]qref|[cC]ref|ref)\*?\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


@dataclass(frozen=True)
class InventoryItem:
    name: str
    kind: str
    scope: str
    pattern: str
    expansion: str
    sections: frozenset[int] | None = None
    math_only: bool = True
    flags: int = 0
    # A result containing a carrier contains this object after recursively
    # expanding the displayed definition named in ``expansion``.
    result_carriers: tuple[str, ...] = ()
    decision: str = "retain"
    notes: str = ""


def exported(
    name: str,
    pattern: str,
    expansion: str,
    *,
    carriers: tuple[str, ...] = (),
    sections: set[int] | None = None,
    kind: str = "notation",
    math_only: bool = True,
    flags: int = 0,
    notes: str = "",
) -> InventoryItem:
    return InventoryItem(
        name,
        kind,
        "exported",
        pattern,
        expansion,
        frozenset(sections) if sections else None,
        math_only,
        flags,
        carriers,
        "retain canonical name",
        notes,
    )


def local(
    name: str,
    pattern: str,
    expansion: str,
    *,
    sections: set[int] | None = None,
    notes: str = "",
) -> InventoryItem:
    return InventoryItem(
        name,
        "notation",
        "proof-local",
        pattern,
        expansion,
        frozenset(sections) if sections else None,
        True,
        0,
        (),
        "retain only as a scoped binder",
        notes,
    )


def removed(name: str, pattern: str, reason: str, *, flags: int = 0) -> InventoryItem:
    return InventoryItem(
        name,
        "removed",
        "removed",
        pattern,
        reason,
        None,
        False,
        flags,
        (),
        "zero occurrences required",
        "A match indicates that a superseded name has returned.",
    )


def phrase(
    name: str,
    expansion: str,
    *,
    carriers: tuple[str, ...] = (),
    exported_term: bool = True,
) -> InventoryItem:
    pattern = re.escape(name).replace(r"\ ", r"\s+")
    return InventoryItem(
        name,
        "terminology",
        "exported" if exported_term else "descriptive",
        pattern,
        expansion,
        None,
        False,
        re.I,
        carriers,
        "retain canonical phrase" if exported_term else "use as an ordinary description",
        "Whitespace-normalized, case-insensitive exact phrase count.",
    )


SINGLE = lambda token: rf"(?<![A-Za-z\\]){token}(?![A-Za-z_])"

# Only manuscript-interface objects belong here.  One-use abbreviations inside
# calculations belong in PROOF_LOCAL below, not in this list.  ``carriers``
# make the macro-expansion test explicit: for example, a theorem that uses
# mu_alpha also uses rho_alpha after expanding mu_alpha=rho_alpha^(tensor N).
EXPORTED: tuple[InventoryItem, ...] = (
    exported(r"\rho", r"\\rho(?![A-Za-z_^])", "common finite-variance coordinate law", carriers=(r"\\mu(?![A-Za-z_^])",)),
    exported(r"\mu", r"\\mu(?![A-Za-z_^])", "default product law rho^(tensor N), with explicit local rebinding in general-measure results"),
    exported(r"\mu_n", r"\\mu_[nmN](?![A-Za-z])", "finite coordinate product or finite marginal, as declared in scope"),
    exported(r"\phi", r"\\phi(?![A-Za-z_])", "characteristic function u -> E exp(iuX)"),
    exported("R", SINGLE("R"), "eta phi'(xi)phi(eta)-xi phi(xi)phi'(eta)"),
    exported(r"W_{\xi,\eta}", r"W_\{\\xi,\\eta\}", "product of the two centered complex exponentials"),
    exported("H", SINGLE("H"), "ell^2(N;R), the coefficient Hilbert space"),
    exported("s", r"(?<![A-Za-z\\])s(?=\s*(?:=|\())", "location score -f'/f=-2g'/g", carriers=(r"S_[AB](?![A-Za-z])",)),
    exported("d", r"(?<![A-Za-z\\])d(?=\s*(?:=|\())", "scale score x s(x)-1", carriers=(r"S_[AB](?![A-Za-z])",)),
    exported("J", r"(?<!\\mathcal )(?<![A-Za-z\\])J(?![A-Za-z_])", "location Fisher information E s(X)^2"),
    exported(r"\kappa", r"\\kappa(?![A-Za-z_])", "scale Fisher information E d(X)^2"),
    exported(r"\mathcal P", r"\\mathcal P(?![A-Za-z_^])", "signed coordinate permutations whose signs preserve rho"),
    exported(r"\Phi_T", r"\\Phi_T(?![A-Za-z_])", "measurable row-series realization of T", carriers=(r"\\nu_T(?![A-Za-z_])",)),
    exported(r"\nu_T", r"\\nu_T(?![A-Za-z_])", "(Phi_T)_# mu"),
    exported(r"\Aff", r"\\Aff(?![A-Za-z])", "Hellinger affinity"),
    exported("h", SINGLE("h"), "squared Hellinger distance h(lambda,nu)^2=2-2 Aff(lambda,nu)"),
    exported("P_n", r"(?<!\\mathcal )P_[nmN](?![A-Za-z])", "orthogonal projection in H onto an initial coordinate segment"),
    exported(r"\pi_n", r"\\pi_[nmN](?![A-Za-z])", "coordinate extraction from the product sample space", carriers=(r"E_[nmN](?![A-Za-z])",)),
    exported("E_n(T)", r"(?<![A-Za-z\\])E_[nmN](?![A-Za-z])", "projected Hellinger energy -2 log Aff(mu_n,(pi_n)_#nu_T)"),
    exported(r"\mathcal S_2", r"\\mathcal S_2", "Hilbert--Schmidt operator ideal"),
    exported("matrix score S_A", r"S_[AB](?![A-Za-z])", "matrix-path score sum"),
    exported(r"\mathcal I", r"\\mathcal I(?![A-Za-z])", "matrix Fisher operator defined by score covariance"),
    exported("U_A", r"U_(?:[AB]|\{(?:[AB]|\\exp))", "unitary half-density action induced by A"),
    exported(r"\Omega_n", r"\\Omega_[nmN](?![A-Za-z])", "product square-root density"),
    exported("G_A", r"G_[AB](?![A-Za-z])", "generator of the half-density action"),
    exported("finite Fourier functions", r"(?<![A-Za-z\\])[pqr](?![A-Za-z_])", "the three finite real Fourier sums with displayed dual moments", sections={3}),
    exported("H_A", r"H_[AB](?![A-Za-z])", "quadratic function built from the three finite Fourier sums", sections={3}),
    exported(r"\mathcal P_n", r"\\mathcal P_[nmN](?![A-Za-z^])", "finite-dimensional rho-admissible signed-permutation group"),
    exported("d_n", r"(?<![A-Za-z\\])d_[nmN](?![A-Za-z])", "Frobenius distance to the finite rho-admissible group"),
    exported(r"\ell_{T,n}", r"\\ell_\{T,[nmN]\}|\\ell_\{T_[nmN]\}", "finite-marginal likelihood ratio on the common product space"),
    exported(r"\ell_T", r"\\ell_T(?![A-Za-z_])", "Radon--Nikodym derivative d nu_T/d mu"),
    exported(r"\rho_\alpha", r"\\rho_\\alpha", "standard symmetric alpha-stable coordinate law", carriers=(r"\\mu_\\alpha(?![A-Za-z_])",)),
    exported(r"\mu_\alpha", r"\\mu_\\alpha(?![A-Za-z_])", "rho_alpha^(tensor N)"),
    exported(r"\mu_{\alpha,n}", r"\\mu_\{\\alpha,[nmN]\}", "finite product of the standard symmetric alpha-stable coordinate law"),
    exported(r"\Phi_{\alpha,T}", r"\\Phi_\{\\alpha,[A-Z]\}", "compatible stable row-series realization", carriers=(r"\\nu_\{\\alpha,[A-Z]\}",)),
    exported(r"\nu_{\alpha,T}", r"\\nu_\{\\alpha,[A-Z]\}(?![A-Za-z_])", "(Phi_{alpha,T})_#mu_alpha"),
    exported(r"F_\alpha", r"F_\\alpha(?![A-Za-z_])", "sum over columns of the alpha-th powers of their ell^2 norms; the mixing cost applies it to the off-diagonal part", carriers=(r"\\mathfrak e_\\alpha(?![A-Za-z_])",)),
    exported(r"\mathfrak e_\alpha", r"\\mathfrak e_\\alpha(?![A-Za-z_])", "diagonal square cost plus F_alpha of the off-diagonal part"),
    exported(r"E_{\alpha,n}", r"E_\{\\alpha,[nmN]\}", "projected Hellinger energy for the stable image law"),
    exported(r"\mathcal P^{\pm}", r"\\mathcal P\^\{\\pm\}", "full signed-permutation group"),
    exported(r"\mathcal P_n^{\pm}", r"\\mathcal P_[nmN]\^\{\\pm\}", "finite-dimensional full signed-permutation group", carriers=(r"\\mathfrak e_\{\\alpha,[nmN]\}",)),
    exported(r"\mathfrak e_{\alpha,n}", r"\\mathfrak e_\{\\alpha,[nmN]\}", "finite-dimensional stable mixing cost minimized over signed permutations"),
    exported(r"\mathcal G_\rho", r"\\mathcal G_\\rho", "linear equivalence group {T:nu_T is equivalent to mu}", sections={7}),
    exported(r"\mathcal U", r"\\mathcal U(?![A-Za-z])", "positivity set {x:f(x)>0}", sections={7}),
    exported(r"\rho^-", r"\\rho\^-", "law of -X", sections={7}),
    exported(r"\Tail_n", r"\\Tail_[nmN](?![A-Za-z])", "sum of forward and reverse finite-marginal ratio tails", sections={7}),
    exported("r_k", r"(?<![A-Za-z\\])r_k(?![A-Za-z])", "block affinity Aff(lambda_k,eta_k)", sections={7}),
    exported("a_k,b_k", r"[ab]_k", "the two common-support masses in the block criterion", sections={7}, notes="The broad scoped pattern also recognizes compact TeX products such as \\prod_ka_k and a_kb_k."),
)

TERMINOLOGY: tuple[InventoryItem, ...] = (
    phrase("rotational Fourier defect", "the scalar function R"),
    phrase("weighted Fourier jet", "the curve u -> (u phi(u),phi'(u))"),
    phrase("matrix Fisher operator", "the score-covariance operator mathcal I"),
    phrase("measurable row-series realization", "the Borel row-series map Phi_T"),
    phrase("projected Hellinger energy", "the finite-output quantity E_n or E_{alpha,n}"),
    phrase("finite-marginal likelihood ratios", "the martingale of marginal density ratios"),
    phrase("likelihood ratio", "a Radon--Nikodym derivative with its two measures specified"),
    phrase("Hellinger coercivity", "dimension-free comparison of Hellinger loss with matrix cost"),
    phrase("exact linear stabilizer", "operators preserving the product law exactly"),
    phrase("bounded invertible linear mixing", "T in GL(H) acting through its row-series realization"),
    phrase("centered with variance one", "E X=0 and E X^2=1"),
    phrase("a.e.-positive density", "f>0 Lebesgue-almost everywhere"),
    phrase("compatible stable row-series realization", "a measurable stable row action with a two-sided row-series inverse"),
    phrase("anisotropic mixing cost", "mathfrak e_alpha"),
    phrase("column cost", "F_alpha"),
    phrase("anisotropic stable Hellinger coercivity", "comparison with mathfrak e_{alpha,n}"),
    phrase("zero-set row condition", "forward and inverse rows avoid the density zero set almost surely"),
    phrase("linear equivalence group", "mathcal G_rho"),
)

PROOF_LOCAL: tuple[InventoryItem, ...] = (
    local("C_0,C_1", r"C_[01](?![A-Za-z])", "constants local to the displayed estimate"),
    local(r"C_\lambda", r"C_\\lambda", "second-moment domination constant for a locally fixed law", sections={4}),
    local(r"\Gamma", r"\\Gamma(?![A-Za-z_])", "countable operator group in the realization proof", sections={4}),
    local("L_a and its Borel representative", r"(?:\\widehat )?L_a", "row sum and selected Borel version", sections={4}),
    local("local cutoff/perturbation symbols", r"(?:r_0|\\Theta_u|\\mathcal M_u|N_\{\\mathrm\{open\}\})", "binders confined to their construction"),
)

REMOVED: tuple[InventoryItem, ...] = (
    removed(r"R_\mu", r"R_\\mu", "the coordinate law is fixed; use R"),
    removed(r"\Gamma_\mu", r"\\Gamma_\\mu", "the explicit weighted Fourier jet replaces this alias"),
    removed(r"\mathcal R_w", r"\\mathcal R_w", "display the one-off integral instead"),
    removed(r"\Sigma_f or \mathcal P_f", r"\\(?:Sigma|mathcal P)_f", "use the canonical rho-admissible group mathcal P"),
    removed(r"d_{n,f}", r"d_\{n,f\}", "the fixed-law suffix is redundant"),
    removed("Z_T", r"Z_T", "use the likelihood-ratio family ell_T"),
    removed(r"\Phi_T^{(\alpha)} or \nu_T^{(\alpha)}", r"\\(?:Phi|nu)_T\^\{\(\\alpha\)\}", "use alpha as the first subscript"),
    removed(r"\widehat\rho_\alpha", r"\\widehat\{?\\rho\}?_\\alpha", "display the characteristic function directly"),
    removed(r"\mathcal C_\alpha", r"\\mathcal C_\\alpha", "expand the stable column condition"),
    removed(r"\mathcal E_{\alpha,n}", r"\\mathcal E_\{?\\alpha,n\}?", "use mathfrak e_{alpha,n}"),
    removed("inverse-adjoint shorthand", r"(?:T|A)\^\{-(?:\\ast|\*)\}", "write ((T^{-1})^*) or ((A^{-1})^*)"),
    removed("left signed-permutation normalization", r"Q\^\{-1\}T", "use the paper's canonical right normalization TQ^{-1}"),
    removed("D_n(M) ratio-tail alias", r"D_n\(M\)", "use Tail_n(M), reserving D for diagonal objects"),
    removed("historical restricted names", r"(?i)restricted[-_:]", "use theorem-specific semantic names"),
    removed("proof-process terminology", r"(?i)(?:fractional column necessity|global signed-permutation match|rare-source (?:estimate|construction)|tail sign symmetry|sign-cut argument|uniform receiver)", "describe the mathematical step rather than naming proof chronology"),
)

INVENTORY = EXPORTED + TERMINOLOGY + PROOF_LOCAL + REMOVED

# Each exported manuscript interface item is assigned to the exact English
# phrase used for its Google Scholar collision check.  Several symbols may
# expand to the same standard phrase; that is intentional and makes the
# notation-to-search correspondence explicit rather than treating glyphs as
# searchable terminology.
SCHOLAR_QUERY_BY_ITEM: dict[str, str] = {
    r"\rho": "coordinate law",
    r"\mu": "product law",
    r"\mu_n": "product law",
    r"\phi": "characteristic function",
    "R": "rotational Fourier defect",
    r"W_{\xi,\eta}": "product of centered complex exponentials",
    "H": "Hilbert space",
    "s": "location score",
    "d": "scale score",
    "J": "location Fisher information",
    r"\kappa": "scale Fisher information",
    r"\mathcal P": "signed permutation",
    r"\Phi_T": "measurable row-series realization",
    r"\nu_T": "image law",
    r"\Aff": "Hellinger affinity",
    "h": "Hellinger distance",
    "P_n": "orthogonal projection",
    r"\pi_n": "coordinate projection",
    "E_n(T)": "projected Hellinger energy",
    r"\mathcal S_2": "Hilbert-Schmidt ideal",
    "matrix score S_A": "matrix score",
    r"\mathcal I": "matrix Fisher operator",
    "U_A": "unitary half-density action",
    r"\Omega_n": "product square-root density",
    "G_A": "half-density generator",
    "finite Fourier functions": "finite real Fourier sums",
    "H_A": "finite real Fourier sums",
    r"\mathcal P_n": "signed permutation",
    "d_n": "Frobenius distance",
    r"\ell_{T,n}": "finite-marginal likelihood ratio",
    r"\ell_T": "likelihood ratio",
    r"\rho_\alpha": "standard symmetric alpha-stable law",
    r"\mu_\alpha": "product law",
    r"\mu_{\alpha,n}": "standard symmetric alpha-stable law",
    r"\Phi_{\alpha,T}": "compatible stable row-series realization",
    r"\nu_{\alpha,T}": "image law",
    r"F_\alpha": "column cost",
    r"\mathfrak e_\alpha": "anisotropic mixing cost",
    r"E_{\alpha,n}": "projected Hellinger energy",
    r"\mathcal P^{\pm}": "signed permutation group",
    r"\mathcal P_n^{\pm}": "signed permutation group",
    r"\mathfrak e_{\alpha,n}": "anisotropic mixing cost",
    r"\mathcal G_\rho": "linear equivalence group",
    r"\mathcal U": "positivity set",
    r"\rho^-": "reflected law",
    r"\Tail_n": "finite-marginal ratio tails",
    "r_k": "Hellinger affinity",
    "a_k,b_k": "common-support mass",
    "rotational Fourier defect": "rotational Fourier defect",
    "weighted Fourier jet": "weighted Fourier jet",
    "matrix Fisher operator": "matrix Fisher operator",
    "measurable row-series realization": "measurable row-series realization",
    "projected Hellinger energy": "projected Hellinger energy",
    "finite-marginal likelihood ratios": "finite-marginal likelihood ratio",
    "likelihood ratio": "likelihood ratio",
    "Hellinger coercivity": "Hellinger coercivity",
    "exact linear stabilizer": "exact linear stabilizer",
    "bounded invertible linear mixing": "bounded invertible linear mixing",
    "centered with variance one": "centered with variance one",
    "a.e.-positive density": "a.e.-positive density",
    "compatible stable row-series realization": "compatible stable row-series realization",
    "anisotropic mixing cost": "anisotropic mixing cost",
    "column cost": "column cost",
    "anisotropic stable Hellinger coercivity": "anisotropic stable Hellinger coercivity",
    "zero-set row condition": "zero-set row condition",
    "linear equivalence group": "linear equivalence group",
}

ACCEPTED_COLLISION_STATUSES = {
    "no_exact_articles",
    "hits_standard_context",
    "hits_related_context",
    "hits_context_dependent",
    "hits_other_context",
}


def strip_comments(source: str) -> str:
    return re.sub(r"(?<!\\)%[^\n]*", lambda match: " " * len(match.group()), source)


def math_mask(source: str) -> str:
    """Blank non-math text while preserving offsets and line breaks."""
    keep = bytearray(len(source))
    patterns = (
        r"(?<!\\)\$\$.*?(?<!\\)\$\$",
        r"(?<!\\)\$(?!\$).*?(?<!\\)\$",
        r"\\\(.*?\\\)",
        r"\\\[.*?\\\]",
    )
    spans = [(m.start(), m.end()) for pattern in patterns for m in re.finditer(pattern, source, re.S)]
    spans.extend((match.start(), match.end()) for match in EQUATION_RE.finditer(source))
    for start, end in spans:
        keep[start:end] = b"\x01" * (end - start)
    return "".join(
        char if keep[index] or char == "\n" else " "
        for index, char in enumerate(source)
    )


def line_number(source: str, position: int) -> int:
    return source.count("\n", 0, position) + 1


def contained(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start >= left and end <= right for left, right in spans)


def load_sources() -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    entry = strip_comments(MAIN.read_text())
    inputs = re.findall(r"\\input\{([^}]+)\}", entry)
    if tuple(inputs) != EXPECTED_INPUTS:
        errors.append("main.tex does not contain the canonical eight-section input sequence")
    files = [SECTIONS / f"{name}.tex" for name in inputs]
    if len(files) != 8 or any(not path.exists() for path in files):
        errors.append("notation audit requires all eight included section files")

    data: list[dict] = []
    for index, path in enumerate(files, 1):
        if not path.exists():
            continue
        raw = path.read_bytes()
        source = strip_comments(raw.decode())
        data.append(
            {
                "index": index,
                "path": path,
                "source": source,
                "math": math_mask(source),
                "results": [(match.start(), match.end()) for match in RESULT_RE.finditer(source)],
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return data, errors


def referenced_equations(data: list[dict]) -> set[tuple[Path, int, int]]:
    equations: dict[str, tuple[Path, int, int]] = {}
    for datum in data:
        for match in EQUATION_RE.finditer(datum["source"]):
            for label in LABEL_RE.findall(match.group()):
                equations[label] = (datum["path"], match.start(), match.end())

    referenced: set[tuple[Path, int, int]] = set()
    for datum in data:
        for start, end in datum["results"]:
            for group in REF_RE.findall(datum["source"][start:end]):
                for label in group.split(","):
                    target = equations.get(label.strip())
                    if target:
                        referenced.add(target)
    return referenced


def count_pattern(
    item: InventoryItem,
    pattern: str,
    data: list[dict],
    referenced: set[tuple[Path, int, int]],
) -> tuple[list[str], list[str], list[str]]:
    matches: list[str] = []
    direct: list[str] = []
    via_equation: list[str] = []
    for datum in data:
        if item.sections and datum["index"] not in item.sections:
            continue
        searched = datum["math"] if item.math_only else datum["source"]
        for match in re.finditer(pattern, searched, item.flags):
            location = f"{datum['path'].relative_to(ROOT)}:{line_number(datum['source'], match.start())}"
            matches.append(location)
            if contained(match.start(), match.end(), datum["results"]):
                direct.append(location)
            elif any(
                path == datum["path"] and match.start() >= start and match.end() <= end
                for path, start, end in referenced
            ):
                via_equation.append(location)
    return matches, direct, via_equation


def audit(data: list[dict]) -> tuple[list[list[object]], list[str]]:
    referenced = referenced_equations(data)
    rows: list[list[object]] = []
    failures: list[str] = []

    for item in INVENTORY:
        matches, direct, via_equation = count_pattern(item, item.pattern, data, referenced)
        carrier_locations: list[str] = []
        for carrier in item.result_carriers:
            _, carrier_direct, carrier_equations = count_pattern(item, carrier, data, referenced)
            carrier_locations.extend(carrier_direct)
            carrier_locations.extend(carrier_equations)

        result_occurrences = list(dict.fromkeys(direct + via_equation + carrier_locations))
        if item.scope == "removed":
            status = "PASS: absent" if not matches else "FAIL: superseded name is present"
            if matches:
                failures.append(f"{item.name}: superseded name occurs at {matches[0]}")
        elif item.scope == "proof-local":
            status = "SCOPED: proof-local binder; exported threshold does not apply"
        elif item.scope == "descriptive":
            status = "SCOPED: ordinary descriptive phrase"
        elif len(matches) < 3:
            status = "FAIL: fewer than three lexical uses"
            failures.append(f"{item.name}: only {len(matches)} lexical use(s)")
        elif not result_occurrences:
            status = "FAIL: absent from formal results after configured expansion"
            failures.append(f"{item.name}: no formal-result occurrence after definition expansion")
        else:
            status = "PASS: load-bearing"

        allowed = "all" if item.sections is None else ",".join(f"{n:02}" for n in sorted(item.sections))
        rows.append(
            [
                item.name,
                item.kind,
                item.scope,
                item.pattern,
                len(matches),
                len(direct),
                len(via_equation),
                len(set(carrier_locations)),
                matches[0] if matches else "",
                item.expansion,
                status,
                item.decision,
                item.notes,
                "; ".join(dict.fromkeys(result_occurrences)),
                allowed,
            ]
        )
    return rows, failures


def render_review(data: list[dict], rows: list[list[object]], failures: list[str]) -> str:
    hashes = "\n".join(
        f"{datum['path'].relative_to(ROOT)}  {datum['sha256']}" for datum in data
    )
    sections = "\n".join(
        f"{datum['index']:02}. {datum['path'].stem[3:]}" for datum in data
    )
    failure_text = "\n".join(f"- {failure}" for failure in failures) or "- None."
    exported_count = sum(1 for row in rows if row[2] == "exported")
    local_count = sum(1 for row in rows if row[2] == "proof-local")
    removed_count = sum(1 for row in rows if row[2] == "removed")
    return f"""SOURCE AND NOTATION REVIEW: EIGHT-SECTION MANUSCRIPT

Scope
This deterministic snapshot covers the eight TeX files included by
sections/main.tex, in this order:
{sections}

Method
The companion TSV inventories {exported_count} exported notation or terminology
families, {local_count} representative proof-local binder families, and
{removed_count} superseded spellings.  Mathematical notation is counted only
inside TeX math delimiters and displayed math environments; terminology is
counted in uncommented source.  A location inside a theorem, proposition,
lemma, or corollary is a direct result occurrence.  A defining equation cited
from such a result is recorded separately.  The carrier column implements the
configured macro-expansion test: a result using a defined carrier counts only
when the inventory explicitly records that substitution.

An exported item passes only if it has at least three lexical uses and occurs in
a formal result directly, through a cited defining equation, or through an
explicitly configured definition carrier.  Proof-local binders are counted but
are not promoted to manuscript terminology and therefore do not face the
exported threshold.  A removed spelling must have zero occurrences.

Limitations
This is a lexical source audit, not a TeX parser or theorem prover.  It cannot
establish that an informal paraphrase is mathematically equivalent to a
definition, and it cannot discover every possible semantic collision.  The
``expansion`` and ``decision`` columns make the human-review commitments
inspectable.  Scholar collision results belong to the separate collision log;
this script neither performs nor claims those searches.

Current threshold failures
{failure_text}

Reproducibility
Run ``python3 scripts/audit_notation.py --check`` for a read-only check.  Run
``python3 scripts/audit_notation.py --write`` to regenerate
audit/notation-review.tsv and audit/source-review.txt.  Any source hash change
invalidates the prior snapshot.

Snapshot time (UTC)
{datetime.now(timezone.utc).isoformat()}

SHA-256 source fingerprints
{hashes}
"""


def write_outputs(rows: list[list[object]], review: str) -> None:
    output = ROOT / "audit"
    output.mkdir(exist_ok=True)
    with (output / "notation-review.tsv").open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "object_or_phrase",
                "kind",
                "scope",
                "python_regex",
                "total_lexical_occurrences",
                "direct_result_occurrences",
                "result_referenced_equation_occurrences",
                "macro_expansion_carrier_occurrences",
                "first_counted_occurrence",
                "definition_or_semantic_expansion",
                "burden_assessment",
                "decision",
                "limits_or_notes",
                "result_locations_after_expansion",
                "counted_sections",
            ]
        )
        writer.writerows(rows)
    (output / "source-review.txt").write_text(review)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="analyze without writing audit files")
    mode.add_argument("--write", action="store_true", help="regenerate audit files (default)")
    args = parser.parse_args()

    data, structural_errors = load_sources()
    if structural_errors:
        for error in structural_errors:
            print(f"ERROR: {error}")
        return 2

    rows, failures = audit(data)
    review = render_review(data, rows, failures)
    if not args.check:
        write_outputs(rows, review)
        print(f"Wrote {len(rows)} inventory rows for {len(data)} sections.")
    else:
        print(f"Checked {len(rows)} inventory rows for {len(data)} sections without writing files.")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        print(f"FAIL: {len(failures)} notation/terminology burden violation(s).")
        return 1
    print("PASS: every exported item meets the threshold and every superseded spelling is absent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
