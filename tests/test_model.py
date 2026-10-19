"""test_model — tests for glossarian.model, built against contract v2.

The structural model is parse-only: it records what the document IS (front matter,
headings, Definitions blocks) without judging validity. These tests pin the structure
the linter and Sedric's future semantic index both read.

v2 coverage: the typed ```glossary field block under a term heading (parsed into
TermBlock.fields), and the relaxed body traversal — a term body now spans blank lines,
tables, and fenced code, running to the next heading instead of the first blank line.
"""

from __future__ import annotations

from glossarian import model
from glossarian.github_slug import github_slug
from glossarian.model import StrayBlock, TermBlock

VALID = """\
---
id: glossary
is_source_of_truth: true
---

# Glossary

## Governance

Rules.

## Definitions

### working agent
The write-capable agent that performs an item's work.

### human_holds
A completability gate value.

## Confusable Pairs
"""


# --- Front matter ---------------------------------------------------------- #


def test_frontmatter_parsed_as_scalars() -> None:
    m = model.parse(VALID)
    assert m.frontmatter_error is None
    assert m.frontmatter["id"] == "glossary"
    assert m.frontmatter["is_source_of_truth"] == "true"


def test_missing_frontmatter_sets_error_and_empty_map() -> None:
    m = model.parse("# Glossary\n\n## Definitions\n")
    assert m.frontmatter_error is not None
    assert m.frontmatter == {}


def test_unterminated_frontmatter_sets_error() -> None:
    m = model.parse("---\nid: glossary\n# Glossary\n")
    assert m.frontmatter_error is not None and "unterminated" in m.frontmatter_error


# --- Heading skeleton ------------------------------------------------------ #


def test_headings_by_level() -> None:
    m = model.parse(VALID)
    assert [ln.htext for ln in m.headings(1)] == ["Glossary"]
    assert [ln.htext for ln in m.headings(2)] == ["Governance", "Definitions", "Confusable Pairs"]


def test_definitions_heading_line_located() -> None:
    m = model.parse(VALID)
    assert m.definitions_heading_line is not None


# --- Definition blocks ----------------------------------------------------- #


def test_term_blocks_parsed_with_shared_slug() -> None:
    m = model.parse(VALID)
    terms = [b for b in m.definition_blocks if isinstance(b, TermBlock)]
    assert [b.term for b in terms] == ["working agent", "human_holds"]
    assert [b.slug for b in terms] == [github_slug("working agent"), github_slug("human_holds")]
    assert all(b.level == 3 and b.body_line_count >= 1 for b in terms)


def test_missing_blank_line_flag_carries_next_heading() -> None:
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.\n\n### human_holds",
        "### working agent\nThe write-capable agent that performs an item's work.\n### human_holds",
    )
    m = model.parse(text)
    first = next(b for b in m.definition_blocks if isinstance(b, TermBlock))
    assert first.followed_by_heading_without_blank
    assert first.next_heading_line is not None


def test_bold_paragraph_becomes_stray_block() -> None:
    text = VALID.replace("### working agent", "**working agent**")
    m = model.parse(text)
    strays = [b for b in m.definition_blocks if isinstance(b, StrayBlock)]
    assert any(b.kind == "bold" and b.before_any_heading for b in strays)


def test_empty_body_recorded_as_zero_count() -> None:
    text = VALID.replace(
        "### human_holds\nA completability gate value.",
        "### human_holds\n",
    )
    m = model.parse(text)
    hh = [b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "human_holds"]
    assert hh and hh[0].body_line_count == 0


def test_fenced_heading_not_parsed_as_block() -> None:
    text = VALID.replace("Rules.", "```\n### not a term\nbody\n```")
    m = model.parse(text)
    terms = [b.term for b in m.definition_blocks if isinstance(b, TermBlock)]
    assert "not a term" not in terms
    assert terms == ["working agent", "human_holds"]


def test_no_definitions_section_yields_none_and_empty_blocks() -> None:
    text = "---\nid: glossary\n---\n\n# Glossary\n\n## Governance\n\nRules.\n"
    m = model.parse(text)
    assert m.definitions_heading_line is None
    assert m.definition_blocks == []


# --- v2: typed field block ------------------------------------------------- #

FIELDS = """\
---
id: glossary
---

# Glossary

## Definitions

### capability grant
```glossary
aliases: capabilities
short: Per-item least-privilege grant.
confusable: capability tag (Lacey)
```
The per-item least-privilege declaration of what a working agent may do.

A second paragraph, separated by a blank line.

| col | col |
|---|---|
| a | b |

### worker
```glossary
see: managed_by
```
Defined under managed_by.

## Confusable Pairs
"""


def test_field_block_parsed_into_fields() -> None:
    m = model.parse(FIELDS)
    cg = next(b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "capability grant")
    assert cg.field_block_present and cg.field_block_line is not None
    assert cg.fields == {
        "aliases": "capabilities",
        "short": "Per-item least-privilege grant.",
        "confusable": "capability tag (Lacey)",
    }
    # Load-bearing (contract v2 behavior 4): field-block lines are not counted as body.
    assert cg.term == "capability grant" and cg.slug == github_slug("capability grant")


def test_body_spans_blank_lines_and_tables() -> None:
    # Load-bearing (v2 behavior 3): the body runs to the next heading; the second
    # paragraph and the table are body, NOT stray blocks.
    m = model.parse(FIELDS)
    strays = [b for b in m.definition_blocks if isinstance(b, StrayBlock)]
    assert strays == []
    cg = next(b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "capability grant")
    assert cg.body_line_count >= 4  # two prose lines + two table rows, blanks excluded


def test_term_without_field_block_has_empty_fields() -> None:
    m = model.parse(VALID)
    wa = next(b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "working agent")
    assert wa.fields == {} and wa.field_block_present is False and wa.field_block_line is None


def test_see_field_records_target() -> None:
    m = model.parse(FIELDS)
    w = next(b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "worker")
    assert w.fields.get("see") == "managed_by"


def test_glossary_fence_not_first_is_body_not_fields() -> None:
    # A ```glossary fence that is not the first non-blank content under the heading is
    # ordinary body, not the typed field block.
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\nProse first.\n```glossary\naliases: not-parsed\n```",
    )
    m = model.parse(text)
    wa = next(b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "working agent")
    assert wa.field_block_present is False
    assert wa.fields == {}


# --- v2: mid-section stray detection survives the relaxed body (F1) -------- #


def test_mid_section_bold_entry_is_stray_not_swallowed() -> None:
    # Load-bearing: a `**bold**` paragraph that opens after a blank line, sitting BETWEEN two
    # converted `###` entries, must surface as a StrayBlock (before_any_heading=False) rather
    # than being absorbed into the preceding term's body. This is glossarian's central
    # capability — catching an unconverted entry — and the relaxed body must not lose it.
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\nThe write-capable agent that performs an item's work.\n\n"
        "**leftover unconverted entry**\nNever converted to a heading.",
    )
    m = model.parse(text)
    strays = [b for b in m.definition_blocks if isinstance(b, StrayBlock)]
    assert any(b.kind == "bold" and b.before_any_heading is False for b in strays)
    # the preceding term's body stops before the stray; both real terms still parse
    terms = [b.term for b in m.definition_blocks if isinstance(b, TermBlock)]
    assert terms == ["working agent", "human_holds"]


def test_bold_first_body_line_is_body_not_stray() -> None:
    # A `**bold**` line as the FIRST content under a heading is that term's body, not a
    # stray — only a bold paragraph-start that follows other body content is suspected.
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\n**Bold lead** then prose, all one paragraph.",
    )
    m = model.parse(text)
    strays = [b for b in m.definition_blocks if isinstance(b, StrayBlock)]
    assert strays == []


# --- v2: unterminated field block is recorded (F3) ------------------------- #


def test_unterminated_field_block_recorded() -> None:
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\n```glossary\naliases: doer\nfence never closed",
    )
    m = model.parse(text)
    wa = next(b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "working agent")
    assert wa.field_block_present and wa.field_block_unterminated


def test_terminated_field_block_not_flagged_unterminated() -> None:
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\n```glossary\naliases: doer\n```\nThe write-capable agent.",
    )
    m = model.parse(text)
    wa = next(b for b in m.definition_blocks if isinstance(b, TermBlock) and b.term == "working agent")
    assert wa.field_block_present and wa.field_block_unterminated is False
