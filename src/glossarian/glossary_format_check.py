#!/usr/bin/env python3
"""Validate a glossary's structure for deterministic parseability.

Applies the canonical-structure rules to the structural model produced by
`glossarian.model`: YAML front matter (`id: glossary`), a single top-level `# Glossary`
heading, the four required `##` sections in canonical order, and the definition-entry
shape under `## Definitions` — a **clean, term-only** `###` heading (rule 5b), an optional
typed ```glossary``` field block (rule 5c), and a free markdown body that may span
paragraphs, tables, and fenced code (rule 5), with no duplicate term-heading slugs. The
check drives the glossary-anchor repair and ships as a durable guard so the file stays
parseable by the same `glossarian.model` Sedric's glossary tool consumes.

Read-only. Reports violations to stdout and sets an exit code:
  0 = valid · 1 = read OK but rule violations · 2 = path missing / unreadable.

Built against contract v5 (v4 entry grammar + `-h`/`--help` usage, behavior 8).
Companion contract: contracts/glossary_format_check_contract.md
Tests:              tests/test_glossary_format_check.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from glossarian import model
from glossarian.model import GlossaryModel, StrayBlock, TermBlock

DEFAULT_GLOSSARY = "docs/glossary.md"

USAGE = """\
Usage: glossarian-check [GLOSSARY_PATH] [--quiet]
       glossarian-check -h | --help

Validate a markdown glossary's structure (front matter, H1, required sections, definition
entries). GLOSSARY_PATH defaults to docs/glossary.md. Read-only.

Options:
  --quiet       print nothing; rely on the exit code
  -h, --help    show this help and exit 0

Exit codes: 0 valid, 1 rule violations, 2 path missing/unreadable."""

# Required `##` sections, in canonical order (contract rule 4). Matched case-sensitively.
REQUIRED_SECTIONS: list[str] = [
    "Governance",
    "Definitions",
    "Confusable Pairs",
    "Renames and deprecated terms",
]

TERM_HEADING_LEVEL = 3  # `###` term headings under `## Definitions` (contract rule 5)

# Decorations that pollute a heading's github_slug and break inbound links (rule 5b).
# Parenthetical qualifiers, inline aliases, co-defined slashes, bold markers, and the
# `requirements→items` arrow all moved out of the heading into the field block / body.
DISALLOWED_HEADING_CHARS = "()*/:→"  # ( ) * / : →

# The typed field-block keys a term entry may declare (rule 5c).
ALLOWED_FIELD_KEYS: frozenset[str] = frozenset({"aliases", "short", "confusable", "reserved-for", "see"})
ALLOWED_RESERVED_FOR: frozenset[str] = frozenset({"lacey", "auditable-script"})


@dataclass
class Violation:
    line: int | None  # None when the rule is not tied to a specific line
    msg: str


# --------------------------------------------------------------------------- #
# Rules (each applied to the structural model)                                 #
# --------------------------------------------------------------------------- #


def check_frontmatter(m: GlossaryModel) -> tuple[list[Violation], list[str]]:
    """Rule 2. Returns (violations, warnings)."""
    if m.frontmatter_error is not None:
        return [Violation(1, m.frontmatter_error)], []
    data = m.frontmatter
    violations: list[Violation] = []
    warnings: list[str] = []
    if data.get("id") != "glossary":
        violations.append(Violation(1, f"front matter must declare `id: glossary` (found id={data.get('id')!r})"))
    if data.get("is_source_of_truth", "").lower() != "true":
        warnings.append("front matter recommendation: set `is_source_of_truth: true`")
    return violations, warnings


def check_h1(m: GlossaryModel) -> list[Violation]:
    """Rule 3: exactly one `# Glossary` H1."""
    h1 = m.headings(1)
    if len(h1) == 0:
        return [Violation(None, "missing top-level `# Glossary` heading")]
    if len(h1) > 1:
        return [
            Violation(h1[1].no, f"more than one top-level heading (found {len(h1)}; expected exactly one `# Glossary`)")
        ]
    if h1[0].htext != "Glossary":
        return [Violation(h1[0].no, f"top-level heading must be `# Glossary` (found `# {h1[0].htext}`)")]
    return []


def check_sections(m: GlossaryModel) -> list[Violation]:
    """Rule 4: required `##` sections present, verbatim, exactly once, in canonical order."""
    level2 = m.headings(2)
    violations: list[Violation] = []
    for name in REQUIRED_SECTIONS:
        occurrences = [ln for ln in level2 if ln.htext == name]
        if not occurrences:
            violations.append(Violation(None, f"missing required section `## {name}`"))
        elif len(occurrences) > 1:
            # A repeated required section makes the layout ambiguous — e.g. a second
            # `## Definitions` would shadow the first for the glossary parser.
            violations.append(
                Violation(
                    occurrences[1].no,
                    f"duplicate required section `## {name}` (also at line {occurrences[0].no})",
                )
            )
    # Order check over the required sections that ARE present (extras are ignored).
    present = [(REQUIRED_SECTIONS.index(ln.htext), ln) for ln in level2 if ln.htext in REQUIRED_SECTIONS]
    order = [idx for idx, _ in present]
    if order != sorted(order):
        # Identify the first heading that is out of order for a precise line number.
        bad_line = None
        max_seen = -1
        for idx, ln in present:
            if idx < max_seen:
                bad_line = ln.no
                break
            max_seen = max(max_seen, idx)
        violations.append(
            Violation(
                bad_line,
                "malformed section order: required sections must appear as "
                + " → ".join(f"## {n}" for n in REQUIRED_SECTIONS),
            )
        )
    return violations


def check_definitions(m: GlossaryModel) -> tuple[list[Violation], int]:
    """Rules 5, 5b, 5c & 6: definition-entry shape, clean headings, the field block, and
    duplicate-slug detection.

    Returns (violations, entry_count). Absence of the section is reported by
    check_sections; here there is nothing to shape-check.
    """
    if m.definitions_heading_line is None:
        return [], 0

    violations: list[Violation] = []
    slugs: dict[str, int] = {}
    entry_count = 0
    # Rule 5c `see`-resolution needs every term slug up front (a `see` may point forward).
    all_slugs = {b.slug for b in m.definition_blocks if isinstance(b, TermBlock)}

    for b in m.definition_blocks:
        if isinstance(b, StrayBlock):
            kind = "bold-paragraph entry" if b.kind == "bold" else "orphan text"
            if b.before_any_heading:
                violations.append(
                    Violation(
                        b.line,
                        f"definition body before any `###` term heading ({kind}); term entries must be `###` headings",
                    )
                )
            else:
                violations.append(Violation(b.line, f"unexpected {kind} where a `###` term heading was expected"))
            continue

        # TermBlock — rule 5 (shape)
        entry_count += 1
        if b.level != TERM_HEADING_LEVEL:
            violations.append(Violation(b.heading_line, f"term heading must be level `###` (found `{'#' * b.level}`)"))
        if b.slug in slugs:
            violations.append(
                Violation(
                    b.heading_line,
                    f"duplicate term-heading slug '{b.slug}' (first defined at line {slugs[b.slug]})",
                )
            )
        else:
            slugs[b.slug] = b.heading_line
        if b.body_line_count == 0:
            violations.append(Violation(b.heading_line, f"term `{b.term}` has an empty definition body"))
        if b.followed_by_heading_without_blank:
            violations.append(
                Violation(
                    b.next_heading_line,
                    "missing blank line before this term heading (definition block not terminated by a blank line)",
                )
            )

        # Rule 5b — the heading must be the canonical term only (clean slug).
        bad = sorted({c for c in b.term if c in DISALLOWED_HEADING_CHARS})
        if bad:
            violations.append(
                Violation(
                    b.heading_line,
                    f"term heading must contain only the canonical term (found {''.join(bad)!r}); "
                    "move qualifiers/aliases into the ```glossary``` field block or the body",
                )
            )

        # Rule 5c — the typed field block.
        if b.field_block_present:
            if b.field_block_unterminated:
                violations.append(
                    Violation(
                        b.field_block_line,
                        f"unterminated ```glossary``` field block in term `{b.term}` "
                        "(no closing fence before the section ends)",
                    )
                )
            for key in b.fields:
                if key not in ALLOWED_FIELD_KEYS:
                    violations.append(
                        Violation(
                            b.field_block_line,
                            f"unknown field-block key `{key}` in term `{b.term}` "
                            f"(allowed: {', '.join(sorted(ALLOWED_FIELD_KEYS))})",
                        )
                    )
            reserved = b.fields.get("reserved-for")
            if reserved is not None and reserved not in ALLOWED_RESERVED_FOR:
                violations.append(
                    Violation(
                        b.field_block_line,
                        f"`reserved-for` must be one of {', '.join(sorted(ALLOWED_RESERVED_FOR))} "
                        f"(found {reserved!r}) in term `{b.term}`",
                    )
                )
            see = b.fields.get("see")
            if see is not None and see not in all_slugs:
                violations.append(
                    Violation(
                        b.field_block_line,
                        f"`see: {see}` in term `{b.term}` does not resolve to another term's slug",
                    )
                )

    if entry_count == 0:
        violations.append(Violation(m.definitions_heading_line, "`## Definitions` contains no definition entries"))
    return violations, entry_count


# --------------------------------------------------------------------------- #
# Driver                                                                       #
# --------------------------------------------------------------------------- #


def validate(text: str) -> tuple[list[Violation], list[str], int]:
    """Run every rule over the glossary text. Returns (violations, warnings, entry_count)."""
    m = model.parse(text)
    violations: list[Violation] = []
    warnings: list[str] = []

    fm_v, fm_w = check_frontmatter(m)
    violations += fm_v
    warnings += fm_w
    violations += check_h1(m)
    violations += check_sections(m)
    def_v, entry_count = check_definitions(m)
    violations += def_v

    violations.sort(key=lambda v: (v.line is None, v.line or 0))
    return violations, warnings, entry_count


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    quiet = "--quiet" in argv
    positional = [a for a in argv if not a.startswith("--")]
    path = Path(positional[0]) if positional else Path(DEFAULT_GLOSSARY)

    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    violations, warnings, entry_count = validate(text)

    if not quiet:
        for w in warnings:
            print(f"{path}: warning: {w}")
        for v in violations:
            loc = f"{path}:{v.line}" if v.line is not None else f"{path}"
            print(f"{loc}: {v.msg}")
        if not violations:
            print(f"OK: {path} — {entry_count} definition entr{'y' if entry_count == 1 else 'ies'}")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
