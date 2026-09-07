#!/usr/bin/env python3
"""Run fast, deterministic source checks without invoking TeX.

The script checks the manuscript's public interface: the eight included
section files, headings and labels, cross-references, canonical notation
spellings, and globally declared notation macros.  Proof-local dummy
variables are outside the notation-burden check; ``audit_notation.py``
records that distinction in more detail.
"""

from collections import Counter
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

RESULT_PREFIX = {
    "theorem": "thm",
    "proposition": "prop",
    "lemma": "lem",
    "corollary": "cor",
}
RESULT_RE = re.compile(
    r"\\begin\{(?P<env>theorem|proposition|lemma|corollary)\}"
    r"(?:\[[^]]*\])?(?P<body>.*?)\\end\{(?P=env)\}",
    re.S,
)
REF_RE = re.compile(
    r"\\(?P<command>[cC]ref|[eE]qref|ref|pageref)\*?"
    r"(?:\[[^]]*\])?\{(?P<keys>[^}]*)\}"
)

# A stale spelling here means that a superseded interface has leaked back
# into the paper.  Patterns are applied only to live, uncommented TeX.
FORBIDDEN = {
    "historical restricted label/name": r"(?i)(?:restricted[-_:]|\\(?:label|[cC]ref|[eE]qref)\{[^}]*restricted)",
    "historical draft label": r"\\(?:label|[cC]ref|[eE]qref)\{[^}]*(?::(?:ng-|intro-)|(?:candidate|endpoint|closure))",
    "superseded section filename": (
        r"(?:05-proof-of-the-measure-equivalence-theorem|"
        r"06-density-zeros-and-the-linear-equivalence-group|"
        r"07-scope-and-sharpness-of-the-hypotheses|"
        r"07-support-compatibility-and-linear-equivalence)"
    ),
    "superseded section title": (
        r"\\section\{(?:Proof of the Measure Equivalence Theorem|"
        r"Density Zeros and the Linear Equivalence Group|"
        r"Scope and Sharpness of the Hypotheses|"
        r"Support Compatibility and Linear Equivalence)\}"
    ),
    "old Fourier notation": (
        r"R_\\mu|\\Gamma_\\mu|\\mathcal R_w|G_\{\\xi,\\eta\}|"
        r"Fourier curvature|weighted-jet|weighted Fourier-jet"
    ),
    "old finite-variance notation": (
        r"\\Sigma_f|\\mathcal P_f|d_\{n,f\}|Z_T|"
        r"(?i:projected likelihood|likelihood closure|finite-corner)"
    ),
    "old stable-law notation": (
        r"\\(?:Phi|nu)_T\^\{\(\\alpha\)\}|"
        r"\\widehat\{?\\rho\}?_\\alpha|"
        r"\\mathcal C_\\alpha|\\mathcal E_\{?\\alpha,n\}?|"
        r"(?:T|A)\^\{-(?:\\ast|\*)\}|Q\^\{-1\}T|D_n\(M\)"
    ),
    "noncanonical adjoint": r"\^\{\\mathsf T\}|\^\\top|\^\{\\top\}",
    "unexpanded standard notation": (
        r"\\mathbb\s*\{?[REN]\}?|"
        r"\\operatorname\{(?:Law|diag|Tail)\}|"
        r"\\mathrm\{GL\}"
    ),
}

# These are formatting conveniences rather than exported mathematical
# objects.  They must still be used at least three times, but do not need to
# occur in a formal result statement.  Every other global notation macro is
# required to be load-bearing in a theorem/lemma/proposition/corollary.
STANDARD_MACRO_EXEMPTIONS = {"R", "N", "E", "Law", "GL"}


def uncomment(text: str) -> str:
    """Remove comments while preserving newlines for useful diagnostics."""
    return re.sub(r"(?<!\\)%[^\n]*", lambda match: " " * len(match.group()), text)


def line_number(source: str, position: int) -> int:
    return source.count("\n", 0, position) + 1


def title_slug(title: str) -> str:
    """Return the filename/label slug used by top-level section headings."""
    plain = re.sub(r"\\[A-Za-z]+\*?", "", title)
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def check_balancing(path: Path, source: str, errors: list[str]) -> None:
    braces: list[int] = []
    for match in re.finditer(r"(?<!\\)[{}]", source):
        if match[0] == "{":
            braces.append(match.start())
        elif braces:
            braces.pop()
        else:
            errors.append(
                f"{path.name}:{line_number(source, match.start())}: unmatched closing brace"
            )
    if braces:
        errors.append(f"{path.name}: {len(braces)} unmatched opening brace(s)")

    stack: list[tuple[str, int]] = []
    for match in re.finditer(r"\\(begin|end)\{([^}]+)\}", source):
        kind, environment = match.groups()
        if kind == "begin":
            stack.append((environment, match.start()))
        elif stack and stack[-1][0] == environment:
            stack.pop()
        else:
            errors.append(
                f"{path.name}:{line_number(source, match.start())}: "
                f"mismatched environment {environment}"
            )
    if stack:
        names = [name for name, _ in stack]
        errors.append(f"{path.name}: unclosed environments {names}")

    delimiters: list[str] = []
    for match in re.finditer(r"(?<!\\)\\[()\[\]]|(?<!\\)\$", source):
        token = match[0]
        if token in (r"\(", r"\["):
            delimiters.append(token)
        elif token == "$":
            if delimiters and delimiters[-1] == "$":
                delimiters.pop()
            else:
                delimiters.append(token)
        elif delimiters and delimiters[-1] == {r"\)": r"\(", r"\]": r"\["}[token]:
            delimiters.pop()
        else:
            errors.append(
                f"{path.name}:{line_number(source, match.start())}: "
                f"mismatched math delimiter {token}"
            )
    if delimiters:
        errors.append(f"{path.name}: unclosed math delimiters {delimiters}")


def main() -> int:
    errors: list[str] = []
    entry = uncomment(MAIN.read_text())
    inputs = re.findall(r"\\input\{([^}]+)\}", entry)

    if tuple(inputs) != EXPECTED_INPUTS:
        errors.append(
            "Section inputs do not match the canonical eight-file sequence:\n  "
            + "\n  ".join(EXPECTED_INPUTS)
        )
    if len(inputs) != len(set(inputs)):
        errors.append("Duplicate section input")
    numbers = [name.split("-", 1)[0] for name in inputs]
    if numbers != [f"{number:02}" for number in range(1, len(inputs) + 1)]:
        errors.append("Section filenames are not consecutively numbered in input order")

    paths = [SECTIONS / f"{name}.tex" for name in inputs]
    expected_tex = {MAIN, *paths}
    actual_tex = set(SECTIONS.glob("*.tex"))
    if actual_tex != expected_tex:
        missing = sorted(path.name for path in expected_tex - actual_tex)
        extra = sorted(path.name for path in actual_tex - expected_tex)
        if missing:
            errors.append("Missing TeX source(s): " + ", ".join(missing))
        if extra:
            errors.append("Unincluded TeX source(s): " + ", ".join(extra))

    texts: list[tuple[Path, str]] = [(MAIN, entry)]
    for path in paths:
        if not path.exists():
            continue
        source = uncomment(path.read_text())
        titles = list(re.finditer(r"\\section\{([^}]+)\}", source))
        if len(titles) != 1:
            errors.append(f"{path.name}: expected exactly one top-level section")
        else:
            title_match = titles[0]
            slug = title_slug(title_match.group(1))
            if path.stem[3:] != slug:
                errors.append(
                    f"{path.name}:{line_number(source, title_match.start())}: "
                    f"filename does not match section title (expected {path.stem[:3]}{slug}.tex)"
                )
            following = source[title_match.end() :]
            next_nonspace = re.match(r"\s*\\label\{([^}]+)\}", following)
            expected_label = f"sec:{slug}"
            if not next_nonspace or next_nonspace.group(1) != expected_label:
                errors.append(
                    f"{path.name}: top-level section label must be {expected_label}"
                )
        check_balancing(path, source, errors)
        texts.append((path, source))

    check_balancing(MAIN, entry, errors)
    combined = "\n".join(source for _, source in texts)
    body = "\n".join(source for _, source in texts[1:])

    label_matches = list(re.finditer(r"\\label\{([^}]*)\}", combined))
    for match in label_matches:
        if match.group(1) != match.group(1).strip():
            errors.append(f"Whitespace inside \\label{{{match.group(1)}}}")
    label_counts = Counter(match.group(1).strip() for match in label_matches)
    for key, count in sorted(label_counts.items()):
        if not key:
            errors.append("Empty label")
        elif count > 1:
            errors.append(f"Duplicate label: {key}")
        if re.search(r"\s|,", key):
            errors.append(f"Noncanonical label key: {key!r}")
        if ":" not in key or key.split(":", 1)[0] not in {
            "sec", "eq", "thm", "prop", "lem", "cor", "fig", "tab", "app"
        }:
            errors.append(f"Unknown label prefix: {key}")

    reference_keys: list[str] = []
    for match in REF_RE.finditer(combined):
        command = match.group("command")
        raw_keys = match.group("keys").split(",")
        keys = [key.strip() for key in raw_keys]
        if any(raw != stripped for raw, stripped in zip(raw_keys, keys)):
            errors.append(
                f"Whitespace inside \\{command}{{{match.group('keys')}}}; "
                "reference keys must be comma-separated with no surrounding whitespace"
            )
        if any(not key for key in keys):
            errors.append(f"Empty target in \\{command} at combined line {line_number(combined, match.start())}")
            continue
        if len(keys) != len(set(keys)):
            errors.append(
                f"Duplicate target within \\{command}{{{match.group('keys')}}}"
            )
        if command.lower() == "eqref" and len(keys) != 1:
            errors.append(
                f"Multi-label \\{command}{{{match.group('keys')}}}; use \\cref for multiple equations"
            )
        reference_keys.extend(keys)

    undefined = sorted(set(reference_keys) - set(label_counts))
    errors.extend(f"Undefined reference: {key}" for key in undefined)

    # Formal results carry one label of the matching semantic kind.  Equation
    # labels nested in the statement are allowed and ignored here.
    for path, source in texts[1:]:
        for match in RESULT_RE.finditer(source):
            env = match.group("env")
            prefix = RESULT_PREFIX[env]
            result_labels = re.findall(rf"\\label\{{{prefix}:[^}}]+\}}", match.group())
            if len(result_labels) != 1:
                errors.append(
                    f"{path.name}:{line_number(source, match.start())}: {env} must contain "
                    f"exactly one {prefix}: label (found {len(result_labels)})"
                )

    bibliography_path = SECTIONS / "references.bib"
    bibliography = bibliography_path.read_text()
    bib_keys = re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bibliography)
    citations = [
        key.strip()
        for group in re.findall(r"\\cite\w*\*?(?:\[[^]]*\])*\{([^}]+)\}", combined)
        for key in group.split(",")
    ]
    errors.extend(f"Undefined citation: {key}" for key in sorted(set(citations) - set(bib_keys)))
    errors.extend(
        f"Duplicate bibliography key: {key}"
        for key, count in Counter(bib_keys).items()
        if count > 1
    )

    result_text = "\n".join(match.group() for match in RESULT_RE.finditer(body))
    macro_names = re.findall(
        r"\\(?:newcommand|DeclareMathOperator)\{\\([A-Za-z]+)\}", entry
    )
    for command in macro_names:
        pattern = rf"\\{command}(?![A-Za-z])"
        uses = len(re.findall(pattern, body))
        result_uses = len(re.findall(pattern, result_text))
        if uses < 3:
            errors.append(
                f"Low-burden global macro: \\{command} has {uses} substantive use(s); "
                "inline it or make it load-bearing"
            )
        elif command not in STANDARD_MACRO_EXEMPTIONS and result_uses == 0:
            errors.append(
                f"Non-load-bearing global notation: \\{command} never occurs in a formal result"
            )

    for description, pattern in FORBIDDEN.items():
        # Macro declarations necessarily spell out the standard expansions;
        # only manuscript bodies are required to use the canonical wrappers.
        searched = body if description == "unexpanded standard notation" else combined
        match = re.search(pattern, searched)
        if match:
            errors.append(
                f"Residual {description} at scanned line {line_number(searched, match.start())}: "
                f"{match.group()!r}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"FAIL: {len(errors)} static source error(s).")
        return 1

    print(
        f"PASS: {len(paths)} canonical consecutive sections; {len(label_counts)} unique labels; "
        f"{len(reference_keys)} resolved references; {len(set(citations))} resolved citation keys."
    )
    print(
        "PASS: input/title/file/label continuity, result-label kinds, multi-reference syntax, "
        "balancing, canonical spellings, and global-notation burden."
    )
    print("Static source checks only; no compilation, PDF rendering, or proof verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
