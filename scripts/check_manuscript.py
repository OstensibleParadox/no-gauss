#!/usr/bin/env python3
"""Static manuscript checks; never invokes TeX, bibliography tools, or rendering."""

from collections import Counter
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ROOT / "sections"
MAIN = SECTIONS / "main.tex"


def uncomment(text):
    return re.sub(r"(?<!\\)%[^\n]*", "", text)


def main():
    errors = []
    entry = uncomment(MAIN.read_text())
    inputs = re.findall(r"\\input\{([^}]+)\}", entry)
    paths = [SECTIONS / (name + ".tex") for name in inputs]
    if len(inputs) != len(set(inputs)):
        errors.append("Duplicate section input")
    if [name[:2] for name in inputs] != [f"{i:02}" for i in range(1, len(inputs) + 1)]:
        errors.append("Section filenames are not consecutively numbered in input order")
    expected = {MAIN, *paths}
    if set(SECTIONS.glob("*.tex")) != expected:
        errors.append("Unincluded or missing TeX source in sections/")
    texts = [(MAIN, entry)]
    for path in paths:
        if not path.exists():
            errors.append(f"Missing input: {path.name}")
            continue
        source = uncomment(path.read_text())
        titles = re.findall(r"\\section\{([^}]+)\}", source)
        if len(titles) != 1:
            errors.append(f"{path.name}: expected exactly one top-level section")
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", titles[0].lower()).strip("-")
            if path.stem[3:] != slug:
                errors.append(f"{path.name}: filename does not match section title")
            if not re.search(r"\\section\{[^}]+\}\s*\\label\{sec:" + re.escape(slug) + r"\}", source):
                errors.append(f"{path.name}: section label does not match title")
        texts.append((path, source))

    for path, source in texts:
        braces = []
        for match in re.finditer(r"(?<!\\)[{}]", source):
            if match[0] == "{":
                braces.append(match.start())
            elif braces:
                braces.pop()
            else:
                errors.append(f"{path.name}: unmatched closing brace")
        if braces:
            errors.append(f"{path.name}: {len(braces)} unmatched opening braces")
        stack = []
        for match in re.finditer(r"\\(begin|end)\{([^}]+)\}", source):
            kind, env = match.groups()
            if kind == "begin":
                stack.append(env)
            elif stack and stack[-1] == env:
                stack.pop()
            else:
                errors.append(f"{path.name}: mismatched environment {env}")
        if stack:
            errors.append(f"{path.name}: unclosed environments {stack}")
        delimiters = []
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
                errors.append(f"{path.name}: mismatched math delimiter {token}")
        if delimiters:
            errors.append(f"{path.name}: unclosed math delimiters {delimiters}")

    combined = "\n".join(source for _, source in texts)
    labels = Counter(re.findall(r"\\label\{([^}]+)\}", combined))
    references = [key.strip() for group in re.findall(r"\\(?:[cC]ref|[eE]qref|ref|pageref)\*?\{([^}]+)\}", combined) for key in group.split(",")]
    errors.extend(f"Duplicate label: {key}" for key, count in labels.items() if count > 1)
    errors.extend(f"Undefined reference: {key}" for key in sorted(set(references) - labels.keys()))
    bibliography = (SECTIONS / "references.bib").read_text()
    bib_keys = re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bibliography)
    citations = [key.strip() for group in re.findall(r"\\cite\w*\*?(?:\[[^\]]*\])*\{([^}]+)\}", combined) for key in group.split(",")]
    errors.extend(f"Undefined citation: {key}" for key in sorted(set(citations) - set(bib_keys)))
    errors.extend(f"Duplicate bibliography key: {key}" for key, count in Counter(bib_keys).items() if count > 1)
    for command in re.findall(r"\\(?:newcommand|DeclareMathOperator)\{\\([A-Za-z]+)\}", entry):
        if len(re.findall(r"\\" + command + r"(?![A-Za-z])", combined)) < 2:
            errors.append(f"Unused custom macro: {command}")
    forbidden = {
        "draft label prefix": r"\\(?:label|[cC]ref|eqref)\{[^}]*:(?:ng-|intro-)|\\label\{[^}]*(?:candidate|endpoint|closure)",
        "old section filename": r"\\input\{section[1-6]\}",
        "old Fourier alias": r"R_\\mu|\\Gamma_\\mu|\\mathcal R_w|Fourier curvature|weighted-jet|weighted Fourier-jet",
        "old group alias": r"\\Sigma_f|\\mathcal P_f|d_\{[^}]*,f\}",
        "old likelihood term": r"(?i)projected likelihood|likelihood closure|finite-corner",
        "unnormalized adjoint": r"\^\{\\mathsf T\}|\^\\top|\^\{\\top\}",
        "unnormalized standard macro": r"\\mathbb\s*[{]?[REN][}]?|\\operatorname\{(?:Law|diag|tr)\}|\\mathrm\{GL\}",
    }
    # Standard macro definitions themselves intentionally contain their expansions.
    body = "\n".join(source for _, source in texts[1:])
    for description, pattern in forbidden.items():
        if re.search(pattern, body):
            errors.append(f"Residual {description}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"PASS: {len(paths)} consecutive sections; {len(labels)} unique labels; "
          f"{len(references)} resolved references; {len(set(citations))} resolved citation keys.")
    print("PASS: input coverage, title/file/label agreement, braces, environments, math delimiters, custom macros, and canonical spellings.")
    print("Static source checks only; no compilation, PDF rendering, or proof verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
