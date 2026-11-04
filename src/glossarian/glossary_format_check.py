#!/usr/bin/env python3
"""Validate a glossary's structure for deterministic parseability.

Applies the canonical-structure rules to the structural model produced by
`glossarian.model`: YAML front matter (`id: glossary`), a single top-level `# Glossary`
heading, the five required `##` sections in canonical order, a `## Governance` field block
declaring the directory the glossary governs (`governs:`, rule 4b), and the definition-entry
shape under `## Definitions` — a **clean, term-only** `###` heading (rule 5b), an optional
typed ```glossary``` field block (rule 5c), and a free markdown body that may span
paragraphs, tables, and fenced code (rule 5), with no duplicate term-heading slugs. Terms
named by a `reserved-for` field must be *reserved targets* (`reserved-for-target: true`)
and each reserved target must have a row under `## Reserved Targets` (rule 5d). The check
drives the glossary-anchor repair and ships as a durable guard so the file stays parseable
by the same `glossarian.model` Sedric's glossary tool consumes.

Read-only. Reports violations to stdout and sets an exit code:
  0 = valid · 1 = read OK but rule violations · 2 = path missing / unreadable.
Each violation carries a stable `code`; the ones `glossarian-fix` can repair also carry a
`fix` description, which the report prints alongside the command to run.

Built against contract v6 (v5 + governs scope, open reserved targets, fix hints).
Companion contract: contracts/glossary_format_check_contract.md
Tests:              tests/test_glossary_format_check.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from glossarian import model, scope
from glossarian.github_slug import github_slug
from glossarian.model import GlossaryModel, StrayBlock, TermBlock

DEFAULT_GLOSSARY = "docs/glossary.md"

USAGE = """\
Usage: glossarian-check [GLOSSARY_PATH] [--repo-root DIR] [--quiet]
       glossarian-check -h | --help

Validate a markdown glossary's structure (front matter, H1, required sections, the
Governance `governs` scope, definition entries, reserved targets). GLOSSARY_PATH defaults
to docs/glossary.md. Read-only.

Options:
  --repo-root DIR  the repository root the `governs` scope may not escape (default: the
                   nearest ancestor of the glossary containing `.git`)
  --quiet          print nothing; rely on the exit code
  -h, --help       show this help and exit 0

Exit codes: 0 valid, 1 rule violations, 2 path missing/unreadable or bad usage."""

# Required `##` sections, in canonical order (contract rule 4). Matched case-sensitively.
REQUIRED_SECTIONS: list[str] = [
    "Governance",
    "Definitions",
    "Confusable Pairs",
    "Renames and deprecated terms",
    "Reserved Targets",
]

# Placeholder bodies `glossarian-fix` may append when one of these sections is missing.
# Governance and Definitions are never stubbed: their content cannot be guessed.
SECTION_STUBS: dict[str, str] = {
    "Confusable Pairs": "None yet.",
    "Renames and deprecated terms": "None yet.",
    "Reserved Targets": "None.",
}

TERM_HEADING_LEVEL = 3  # `###` term headings under `## Definitions` (contract rule 5)

# Decorations that pollute a heading's github_slug and break inbound links (rule 5b).
DISALLOWED_HEADING_CHARS = "()*/:→"  # ( ) * / : →

# The typed field-block keys a term entry may declare (rule 5c).
ALLOWED_FIELD_KEYS: frozenset[str] = frozenset(
    {"aliases", "short", "confusable", "reserved-for", "see", "reserved-for-target"}
)
# The keys the Governance field block may declare (rule 4b).
ALLOWED_GOVERNANCE_KEYS: frozenset[str] = frozenset({scope.GOVERNS_KEY})

FIX_COMMAND = "glossarian-fix"


@dataclass
class Violation:
    line: int | None  # None when the rule is not tied to a specific line
    msg: str
    code: str = ""  # stable machine-readable rule id (contract rule 7)
    fix: str | None = None  # what `glossarian-fix` would change, when it can repair this


# --------------------------------------------------------------------------- #
# Rules (each applied to the structural model)                                 #
# --------------------------------------------------------------------------- #


def check_frontmatter(m: GlossaryModel) -> tuple[list[Violation], list[str]]:
    """Rule 2. Returns (violations, warnings)."""
    if m.frontmatter_error is not None:
        return [Violation(1, m.frontmatter_error, "frontmatter-malformed")], []
    data = m.frontmatter
    violations: list[Violation] = []
    warnings: list[str] = []
    if data.get("id") != "glossary":
        violations.append(
            Violation(1, f"front matter must declare `id: glossary` (found id={data.get('id')!r})", "frontmatter-id")
        )
    if data.get("is_source_of_truth", "").lower() != "true":
        warnings.append("front matter recommendation: set `is_source_of_truth: true`")
    return violations, warnings


def check_h1(m: GlossaryModel) -> list[Violation]:
    """Rule 3: exactly one `# Glossary` H1."""
    h1 = m.headings(1)
    if len(h1) == 0:
        return [Violation(None, "missing top-level `# Glossary` heading", "h1-missing")]
    if len(h1) > 1:
        return [
            Violation(
                h1[1].no,
                f"more than one top-level heading (found {len(h1)}; expected exactly one `# Glossary`)",
                "h1-duplicate",
            )
        ]
    if h1[0].htext != "Glossary":
        return [Violation(h1[0].no, f"top-level heading must be `# Glossary` (found `# {h1[0].htext}`)", "h1-text")]
    return []


def check_sections(m: GlossaryModel) -> list[Violation]:
    """Rule 4: required `##` sections present, verbatim, exactly once, in canonical order."""
    level2 = m.headings(2)
    violations: list[Violation] = []
    for name in REQUIRED_SECTIONS:
        occurrences = [ln for ln in level2 if ln.htext == name]
        if not occurrences:
            near = [ln for ln in level2 if ln.htext.strip().lower() == name.lower()]
            if near:
                violations.append(
                    Violation(
                        near[0].no,
                        f"missing required section `## {name}` (found `## {near[0].htext}`; case must match)",
                        "section-case",
                        fix=f"rename `## {near[0].htext}` to `## {name}`",
                    )
                )
            else:
                stub = SECTION_STUBS.get(name)
                violations.append(
                    Violation(
                        None,
                        f"missing required section `## {name}`",
                        "section-missing",
                        fix=f"append `## {name}` with the placeholder body `{stub}`" if stub else None,
                    )
                )
        elif len(occurrences) > 1:
            # A repeated required section makes the layout ambiguous — e.g. a second
            # `## Definitions` would shadow the first for the glossary parser.
            violations.append(
                Violation(
                    occurrences[1].no,
                    f"duplicate required section `## {name}` (also at line {occurrences[0].no})",
                    "section-duplicate",
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
                "section-order",
            )
        )
    return violations


def check_governance(
    m: GlossaryModel, glossary_path: Path | None = None, repo_root: Path | None = None
) -> list[Violation]:
    """Rule 4b: `## Governance` opens with a field block declaring a safe `governs` scope.

    The syntax of the value is always checked. The filesystem rules (the directory exists,
    it does not escape the repository root, it contains the glossary) run only when
    `glossary_path` is given — the pure-text `validate(text)` API has no location to
    resolve against.
    """
    if m.governance_heading_line is None:
        return []  # reported by check_sections
    g = m.governance
    if not g.present:
        return [
            Violation(
                m.governance_heading_line,
                "`## Governance` must open with a ```glossary field block declaring `governs: <path>` "
                "(the directory this glossary governs, relative to the glossary's own directory)",
                "governance-block-missing",
            )
        ]
    violations: list[Violation] = []
    if g.unterminated:
        violations.append(
            Violation(g.line, "unterminated ```glossary field block under `## Governance`", "governance-unterminated")
        )
    for key in g.fields:
        if key not in ALLOWED_GOVERNANCE_KEYS:
            violations.append(
                Violation(
                    g.line,
                    f"unknown key `{key}` in the `## Governance` field block "
                    f"(allowed: {', '.join(sorted(ALLOWED_GOVERNANCE_KEYS))})",
                    "governance-key-unknown",
                )
            )
    governs = g.fields.get(scope.GOVERNS_KEY)
    if governs is None:
        violations.append(
            Violation(
                g.line,
                "the `## Governance` field block must declare `governs: <path>` "
                "(e.g. `governs: ../` for docs/glossary.md governing the repository)",
                "governs-missing",
            )
        )
        return violations
    reason = scope.check_governs_syntax(governs)
    if reason is not None:
        violations.append(Violation(g.line, reason, "governs-invalid"))
        return violations
    if glossary_path is not None:
        try:
            scope.resolve_scope(glossary_path, governs, repo_root)
        except scope.ScopeError as exc:
            violations.append(Violation(g.line, str(exc), "governs-invalid"))
    return violations


def _split_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def check_definitions(m: GlossaryModel) -> tuple[list[Violation], int]:
    """Rules 5, 5b, 5c, 5d & 6: definition-entry shape, clean headings, the field block,
    reserved targets, and duplicate-slug detection.

    Returns (violations, entry_count). Absence of the section is reported by
    check_sections; here there is nothing to shape-check.
    """
    if m.definitions_heading_line is None:
        return [], 0

    violations: list[Violation] = []
    slugs: dict[str, int] = {}
    entry_count = 0
    # Rule 5c `see`-resolution needs every term slug up front (a `see` may point forward).
    terms = [b for b in m.definition_blocks if isinstance(b, TermBlock)]
    all_slugs = {b.slug for b in terms}
    # Rule 5d: the reserved targets are the terms that declare `reserved-for-target: true`.
    target_slugs = {b.slug for b in terms if b.fields.get("reserved-for-target", "").strip().lower() == "true"}

    for b in m.definition_blocks:
        if isinstance(b, StrayBlock):
            kind = "bold-paragraph entry" if b.kind == "bold" else "orphan text"
            if b.before_any_heading:
                violations.append(
                    Violation(
                        b.line,
                        f"definition body before any `###` term heading ({kind}); term entries must be `###` headings",
                        "definitions-stray-before-heading",
                    )
                )
            else:
                violations.append(
                    Violation(b.line, f"unexpected {kind} where a `###` term heading was expected", "definitions-stray")
                )
            continue

        # TermBlock — rule 5 (shape)
        entry_count += 1
        if b.level != TERM_HEADING_LEVEL:
            violations.append(
                Violation(b.heading_line, f"term heading must be level `###` (found `{'#' * b.level}`)", "term-level")
            )
        if b.slug in slugs:
            violations.append(
                Violation(
                    b.heading_line,
                    f"duplicate term-heading slug '{b.slug}' (first defined at line {slugs[b.slug]})",
                    "term-duplicate-slug",
                )
            )
        else:
            slugs[b.slug] = b.heading_line
        if b.body_line_count == 0:
            violations.append(
                Violation(b.heading_line, f"term `{b.term}` has an empty definition body", "term-empty-body")
            )
        if b.followed_by_heading_without_blank:
            violations.append(
                Violation(
                    b.next_heading_line,
                    "missing blank line before this term heading (definition block not terminated by a blank line)",
                    "term-no-blank-before-heading",
                    fix=f"insert a blank line before line {b.next_heading_line}",
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
                    "term-heading-chars",
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
                        "field-unterminated",
                    )
                )
            for key in b.fields:
                if key not in ALLOWED_FIELD_KEYS:
                    violations.append(
                        Violation(
                            b.field_block_line,
                            f"unknown field-block key `{key}` in term `{b.term}` "
                            f"(allowed: {', '.join(sorted(ALLOWED_FIELD_KEYS))})",
                            "field-key-unknown",
                        )
                    )
            flag = b.fields.get("reserved-for-target")
            if flag is not None and flag.strip().lower() not in {"true", "false"}:
                violations.append(
                    Violation(
                        b.field_block_line,
                        f"`reserved-for-target` must be `true` or `false` (found {flag!r}) in term `{b.term}`",
                        "field-reserved-for-target-value",
                    )
                )
            reserved = b.fields.get("reserved-for")
            if reserved is not None:
                for target in _split_list(reserved):
                    if target in target_slugs:
                        continue
                    fix = None
                    if github_slug(target) in target_slugs:
                        fix = f"rewrite `reserved-for: {target}` as the slug `{github_slug(target)}`"
                    violations.append(
                        Violation(
                            b.field_block_line,
                            f"`reserved-for: {target}` in term `{b.term}` does not name a reserved target "
                            "(a `###` term whose field block declares `reserved-for-target: true`)",
                            "field-reserved-for-unresolved",
                            fix=fix,
                        )
                    )
            see = b.fields.get("see")
            if see is not None and see not in all_slugs:
                fix = None
                if github_slug(see) in all_slugs:
                    fix = f"rewrite `see: {see}` as the slug `{github_slug(see)}`"
                violations.append(
                    Violation(
                        b.field_block_line,
                        f"`see: {see}` in term `{b.term}` does not resolve to another term's slug",
                        "field-see-unresolved",
                        fix=fix,
                    )
                )

    if entry_count == 0:
        violations.append(
            Violation(
                m.definitions_heading_line, "`## Definitions` contains no definition entries", "definitions-empty"
            )
        )
    return violations, entry_count


def check_reserved_targets(m: GlossaryModel) -> list[Violation]:
    """Rule 5d (section half): every reserved target has a row under `## Reserved Targets`,
    and every row names a reserved target."""
    if m.reserved_targets_heading_line is None:
        return []  # reported by check_sections
    terms = [b for b in m.definition_blocks if isinstance(b, TermBlock)]
    targets = {b.slug: b for b in terms if b.fields.get("reserved-for-target", "").strip().lower() == "true"}
    violations: list[Violation] = []
    seen: set[str] = set()
    for row in m.reserved_target_rows:
        if row.slug not in targets:
            violations.append(
                Violation(
                    row.line,
                    f"`## Reserved Targets` row names `{row.cell}` (slug `{row.slug}`), which is not a reserved "
                    "target term (define it under `## Definitions` with `reserved-for-target: true`)",
                    "reserved-row-unknown",
                )
            )
        seen.add(row.slug)
    for slug, b in targets.items():
        if slug not in seen:
            violations.append(
                Violation(
                    m.reserved_targets_heading_line,
                    f"reserved target `{b.term}` (line {b.heading_line}) has no row under `## Reserved Targets`",
                    "reserved-target-no-row",
                )
            )
    return violations


# --------------------------------------------------------------------------- #
# Driver                                                                       #
# --------------------------------------------------------------------------- #


def validate(
    text: str, *, glossary_path: Path | None = None, repo_root: Path | None = None
) -> tuple[list[Violation], list[str], int]:
    """Run every rule over the glossary text. Returns (violations, warnings, entry_count).

    `glossary_path` enables the filesystem half of the `governs` check (rule 4b);
    `repo_root` overrides the `.git` search that bounds it.
    """
    m = model.parse(text)
    violations: list[Violation] = []
    warnings: list[str] = []

    fm_v, fm_w = check_frontmatter(m)
    violations += fm_v
    warnings += fm_w
    violations += check_h1(m)
    violations += check_sections(m)
    violations += check_governance(m, glossary_path, repo_root)
    def_v, entry_count = check_definitions(m)
    violations += def_v
    violations += check_reserved_targets(m)

    violations.sort(key=lambda v: (v.line is None, v.line or 0))
    return violations, warnings, entry_count


def parse_args(argv: list[str]) -> tuple[Path, Path | None, bool] | None:
    """(glossary_path, repo_root, quiet), or None on a usage error (message printed)."""
    quiet = "--quiet" in argv
    repo_root: Path | None = None
    positional: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--quiet":
            pass
        elif tok == "--repo-root" or tok.startswith("--repo-root="):
            if "=" in tok:
                repo_root = Path(tok.split("=", 1)[1])
            else:
                i += 1
                if i >= len(argv):
                    print("error: --repo-root requires a directory argument", file=sys.stderr)
                    return None
                repo_root = Path(argv[i])
        elif tok.startswith("--"):
            print(f"error: unknown option: {tok}", file=sys.stderr)
            return None
        else:
            positional.append(tok)
        i += 1
    if len(positional) > 1:
        print(f"error: unexpected extra positional argument: {positional[1]}", file=sys.stderr)
        return None
    path = Path(positional[0]) if positional else Path(DEFAULT_GLOSSARY)
    return path, repo_root, quiet


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    parsed = parse_args(argv)
    if parsed is None:
        return 2
    path, repo_root, quiet = parsed

    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    violations, warnings, entry_count = validate(text, glossary_path=path, repo_root=repo_root)

    if not quiet:
        fixable = 0
        for w in warnings:
            print(f"{path}: warning: {w}")
            if "is_source_of_truth" in w:
                fixable += 1
                print(f"  fixable: `{FIX_COMMAND} {path}` would add `is_source_of_truth: true` to the front matter")
        for v in violations:
            loc = f"{path}:{v.line}" if v.line is not None else f"{path}"
            print(f"{loc}: {v.msg}")
            if v.fix is not None:
                fixable += 1
                print(f"  fixable: `{FIX_COMMAND} {path}` would {v.fix}")
        if not violations:
            print(f"OK: {path} — {entry_count} definition entr{'y' if entry_count == 1 else 'ies'}")
        if fixable:
            noun = "issue" if fixable == 1 else "issues"
            print(f"{fixable} {noun} can be repaired automatically: run `{FIX_COMMAND} {path}`")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
