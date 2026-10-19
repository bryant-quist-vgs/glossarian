"""glossarian.model — structural parse of a glossary markdown document.

Turns glossary text into a typed *structural* model: the front-matter `key: scalar`
map, the fence-aware body lines, the heading skeleton, and the `## Definitions` section
parsed into typed blocks (term entries + stray content). It records what the document
*is* — not whether it is valid (that is `glossary_format_check`, which applies rules to
this model) and not the semantic term/alias/reserved/deprecated index the Sedric glossary
query tool layers on top (the `contracts.15` deliverable builds its index from this model).

This is the seam the package was extracted for: one parser, consumed by the standalone
linter today and by Sedric's runtime glossary tool tomorrow, so "structurally compliant"
and "parseable into Sedric's index" can never diverge.

Built against contract v2.
Companion contract: contracts/model_contract.md
Tests:              tests/test_model.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from glossarian.github_slug import github_slug

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BOLD_RE = re.compile(r"^\*\*.+")  # a `**term**`-style bold paragraph (pre-migration shape)
_FIELD_FENCE_INFO = "glossary"  # info-string opening a term entry's typed field block


# --------------------------------------------------------------------------- #
# Typed structures                                                             #
# --------------------------------------------------------------------------- #


@dataclass
class Line:
    """One body line, tagged with ATX-heading info (headings inside code fences excluded)."""

    no: int  # 1-based line number in the source file
    raw: str
    is_heading: bool
    level: int  # heading level (0 when not a heading)
    htext: str  # heading text (empty when not a heading)

    @property
    def blank(self) -> bool:
        return self.raw.strip() == ""


@dataclass
class TermBlock:
    """A `###`-style term entry parsed under `## Definitions` (a candidate definition)."""

    heading_line: int  # 1-based line of the term heading
    level: int  # heading level actually found (expected 3)
    term: str  # the heading text
    slug: str  # github_slug(term)
    body_line_count: int  # non-blank, non-heading body lines (field block excluded; v2)
    followed_by_heading_without_blank: bool  # next sibling heading not separated by a blank line
    next_heading_line: int | None = None  # line of that next heading, when the above is true
    # v2 — the typed field block (```glossary ... ```) immediately under the heading.
    fields: dict[str, str] = field(default_factory=dict)  # parsed key: value lines ({} when absent)
    field_block_present: bool = False  # a ```glossary block was found right under the heading
    field_block_line: int | None = None  # 1-based line of the opening ```glossary fence
    field_block_unterminated: bool = False  # the ```glossary fence ran to section end with no close


@dataclass
class StrayBlock:
    """Non-heading content inside `## Definitions` where a `###` term heading was expected."""

    line: int  # 1-based line where the stray content starts
    kind: Literal["bold", "orphan"]  # "bold" = a `**term**` (pre-migration) paragraph
    before_any_heading: bool  # appeared before the section's first term heading


Block = TermBlock | StrayBlock


@dataclass
class GlossaryModel:
    """The structural model of a glossary document."""

    frontmatter: dict[str, str]  # narrow `key: scalar` map; empty when the block is malformed
    frontmatter_error: str | None  # message when the front-matter block is missing/unterminated
    body: list[Line]  # fence-aware tagged body lines (everything after the front matter)
    definitions_heading_line: int | None  # line of `## Definitions`, or None if absent
    definition_blocks: list[Block] = field(default_factory=list)

    def headings(self, level: int) -> list[Line]:
        """All body headings at the given level, in document order."""
        return [ln for ln in self.body if ln.is_heading and ln.level == level]


# --------------------------------------------------------------------------- #
# Parsing                                                                      #
# --------------------------------------------------------------------------- #


def _split_frontmatter(lines: list[str]) -> tuple[list[str], list[Line], str | None]:
    """Return (frontmatter_inner_lines, body_Line_records, error).

    error is a message string when the front-matter block is malformed, else None.
    Body records carry absolute (1-based) line numbers and fence-aware headings.
    """
    if not lines or lines[0].strip() != "---":
        return [], _scan_body(lines, start_no=1), "missing front matter (file must begin with '---')"
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            fm = lines[1:idx]
            body = _scan_body(lines[idx + 1 :], start_no=idx + 2)
            return fm, body, None
    return [], _scan_body(lines, start_no=1), "unterminated front matter (no closing '---')"


def _scan_body(body_lines: list[str], start_no: int) -> list[Line]:
    """Tag each body line, detecting ATX headings while ignoring fenced code blocks."""
    out: list[Line] = []
    in_fence = False
    fence_marker = ""
    for offset, raw in enumerate(body_lines):
        no = start_no + offset
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif stripped.startswith(fence_marker):
                in_fence, fence_marker = False, ""
            out.append(Line(no, raw, False, 0, ""))
            continue
        if not in_fence:
            m = _HEADING_RE.match(raw)
            if m:
                out.append(Line(no, raw, True, len(m.group(1)), m.group(2).strip()))
                continue
        out.append(Line(no, raw, False, 0, ""))
    return out


def _parse_frontmatter_scalars(fm: list[str]) -> dict[str, str]:
    """The narrow `key: scalar` subset used across the repo's docs tooling (no PyYAML)."""
    data: dict[str, str] = {}
    for raw in fm:
        s = raw.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        key, _, val = s.partition(":")
        data[key.strip()] = val.strip().strip("'\"")
    return data


def _is_fence(ln: Line) -> bool:
    """A code-fence delimiter line (``` or ~~~), possibly with an info-string."""
    s = ln.raw.lstrip()
    return s.startswith("```") or s.startswith("~~~")


def _opens_field_block(ln: Line) -> bool:
    """The ```glossary opening fence of a term entry's typed field block."""
    s = ln.raw.lstrip()
    return s.startswith("```" + _FIELD_FENCE_INFO) or s.startswith("~~~" + _FIELD_FENCE_INFO)


def _parse_field_block(section: list[Line], start: int) -> tuple[dict[str, str], int, bool]:
    """Parse a ```glossary field block starting at `start` (its opening fence).

    Returns (fields, index_after_block, unterminated). Lines are the narrow `key: value`
    subset; a closing fence terminates the block. When the block runs to section end with
    no closing fence, `unterminated` is True (the linter surfaces a specific diagnostic
    rather than letting the whole section be silently swallowed as field lines).
    """
    fields: dict[str, str] = {}
    k = start + 1
    n = len(section)
    while k < n and not _is_fence(section[k]):
        s = section[k].raw.strip()
        if s and not s.startswith("#") and ":" in s:
            key, _, val = s.partition(":")
            fields[key.strip()] = val.strip()
        k += 1
    unterminated = k >= n  # reached section end without a closing fence
    if k < n:  # consume the closing fence
        k += 1
    return fields, k, unterminated


def _parse_definition_blocks(section: list[Line]) -> list[Block]:
    """Walk the lines of the Definitions section into typed blocks (no validation here)."""
    blocks: list[Block] = []
    seen_heading = False
    i, n = 0, len(section)
    while i < n:
        ln = section[i]
        if ln.blank:
            i += 1
            continue
        if not ln.is_heading:
            kind: Literal["bold", "orphan"] = "bold" if _BOLD_RE.match(ln.raw.strip()) else "orphan"
            blocks.append(StrayBlock(line=ln.no, kind=kind, before_any_heading=not seen_heading))
            # consume to the next heading so a multi-paragraph stray is one block
            i += 1
            while i < n and not section[i].is_heading:
                i += 1
            continue

        # A heading inside the Definitions section: a (candidate) term entry.
        seen_heading = True
        j = i + 1

        # Optional typed field block, immediately under the heading (blank lines allowed first).
        k = j
        while k < n and section[k].blank:
            k += 1
        fields: dict[str, str] = {}
        field_block_present = False
        field_block_line: int | None = None
        field_block_unterminated = False
        if k < n and not section[k].is_heading and _opens_field_block(section[k]):
            field_block_present = True
            field_block_line = section[k].no
            fields, k, field_block_unterminated = _parse_field_block(section, k)

        # Body: everything from here to the next heading (blank lines / tables / fences spanned).
        # A `**bold**` line that opens a new paragraph (preceded by a blank) is NOT body — it is
        # a suspected unconverted pre-migration entry, so the body stops there and the main loop
        # re-enters the stray branch on it. This keeps glossarian's central capability (catching
        # an unconverted `**bold**` entry sitting *between* converted `###` entries) alive under
        # the relaxed body, where blank lines no longer terminate a definition.
        body_count = 0
        m = k
        while m < n and not section[m].is_heading:
            if m > k and section[m - 1].blank and _BOLD_RE.match(section[m].raw.lstrip()):
                break
            if not section[m].blank:
                body_count += 1
            m += 1
        followed_by_heading = m < n and section[m].is_heading
        # The block is "unterminated" when the line just before the next heading is non-blank.
        without_blank = followed_by_heading and m - 1 >= i and not section[m - 1].blank
        blocks.append(
            TermBlock(
                heading_line=ln.no,
                level=ln.level,
                term=ln.htext,
                slug=github_slug(ln.htext),
                body_line_count=body_count,
                followed_by_heading_without_blank=without_blank,
                next_heading_line=section[m].no if without_blank else None,
                fields=fields,
                field_block_present=field_block_present,
                field_block_line=field_block_line,
                field_block_unterminated=field_block_unterminated,
            )
        )
        i = m
    return blocks


def parse(text: str) -> GlossaryModel:
    """Parse glossary markdown text into its structural model."""
    lines = text.splitlines()
    fm_inner, body, fm_error = _split_frontmatter(lines)
    frontmatter = _parse_frontmatter_scalars(fm_inner) if fm_error is None else {}

    def_start = next(
        (i for i, ln in enumerate(body) if ln.is_heading and ln.level == 2 and ln.htext == "Definitions"),
        None,
    )
    if def_start is None:
        return GlossaryModel(frontmatter, fm_error, body, None, [])

    section: list[Line] = []
    for ln in body[def_start + 1 :]:
        if ln.is_heading and ln.level == 2:
            break
        section.append(ln)
    blocks = _parse_definition_blocks(section)
    return GlossaryModel(frontmatter, fm_error, body, body[def_start].no, blocks)
