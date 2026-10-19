Contract version: v5

# glossary_format_check — Glossary structure validator: Contract

Validate that a glossary (default `docs/glossary.md`) conforms to the canonical structure
the rest of the system relies on: YAML front matter, a single top-level `# Glossary`
heading, the four required second-level sections, and a machine-parseable definition-entry
shape under `## Definitions`. It drives the glossary-anchor repair (the live glossary does
not yet meet the standard) and ships as a **durable guard** so the file stays parseable by
the same `glossarian.model` Sedric's glossary tool consumes. The script reports violations
and sets an exit code; it never edits the glossary.

> **v4 — the enriched single-file entry grammar.** The glossary-structure decision selected
> a single hand-authored markdown file where each term entry is a **clean, term-only `###`
> heading** + an **optional typed ```` ```glossary ```` field block** + a **free markdown
> body** (multi-paragraph, tables, diagrams). Three rule changes follow: (1) **rule 5 relaxes**
> — a body now runs to the next heading and may contain blank lines, tables, and fenced code,
> so the v2/v3 "single contiguous body + terminating blank line" requirement is dropped (the
> non-empty-body and blank-line-before-the-next-heading checks remain); (2) **rule 5b (new):
> the term heading must be the canonical term only** — it must not contain `(`, `)`, `*`, `/`,
> `:`, or `→`, the decorations that polluted the heading's `github_slug` and broke inbound
> `glossary.md#slug` links (qualifiers/aliases move into the field block or the body);
> (3) **rule 5c (new): the field block is validated** — its keys must be drawn from
> `{aliases, short, confusable, reserved-for, see}`, `reserved-for` ∈ `{lacey,
> auditable-script}`, and a `see` value must resolve to another term's slug. The slug still
> comes from the shared `github_slug` (via the model), so F1/F2 stay closed. The full semantic
> alias/reserved/deprecated index and the Confusable-table⇄field cross-check are layered later
> (`contracts.15`) and are **not** part of this version.
>
> **v3 history (retained):** relocated into the `glossarian` package; parsing delegated to
> `glossarian.model`; the module is pure **policy**.
>
> **v2 history (retained):** F1+F2 corrected and extracted the slug to a shared library;
> F3 added duplicate-required-section detection. The required-vs-allowed section policy
> (four required, extras permitted) and the term-heading level (`###`) remain.

## Inputs

- **Argv positional `glossary_path`** — zero or one path; defaults to `docs/glossary.md`.
  **Trust:** operator-provided. A missing/unreadable path is exit 2.
- **`--quiet`** — suppress the per-violation stdout report; rely on the exit code.
- **`-h` / `--help`** — print the usage text to stdout and exit 0 before any path is read
  (v5). Takes precedence over every other argument.
- **The glossary file** — UTF-8 markdown with optional `---` front matter. **Trust:**
  repository content, trusted-at-rest; read and parsed, never executed.

(No stdin. No environment inputs.)

## Outputs

- **stdout** — deterministic, human-readable. On success: one `OK:` line naming the file
  and the definition-entry count. On failure: one line per violation with the offending
  1-based line where determinable. Suppressed under `--quiet`.
- **Exit codes:** `0` valid · `1` read OK but one or more rule violations · `2` path
  missing/unreadable.
  `Load-bearing: callers (tests, the checklist's final-validation step) gate on the exit
  code, not the prose. Exit 0 == "the glossary meets the standard the glossary tool depends
  on."`
- **No file output.** Never writes, creates, or edits any file.

## Behaviors

Each rule is applied to the `GlossaryModel` produced by `glossarian.model.parse`. Anything
not listed is undeclared drift.

1. **Parse.** Obtain the structural model from `glossarian.model` (front matter, fence-aware
   body, Definitions blocks). This module does not re-implement parsing.
2. **Front matter present and identifies the glossary.** Require a well-formed block with
   `id: glossary`. Missing/unterminated block or missing/incorrect `id` is a violation;
   `is_source_of_truth: true` absence is a non-fatal **warning** (does not set exit 1).
3. **Exactly one top-level `# Glossary` heading.** Zero, more than one, or a differently
   named H1 is a violation.
4. **The four required `##` sections present, named verbatim, exactly once, in canonical
   order:** `## Governance`, `## Definitions`, `## Confusable Pairs`, `## Renames and
   deprecated terms`. A missing/mis-cased section names which one; a **duplicate** required
   section is a separate violation (F3); out-of-order is "malformed section order".
   **Additional `##` sections are permitted** and ignored by the order/duplicate checks.
   > **Flag for 3.1/3.2:** the live doc uses `## Confusable pairs` (lowercase p) and carries
   > `## Reserved for sister projects` (not in the required set). The migration renames the
   > live heading to match, or this contract is amended. Surfaced, not silently resolved.
5. **Definition-entry shape under `## Definitions`** (from the model's `definition_blocks`):
   each entry is a `###` term heading, an **optional** ```` ```glossary ```` field block, and
   a **free markdown body** that may span multiple paragraphs and contain blank lines, tables,
   and fenced code (v4 — the body runs to the next heading, no longer terminating at the first
   blank line). Violations: a `StrayBlock` **before the first heading** (orphan / pre-migration
   `**bold**` paragraph); a `StrayBlock` **where a heading was expected** — under the relaxed
   body this is specifically a `**bold**`-led paragraph-start *between* two `###` entries (the
   model's bold-break, contract `model` behavior 3), reported as "unexpected bold-paragraph
   entry where a `###` term heading was expected"; a `TermBlock` whose level is not `###`; an
   empty definition body (no non-blank body lines outside the field block); a block whose
   body's last line abuts the next term heading with no separating blank line. The section
   must contain **at least one** entry.
   > **Reachability (v4).** Under the relaxed body, ordinary prose/tables are legitimate body,
   > so the only mid-section stray the linter still raises is the `**bold**` paragraph-start
   > the model breaks on — narrower than the v3 "any non-heading content" rule, but it is the
   > one that matters: the unconverted pre-migration `**term**` entry. This deliberately
   > preserves the no-regression constraint; a bold lead on a body's first line, inline bold,
   > and soft-wrapped bold are NOT strays.
   > The empty-body check reads the model's `body_line_count`, which (v2) excludes the field
   > block — so an entry that carries only a ```` ```glossary ```` block and no prose still
   > flags as empty-bodied. A `see`-only entry must therefore carry a one-line pointer body.
5b. **Term heading is the canonical term only (v4).** A `TermBlock`'s heading text must not
   contain any of `(`, `)`, `*`, `/`, `:`, or `→` (U+2192). These are the decorations the
   pre-migration glossary carried inline — parenthetical qualifiers (`(the act)`,
   `(completability)`), inline aliases (`(alias: **instance**)`), co-defined slashes
   (`managed_by / **worker** / **assessor**`), and the arrow in `requirements→items LLM` —
   each of which made `github_slug(heading)` differ from the clean anchor every other doc
   links to. The fix is structural: the heading carries only the term; qualifiers and aliases
   move into the field block (rule 5c) or the body.
   `Load-bearing: this rule is what makes the heading slug equal the inbound link target, so
   gather_reference_terms resolves; it is the structural half of the glossary-anchor repair.`
5c. **Field-block validation (v4).** When a `TermBlock` has `field_block_present`:
   - an **unterminated** field block (`field_block_unterminated`, i.e. no closing fence before
     the section ends) is a violation reported **at the opening-fence line** — a specific
     diagnostic, not the misleading downstream "empty definition body" the swallowed section
     would otherwise produce;
   - every key in `fields` must be drawn from the allowed set `{aliases, short, confusable,
     reserved-for, see}` (an unknown key is a violation);
   - a `reserved-for` value must be one of `lacey` / `auditable-script`;
   - a `see` value must resolve to the **`github_slug` form** of a term defined under
     `## Definitions` (a dangling `see` is a violation).
   > **`see` takes the slug form, not the term form (authoring note).** Resolution is against
   > term *slugs*, so a multi-word target must be written hyphenated: `see: working-agent`,
   > **not** `see: working agent` (the latter reads as dangling). For a single-token term the
   > slug equals the term (`see: human_holds`). A `see` pointing at the entry's own slug is
   > not separately rejected (it resolves, since the set includes self) — harmless but
   > pointless; `see` is meant for co-defined siblings sharing one body (the
   > `worker`/`assessor` → `managed_by` case).
   The block's contents are otherwise free text the linter does not police (the semantic
   index is `contracts.15`).
6. **No duplicate term-heading slugs.** Each `TermBlock` carries `github_slug(term)`; a slug
   on more than one heading is flagged (GitHub would append `-1`/`-2`, breaking inbound
   anchors). The slug lives in ONE shared module (F1+F2) — no second copy to drift.
7. **Report and set exit code.** Collect ALL violations (not fail-fast), print in document
   order unless `--quiet`, print `OK:` when none, exit `1` if any else `0`; a read/decode
   failure short-circuits to exit `2`.
8. **Help (v5).** With `-h` or `--help` anywhere in argv, print the usage text to stdout and
   exit `0` without reading any file.
   `Load-bearing: the glossarian_install.sh --check self-test runs every installed shim as
   glossarian-check --help and expects exit 0.`

## Declared capability surface

- **Filesystem reads:** the single `glossary_path` (default `docs/glossary.md`). No others.
- **Filesystem writes / network / subprocess / environment / secrets / privilege:** None.

A reviewer should find a single `path.read_text(...)` and nothing else with side effects.
The non-stdlib imports are `glossarian.model` and (transitively) `glossarian.github_slug`,
both pure no-I/O modules.

## Assumptions for operation

- Python >= 3.14. Standard library only, plus `glossarian.model` / `glossarian.github_slug`
  (package imports — no `sys.path` bootstrap; `glossarian` is an installed/workspace
  package).
- UTF-8 file I/O; run so the default `docs/glossary.md` resolves (repo root, or pass a path).
- Front matter is the narrow `key: scalar` subset parsed by the model.

## Anti-patterns this script must not do

- Do **not** edit, rewrite, or "auto-fix" the glossary. Read-only validator; repair is the
  migration's job (`3.x`/`4.x`).
- Do **not** fail-fast; report all violations (rule 7).
- Do **not** re-implement parsing or the slug — consume `glossarian.model`. Re-inlining is
  exactly the drift the extraction removed.
- Do **not** import a YAML library.

## Revision rules

- Changing the required-section set, duplicate/order rules (rule 4), the term-heading level
  or relaxed-body shape (rule 5), the disallowed heading characters (rule 5b), or the allowed
  field-block keys / `reserved-for` values / `see`-resolution (rule 5c) is load-bearing: bump
  the version and re-check the migration plan.
- Parsing changes live in `glossarian.model`'s contract and ripple here.
- Adding any capability to the declared surface requires operator review.

## Revision history

- v5 — standalone-repo graduation: `-h`/`--help` prints usage and exits 0 (input + behavior
  8), so the PATH-shim installer's `--check` has a read-nothing invocation to run. No rule,
  output, or capability change. Test-run paths now relative to the repo root.
