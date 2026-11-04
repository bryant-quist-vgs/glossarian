Contract version: v6

# glossary_format_check — Glossary structure validator: Contract

> **v6 — governed scope, open reserved targets, fix hints (2026-11-04).** (1) **Rule 4b
> (new):** `## Governance` must open with a ```` ```glossary ```` field block declaring
> `governs: <path>`, the directory this glossary governs relative to its own; the value is
> syntax-checked always and, when the file's path is known, resolved by `glossarian.scope`
> (exists, does not escape the repository root, contains the glossary). (2) **Rule 4:**
> `## Reserved Targets` is the **fifth** required section. (3) **Rule 5c:** the closed
> `reserved-for ∈ {lacey, auditable-script}` list is gone; `reserved-for-target` joins the
> allowed keys. (4) **Rule 5d (new):** a `reserved-for` value (comma-separated slugs) must
> name a term whose block declares `reserved-for-target: true`; every such target must have a
> row under `## Reserved Targets` and every row must name a target. (5) **Rule 7:** every
> violation carries a stable `code`; the ones `glossarian-fix` can repair carry a `fix`
> description, and the report prints the hint and command. New input `--repo-root`.

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
- **`--repo-root DIR`** (v6) — the repository root the `governs` scope may not escape;
  default is the nearest ancestor of the glossary containing `.git`. Missing argument or an
  unknown option is a usage error (exit 2).
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
4. **The five required `##` sections present, named verbatim, exactly once, in canonical
   order:** `## Governance`, `## Definitions`, `## Confusable Pairs`, `## Renames and
   deprecated terms`, `## Reserved Targets` (v6). A missing/mis-cased section names which
   one (v6: a case-only mismatch is reported as `section-case` with a fix; a missing
   Confusable Pairs / Renames / Reserved Targets section as `section-missing` with an
   append-placeholder fix); a **duplicate** required
   section is a separate violation (F3); out-of-order is "malformed section order".
   **Additional `##` sections are permitted** and ignored by the order/duplicate checks.
   > **Flag for 3.1/3.2:** the live doc uses `## Confusable pairs` (lowercase p) and carries
   > `## Reserved for sister projects` (not in the required set). The migration renames the
   > live heading to match, or this contract is amended. Surfaced, not silently resolved.
4b. **Governance declares a safe scope (v6).** When `## Governance` exists, its leading
   field block (model v3 `governance`) must be present (`governance-block-missing`),
   terminated (`governance-unterminated`), use only the key `governs`
   (`governance-key-unknown`), and declare `governs` (`governs-missing`). The value is checked
   with `scope.check_governs_syntax` always (`governs-invalid`: empty, absolute, `~`, URL,
   backslash) and, when `validate(..., glossary_path=…)` is given a path (as `main` always
   does), resolved with `scope.resolve_scope(glossary_path, governs, repo_root)` — a missing
   directory, no repository root, a scope above the root, or a scope that excludes the
   glossary's directory is `governs-invalid` with the `ScopeError` reason.
   `Load-bearing: "no glossary extends its governance above a repository root" is enforced
   here and in gather_reference_terms through the same scope module.`
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
     reserved-for, see, reserved-for-target}` (an unknown key is a violation);
   - a `reserved-for-target` value must be `true` or `false` (v6);
   - a `reserved-for` value is **open** (v6): each comma-separated item must be the slug of a
     reserved target (rule 5d); otherwise `field-reserved-for-unresolved`, with a fix offered
     when the item's `github_slug` is a reserved target;
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
5d. **Reserved targets (v6).** A *reserved target* is a `###` term whose field block declares
   `reserved-for-target: true` — a tool, convention, policy, repository, or anything a term
   may be reserved for. When `## Reserved Targets` exists, each target must have a row in its
   table whose first cell names it (a `#<slug>` link, or plain/backticked/bold text whose
   `github_slug` is the target's slug) — `reserved-target-no-row` at the section heading —
   and each row must name a target — `reserved-row-unknown` at the row. With no targets the
   section may hold a header-only table or prose such as `None.`
   `Load-bearing: this is what makes every reserved-for value a glossary link that resolves —
   the target is a defined term, so docs can link glossary.md#<target>.`
6. **No duplicate term-heading slugs.** Each `TermBlock` carries `github_slug(term)`; a slug
   on more than one heading is flagged (GitHub would append `-1`/`-2`, breaking inbound
   anchors). The slug lives in ONE shared module (F1+F2) — no second copy to drift.
7. **Report and set exit code.** Collect ALL violations (not fail-fast), print in document
   order unless `--quiet`, print `OK:` when none, exit `1` if any else `0`; a read/decode
   failure short-circuits to exit `2`. (v6) Every `Violation` carries a stable `code`
   (`frontmatter-id`, `h1-text`, `section-missing`, `section-case`, `governs-invalid`,
   `term-no-blank-before-heading`, `field-see-unresolved`, …) and, when `glossarian-fix` can
   repair it, a `fix` description; the report prints `  fixable: \`glossarian-fix PATH\` would
   <fix>` under such a violation (and under the `is_source_of_truth` warning) and ends with
   `N issue(s) can be repaired automatically: run \`glossarian-fix PATH\``. Fixable today:
   `section-case`, `section-missing` (placeholder sections only), `term-no-blank-before-heading`,
   `field-see-unresolved` / `field-reserved-for-unresolved` (term written instead of slug),
   and the warning. The fix descriptions are the contract `glossary_fix` implements.
8. **Help (v5).** With `-h` or `--help` anywhere in argv, print the usage text to stdout and
   exit `0` without reading any file.
   `Load-bearing: the glossarian_install.sh --check self-test runs every installed shim as
   glossarian-check --help and expects exit 0.`

## Declared capability surface

- **Filesystem reads:** the single `glossary_path` (default `docs/glossary.md`), plus (v6)
  the `is_dir`/`resolve`/`.git`-existence probes of `glossarian.scope` on the glossary's
  ancestors and the `governs` directory. No file contents other than the glossary.
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

- v6 — governed scope (rule 4b, `--repo-root`), fifth required section, open reserved
  targets (rules 5c/5d), violation codes and fix hints (rule 7), 2026-11-04. The
  `validate()` signature gains keyword-only `glossary_path` / `repo_root`; the three-tuple
  return is unchanged.
- v5 — standalone-repo graduation: `-h`/`--help` prints usage and exits 0 (input + behavior
  8), so the PATH-shim installer's `--check` has a read-nothing invocation to run. No rule,
  output, or capability change. Test-run paths now relative to the repo root.
