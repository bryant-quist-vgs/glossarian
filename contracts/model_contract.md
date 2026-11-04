Contract version: v3

# model — Glossary structural parse: Contract

> **v3 — section field blocks and Reserved Targets rows (2026-11-04).** Two additive
> structures: (1) the `## Governance` section's leading ```` ```glossary ```` block is parsed
> into `GlossaryModel.governance: SectionFields` (it carries the `governs:` scope the linter
> validates via `glossarian.scope`); (2) the data rows of the table under `## Reserved
> Targets` are parsed into `reserved_target_rows: list[ReservedTargetRow]`, each with the
> slug its first cell names. A generic `section_lines(name)` helper exposes any `##`
> section's lines. Parse-only, as before: which `governs` is safe and whether every row names
> a reserved target is `glossary_format_check` v6 policy.

`glossarian.model.parse(text) -> GlossaryModel` turns glossary markdown into a typed
**structural** model: the front-matter `key: scalar` map, the fence-aware body lines, the
heading skeleton, and the `## Definitions` section parsed into typed blocks. It records
what the document **is** — it does **not** judge validity (that is `glossary_format_check`,
which applies rules to this model) and does **not** build the semantic term/alias/reserved
index that Sedric's glossary query tool layers on top.

> **Why this module exists.** It is the seam the `glossarian` package was extracted for:
> one parser, consumed by the standalone linter today and (incrementally) by Sedric's
> runtime glossary tool tomorrow, so "structurally compliant" and "parseable into Sedric's
> index" can never diverge. The parsing primitives here were lifted verbatim from the v2
> `glossary_format_check.py` (front-matter split, fence-aware body scan, Definitions
> traversal); the linter now consumes them instead of owning them.
>
> **v2 — the enriched single-file entry grammar (additive structure for `contracts.15`).**
> The glossary-structure decision selected a single hand-authored markdown file in which each
> term entry carries (a) a **clean, term-only `###` heading** (so the heading's `github_slug`
> equals the anchor inbound links target — no qualifier/alias pollution), (b) an **optional
> typed field block** in a fenced ```` ```glossary ```` region immediately under the heading
> (`aliases` / `short` / `confusable` / `reserved-for` / `see`), and (c) a **free markdown
> body** that may span multiple paragraphs and contain blank lines, tables, and diagrams.
> Two model changes follow: (1) `TermBlock` gains `fields` / `field_block_present` /
> `field_block_line` from the parsed ```` ```glossary ```` block; (2) a term entry's body now
> runs from its heading (after any field block) **to the next heading or section end** rather
> than terminating at the first blank line. This module still records what the document *is*;
> the linter (`glossary_format_check` v4) judges heading-cleanliness, the allowed field keys,
> and `see`-resolution. The semantic index (the full alias/reserved/deprecated/cross-ref
> graph and short-gloss derivation) remains the `contracts.15` deliverable, layered on these
> fields — out of scope for this module.
>
> **v1 history (retained).** Parse-only structural model: front matter, fence-aware body,
> Definitions blocks. The single-contiguous-body traversal and the absence of the field block
> were v1; v2 relaxes the body and adds the field block, both consumed by the v4 linter.

## Inputs

- **`text`** — the full glossary markdown document as a `str`. **Trust:** repository
  content, trusted-at-rest; only read and parsed as text, never executed.

(No files, no CLI, no environment — callers read the file and pass text.)

## Outputs

`parse` returns a `GlossaryModel` dataclass:

- **`frontmatter: dict[str, str]`** — the narrow `key: scalar` subset (the same hand-rolled
  parse used across the repo's docs tooling; no PyYAML). Empty `{}` when the block is
  malformed.
- **`frontmatter_error: str | None`** — a message when the front-matter block is missing or
  unterminated, else `None`.
- **`body: list[Line]`** — every body line (after the front matter) tagged with heading
  info; headings inside fenced code blocks are NOT tagged as headings.
- **`definitions_heading_line: int | None`** — the 1-based line of `## Definitions`, or
  `None` when the section is absent.
- **`definition_blocks: list[TermBlock | StrayBlock]`** — the Definitions section parsed
  into ordered typed blocks (below).
- **`governance_heading_line: int | None`** and **`governance: SectionFields`** (v3) — the
  line of `## Governance` and its leading field block: `present`, `line` (opening fence),
  `unterminated`, `fields` (the `key: value` map, e.g. `{"governs": "../"}`; `{}` when
  absent). The block must be the section's first non-blank content, exactly as for a term.
- **`reserved_targets_heading_line: int | None`** and **`reserved_target_rows:
  list[ReservedTargetRow]`** (v3) — the line of `## Reserved Targets` and the data rows of
  the first pipe table in that section (header row and `|---|` separator skipped, fenced
  lines ignored): `line`, `cell` (the first cell, stripped), `slug` (the fragment of the
  first link in the cell when there is one, else `github_slug` of the cell text with
  backticks and `*` removed; `_` is kept because it is part of a term).
- **`section_lines(name) -> list[Line] | None`** (v3) — the lines of the first `## <name>`
  section up to the next `##`, or `None`.
- **`headings(level)`** — helper returning all body headings at a given level, in order.

Block types:

- **`TermBlock`** — a heading found under `## Definitions`: `heading_line`, `level` (the
  level actually found), `term`, `slug` (`github_slug(term)`), `body_line_count`
  (non-blank, non-heading body lines from after any field block to the next heading —
  blank lines, tables, and fenced code inside the body are spanned, not terminators),
  `followed_by_heading_without_blank` (the line immediately before the next sibling heading
  is non-blank), `next_heading_line` (that heading's line when the previous is true), and
  the **v2 field-block fields**: `fields` (a `dict[str, str]` of the `key: value` lines
  parsed from the entry's ```` ```glossary ```` block — empty `{}` when absent),
  `field_block_present` (bool), `field_block_line` (the 1-based line of the opening fence,
  or `None`), and `field_block_unterminated` (bool — True when the ```` ```glossary ````
  fence reached the section end with no closing fence, so the linter can name the unclosed
  fence rather than letting the rest of the section be silently consumed as field lines).
  The field block, when present, must be the first non-blank content under the heading; a
  ```` ```glossary ```` fence appearing later in the body is ordinary body content, not
  parsed into `fields`.
- **`StrayBlock`** — non-heading content where a `###` term heading was expected: `line`,
  `kind` (`"bold"` for a `**term**` pre-migration paragraph, else `"orphan"`), and
  `before_any_heading`.

`Load-bearing: glossary_format_check derives every rule-5/rule-6 violation from these block
fields; Sedric's index will read the same TermBlock/slug structure. The block shape IS the
parse contract.`

## Behaviors

1. **Front-matter split.** A leading `---` line opens the block, which runs to the next
   `---`; everything after is the body. A file not starting with `---` has no front matter
   (`frontmatter_error` set); an unopened-but-unterminated block sets the error too.
2. **Fence-aware heading detection.** ATX headings (`#`..`######`) are tagged with level and
   text, EXCEPT inside ```` ``` ````/`~~~` fenced blocks, whose lines are inert.
3. **Definitions traversal.** The lines from `## Definitions` to the next `##` (or EOF) are
   walked into blocks: a heading starts a `TermBlock` whose body runs **to the next heading
   (any level) or section end**, spanning blank lines, tables, and fenced code (v2 — no
   longer terminated at the first blank line). **One exception preserves stray detection
   under the relaxed body:** a `**bold**`-led line that *opens a new paragraph* (its
   preceding line is blank) and is **not** the entry's first body line ends the body there —
   it is a suspected unconverted pre-migration `**term**` entry. The traversal then re-enters
   the stray path on it, producing a `StrayBlock(kind="bold", before_any_heading=False)`.
   Other non-heading content (prose, tables, a bold lead on the first body line, inline or
   soft-wrapped bold) stays body. Non-heading content **before** the first term heading
   becomes a `StrayBlock` as before (consumed up to the next heading, so a multi-paragraph
   stray collapses to one block). Slugs are computed via the shared `github_slug`.
   `Load-bearing: the bold-paragraph-start break is what keeps glossarian's central
   capability — flagging an unconverted **bold** entry sitting BETWEEN two converted ###
   entries — alive under the relaxed body. glossary_format_check rule 5 derives its
   "unexpected bold-paragraph entry where a ### heading was expected" violation from the
   resulting StrayBlock.`
4. **Field-block parse (v2).** Immediately under a term heading (after any blank lines), a
   fenced block opened by ```` ```glossary ```` is consumed and its `key: value` lines are
   parsed into `TermBlock.fields` (the same narrow `key: scalar` shape as the front matter;
   `field_block_present`/`field_block_line` are set). Its lines are not counted toward
   `body_line_count`. When no closing fence is found before the section ends, the block is
   recorded with `field_block_unterminated=True` (it still fails closed — the remaining
   lines are taken as field lines — but the flag lets the linter name the unclosed fence).
   A ```` ```glossary ```` fence that is not the first non-blank content under the heading is
   left as body. The module records the keys verbatim; which keys are permitted is the
   linter's policy (v4), not the parser's.
5. **Parse-only.** The module records structure and never raises on "invalid" input — an
   empty body, a bold paragraph, a duplicate slug, an unknown field key are all faithfully
   represented, not rejected. Judging them is the linter's job.
6. **Governance field block (v3).** The same field-block parser as behavior 4, applied to the
   lines of `## Governance`: a ```` ```glossary ```` fence that is the section's first
   non-blank content fills `governance.fields`; one appearing after prose is ordinary body
   and `governance.present` stays `False`.
7. **Reserved Targets rows (v3).** Within `## Reserved Targets`, lines starting with `|`
   outside fences form the table; the first such line is the header and any `|---|`-style
   line is a separator; each remaining line yields a `ReservedTargetRow` whose `slug` comes
   from the first cell as described under Outputs. Rows with an empty first cell are skipped.

Anything the module does beyond producing this structure is undeclared drift.

## Declared capability surface

- **Filesystem / network / subprocess / environment / secrets:** None. Pure text→dataclass
  transform over `re` and the shared `github_slug`.

## Assumptions for operation

- Python >= 3.14. Standard library only (`re`, `dataclasses`, `typing`) plus
  `glossarian.github_slug`.
- The slug per term heading comes from `glossarian.github_slug` (one shared definition);
  changing slugging is a change to that contract and ripples here.
- Front matter is the narrow `key: scalar` subset (no nested maps required).

## Anti-patterns this module must not do

- Do **not** apply validation rules or emit "violations" — that is the linter's layer.
- Do **not** re-inline the slug algorithm; import the shared `github_slug`.
- Do **not** import a YAML library; parse the narrow front-matter subset by hand.
- Do **not** build the semantic alias/reserved/deprecated index here — that is
  `contracts.15`, layered on top, and out of scope.

## Revision rules

- Adding fields to a block or `GlossaryModel` is additive. Changing the meaning of an
  existing field (or the traversal that fills it) is load-bearing: bump the version and
  re-verify `glossary_format_check` and its fixtures.
- When the `contracts.15` semantic layer lands, it consumes this model; widening the model
  to serve it should be additive, preserving the structural fields the linter reads.

## Revision history

- v3 — Governance field block (`governs:`), Reserved Targets rows, and `section_lines`
  (2026-11-04), consumed by glossary_format_check v6 and gather_reference_terms v3.
- v2 — field block and relaxed body (see the note at the top).
