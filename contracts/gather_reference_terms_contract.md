Contract version: v2

# gather_reference_terms — Inbound glossary-link resolver: Contract

Scan a documentation tree (default `docs/`) for inbound `glossary.md#<slug>` fragment
links, deduplicate the referenced slugs, build the set of anchors the glossary actually
exposes (the `github_slug` of every heading in `docs/glossary.md`, via the shared
`glossarian.model`), and **fail when a referenced slug resolves to no heading**. It is the
link-integrity half of the glossary-anchor repair — the complement of
`glossary_format_check` (which validates the glossary's own shape). It reports resolved and
unresolved references (as a text report or JSON) and sets an exit code; its only optional
write is a JSON report file — it never edits any documentation or glossary file.

> **v1 — ratified.** The contract was authored ahead of the script (checklist task `2.1`,
> as v0); the script (`2.2`) and its tests (`2.3`,
> `tests/test_gather_reference_terms.py`, all passing) are now built
> against it, so v0 → v1. First run-against-live-docs is `2.4`. The
> tool is built **in the `glossarian` package**, not the gitignored `scripts/docs/`, because
> it must compute heading anchors with the *same* parser and slug Sedric's runtime glossary
> tool (`contracts.15`) will use — so "this inbound link resolves" is decided by the same
> machinery that decides "this term is parseable by Sedric." Single-sourced via
> `glossarian.model` + `glossarian.github_slug`; no second parser, no second slug.
>
> **Grounded in task `1.1`** (`.assessments/1.1.summary.md`): the in-scope referrers are the
> non-archived `docs/` set (152 links / 49 distinct slugs across 11 docs as of the fork —
> `design.md`, `glossary-tool.md`, the three `diagrams/` docs, `state-tree.md`, `config.md`,
> `lacey-parity.md`, `decisions.md`, and `interfaces/{tag-grammar,tool-catalog}.md`); the one
> archived doc (`orchestrator-design-notes.md`, front matter `archived: true`) is excluded.
> The two known mismatch classes 1.1 surfaced — the arrow in `requirements→items LLM` and the
> live glossary's bold-paragraph (non-heading) terms — are exactly what this tool is meant to
> report as unresolved until the `3.x` migration lands.

## Inputs

- **Argv positional `docs_root`** — zero or one path; defaults to `docs/`. The directory
  tree scanned recursively for inbound glossary links. **Trust:** operator-provided. A
  missing/unreadable directory is exit 2.
- **`--glossary PATH`** — optional; defaults to `docs/glossary.md`. The glossary whose
  heading anchors define the valid target set. **Trust:** operator-provided. A
  missing/unreadable/undecodable glossary is exit 2.
- **`--quiet`** — suppress all stdout/stderr reporting; rely on the exit code. Overrides every
  other reporting flag (a `--json FILE` artifact is still written — see Outputs).
- **`--failures`** — *scope:* narrow the term listing to the failing (unresolved) terms only;
  the resolved-term listing is omitted (header and summary footer still print).
- **`--terms-only`** — *detail:* list only the term names, with no per-reference lines (for an
  agent linting its own work, when it already knows the definitions). Mutually exclusive with
  `--verbose`.
- **`--verbose [N]`** — *detail:* under each `file:line` reference, quote the surrounding
  source — `N` lines before and after the line(s) containing the reference, clamped at the
  file's first/last line, shown with 1-based line numbers inside a framed block. `N` is an
  optional non-negative integer **defaulting to 3**; `--verbose 0` quotes only the line(s)
  holding the reference, `--verbose 1` adds one line on each side. Mutually exclusive with
  `--terms-only`.
- **`--debug`** — emit debug trace lines to **stderr** (orthogonal to the reporting flags and
  to `--json`).
- **`-h` / `--help`** — print the usage text to stdout and exit 0 before any parsing,
  validation, or read (v2). Takes precedence over every other argument.
- **`--json [FILE]`** — emit the findings as JSON. Without an argument: pretty-printed JSON to
  stdout (in place of the text report). With an argument: a filesystem path that **must be in
  a writable directory and must not already exist** — the JSON is written there, **never
  overwriting**. **Trust:** operator-provided; a pre-existing path, or an unwritable/absent
  parent directory, is exit 2.
  > Reporting controls are two orthogonal dimensions: **scope** (`--failures` = unresolved
  > terms only; default = both resolved and unresolved) and **detail** (`--terms-only` = names
  > only · *default* = names + `file:line` references · `--verbose [N]` = references + `N`
  > lines of surrounding source). `--terms-only` and `--verbose` are the two ends of the
  > detail axis and are **mutually exclusive**; the dimensions otherwise compose
  > (`--failures --verbose 3`). `--quiet` overrides all of them. `--debug` and `--json`
  > compose with any combination.
- **The scanned `.md` files and the glossary file** — UTF-8 markdown. **Trust:** repository
  content, trusted-at-rest; read and parsed as text, never executed.

(No stdin. No environment inputs.)

## Outputs

Two sinks: a **human-readable text report** (stdout; errors and `--debug` traces to stderr)
and an optional **JSON findings document**. The exit code is the load-bearing signal; the
reports are for humans and downstream tooling. All output is deterministic (sorted).

### Human-readable text report

Emitted by default; **absent under `--quiet`**, and replaced by JSON under `--json` with no
FILE. Structure:

- **Header** — two lines: the directory being scanned and the path to the targeted glossary:

  ```
  Scanning: docs/
  Glossary: docs/glossary.md
  ```

- **Body** — two orthogonal dimensions:
  - *scope* — **default** lists each **resolved** and each **unresolved** term (grouped,
    sorted); **`--failures`** lists only the unresolved terms.
  - *detail* — **`--terms-only`** prints just the term names; **default** prints each term
    followed by its sorted referencing `file:line` lines; **`--verbose [N]`** prints, beneath
    each `file:line` reference, the surrounding source lines (`N` before/after, clamped at the
    file boundaries) quoted with their line numbers inside a framed block, with a blank line
    between references.
  - the dimensions compose (`--failures --verbose 3` = unresolved terms with 3 lines of
    context per reference); `--terms-only` and `--verbose` cannot be combined.
- **Footer** — a summary line with the count of files scanned and the **number** of resolved
  and unresolved terms, followed by a final line of exactly `OK` (no unresolved) or `FAILED`
  (one or more unresolved).
- **Exit reason** — outside `--quiet`, every non-zero exit states why: the `FAILED` footer
  (exit 1) names the unresolved count; a path or `--json`-target failure (exit 2) prints the
  offending path and the failure mode to stderr.

Worked examples (two failing terms):

```
# --failures --terms-only          # --failures
Scanning: docs/                     Scanning: docs/
Glossary: docs/glossary.md          Glossary: docs/glossary.md

Unresolved (2):                     Unresolved (2):
  requirements-items-llm              requirements-items-llm
  human-holds                           docs/design.md:412
                                        docs/design.md:588
Files scanned: 11 | Terms ...           docs/state-tree.md:77
  resolved: 47 | unresolved: 2        human-holds
FAILED                                  docs/config.md:23

                                    Files scanned: 11 | Terms ...
                                      resolved: 47 | unresolved: 2
                                    FAILED
```

```
# --failures --verbose   (N defaults to 3; framed block per reference, line-numbered)
Scanning: docs/
Glossary: docs/glossary.md

Unresolved (2):
  requirements-items-llm
    docs/design.md:412
    --------------------------
    <source lines 409-415, with line numbers>
    --------------------------

    docs/design.md:588
    --------------------------
    <source lines 585-591, with line numbers>
    --------------------------

    docs/state-tree.md:77
    --------------------------
    <source lines 74-80, with line numbers>
    --------------------------

  human-holds
    docs/config.md:23
    --------------------------
    <source lines 20-26, with line numbers>
    --------------------------

Files scanned: 11 | Terms resolved: 47 | Terms unresolved: 2
FAILED
```

### JSON findings (`--json`)

- **No argument:** the complete findings as pretty-printed JSON on **stdout**, replacing the
  text report. Verbosity flags do not shape the JSON — it always carries the full findings.
- **`FILE` argument:** the same JSON written to `FILE`; stdout still carries the text report
  (header + footer per verbosity) unless `--quiet`.
- **Shape** (independent of the `--failures`/`--terms-only`/`--verbose` flags — the JSON
  always carries the complete findings):
  - `docs_root`, `glossary` — the resolved paths scanned.
  - `files_scanned` — count; `files` — the sorted list of scanned (non-archived) files.
  - `terms` — a sorted map `slug -> { resolved: bool, reference_count: int, references:
    [{ file, line }] }`.
  - `summary` — `{ files_scanned, terms_total, resolved, unresolved, result: "OK"|"FAILED" }`.
  `Load-bearing: this shape is the machine contract for any JSON consumer (the checklist's
  evidence capture at 2.4/5.1, CI). It does NOT embed the --verbose source-context lines
  (a text-report-only aid). Field renames or removals are load-bearing changes.`

### Exit codes

`0` every referenced slug resolves · `1` read OK but one or more referenced slugs resolve to
no glossary heading · `2` `docs_root`/`--glossary` path missing/unreadable/undecodable, a
`--json FILE` that already exists or whose parent directory is not writable, or a usage error
(`--verbose` with `--terms-only`, or an invalid `--verbose N`).
`Load-bearing: callers (the tests, and the checklist's run/validation steps 2.4 and 5.1) gate
on the exit code, not the prose. Exit 0 == "every inbound glossary.md#slug link in the
non-archived docs lands on a real heading anchor."`

### File output

At most the single `--json FILE` artifact, and only when that path does not already exist.
Never writes, creates, or edits any documentation or glossary file (that repair is the
migration's job — tasks `3.x`/`4.1`).

## Behaviors

Anything not listed here is undeclared drift.

1. **Discover the scan set.** Recurse `docs_root` for `*.md` files. For each, read its front
   matter via `glossarian.model.parse(text).frontmatter` and **skip any file whose front
   matter has `archived: true`.** Process the remaining files in a deterministic (sorted)
   order.
   `Load-bearing: exclusion keys off the durable, machine-checkable front-matter flag, NOT a
   hand-maintained path list (task 1.1 §2) — so it generalizes as more docs are archived,
   matching the repo's "retire = archive in place" pattern. The lone archived doc today is
   docs/orchestrator-design-notes.md.`

2. **Extract inbound glossary references.** In each scanned file, find every link target
   whose path component's basename is `glossary.md` immediately followed by `#<fragment>`,
   capturing the fragment and its 1-based source line. Accept the bare form
   (`glossary.md#slug`), relative forms (`./glossary.md#…`, `../glossary.md#…`), and
   path-prefixed forms (`docs/glossary.md#…`, used by the `diagrams/` subdir docs). The
   fragment is captured up to the first link-terminating character. Deduplicate into a map of
   `slug -> sorted set of "file:line"` references.
   `Load-bearing: task 2.3 fixtures cover direct links, relative links, duplicate references,
   underscore slugs, and hyphenated slugs.`

3. **Build the valid anchor set from the live glossary.** Parse `--glossary` with
   `glossarian.model.parse` and compute `glossarian.github_slug(heading_text)` for **every
   ATX heading in the model's fence-aware body, at every level** — the exact set of fragment
   anchors GitHub auto-generates for that file. Term definitions (the `###` headings under
   `## Definitions` the migration creates) are part of this set; so are `# Glossary`,
   `## Governance`, etc.
   `Load-bearing: the slug is the shared github_slug (one definition, no drift) so a slug in
   this set equals GitHub's real anchor; underscores are preserved (human_holds, managed_by),
   spaces become hyphens, and the General/Supplemental Punctuation blocks are stripped — all
   delegated to github_slug, never re-implemented here.`

4. **Resolve each referenced slug against the anchor set.** A distinct referenced fragment
   *resolves* iff it is a member of the anchor set (literal comparison; GitHub anchors are
   already lowercased by `github_slug`). Collect **all** slugs that do not resolve — never
   fail-fast — together with their referencing `file:line` list.
   `Load-bearing: this is GitHub-fidelity resolution, so a fragment an author wrote that
   github_slug would not emit for any heading (e.g. the inbound requirements-items-llm vs the
   heading slug requirements→items-llm, or any link into the pre-migration bold-paragraph
   glossary) is correctly reported as unresolved — that failing output is the evidence task
   2.4 preserves before the migration.`

5. **Validate flags and the output target up front.** `-h`/`--help` anywhere in argv
   short-circuits first: usage to stdout, exit `0`, nothing read (v2;
   `Load-bearing: glossarian_install.sh --check runs glossarian-gather --help and expects
   exit 0`). Otherwise reject `--verbose` together with
   `--terms-only`, and a negative/non-integer `--verbose N`, as usage errors (exit 2). When
   `--json FILE` is given, confirm the parent directory is writable and `FILE` does **not**
   already exist **before scanning**, so a bad target fails fast (exit 2) without doing or
   partially emitting work.
   `Load-bearing: the no-overwrite guarantee is checked here; task 2.3 tests that a
   pre-existing --json target exits 2 and is never clobbered.`

6. **Render the report.** Emit the text report on stdout per the **scope** (`--failures` vs
   both) and **detail** (`--terms-only` / default `file:line` / `--verbose [N]`) selections —
   header (two lines), body, footer (file count, resolved/unresolved term counts, `OK`/`FAILED`)
   — OR, under `--json` with no FILE, the JSON findings on stdout instead. Nothing prints under
   `--quiet`. Under `--verbose [N]`, each reference is annotated with the source lines from `N`
   before to `N` after the line(s) holding the reference, **clamped** to the file's first/last
   line, quoted with 1-based line numbers inside a framed block; `N` defaults to 3, and
   `--verbose 0` quotes only the reference's own line(s). The findings themselves are built
   from the same resolved/unresolved term maps regardless of mode.
   `Load-bearing: task 2.3 covers the context-window math — N=0, N=1, the default N=3, clamping
   at the file's start and end, and a reference spanning two physical lines.`

7. **Write the JSON artifact when `--json FILE` is given.** Write the findings JSON to the
   pre-validated `FILE` (the sole filesystem write); the text report still goes to stdout
   unless `--quiet`. The file is created, never overwritten.

8. **Set the exit code, with a reason.** Exit `1` if any referenced slug is unresolved, else
   `0`; a read/decode failure of `docs_root` or the glossary, a bad `--json` target, or a
   usage error (`--verbose` with `--terms-only`, or an invalid `--verbose N`) short-circuits
   to exit `2`. Outside `--quiet`, a non-zero exit always prints its reason (the `FAILED`
   footer for exit 1; the offending path/flag and failure mode to stderr for exit 2).

9. **Debug tracing.** Under `--debug`, emit trace lines (files visited, references found,
   resolution decisions) to **stderr**, so stdout and any JSON stay clean. Off by default.

## Declared capability surface

- **Filesystem reads:** the `*.md` files under `docs_root` (default `docs/`) and the
  `--glossary` file (default `docs/glossary.md`). No reads outside `docs_root` and the
  glossary path. The `--verbose` source context is sliced from the file contents already read
  for reference extraction — no re-read or read elsewhere.
- **Filesystem writes:** at most the single `--json FILE` target, and only when it does
  **not** already exist (no overwrite/truncation) and its parent directory is writable. No
  writes when `--json FILE` is absent. In particular, no documentation or glossary file is
  ever modified.
- **Network access:** None.
- **Subprocess invocation:** None.
- **Environment variables read:** None.
- **Secrets handled:** None.
- **Privilege escalation:** None.

A reviewer should find directory traversal under `docs_root`, `path.read_text(...)` reads, a
**single guarded write** to the existence-checked `--json FILE` path (and `stderr` for
`--debug`/errors), and nothing else with side effects. The non-stdlib imports are
`glossarian.model` and `glossarian.github_slug` (both pure, no-I/O modules); the front-matter
read in behavior 1 reuses `glossarian.model.parse` rather than a second front-matter parser.

## Assumptions for operation

- Python >= 3.14. Standard library only, plus `glossarian.model` / `glossarian.github_slug`
  (package imports — no `sys.path` bootstrap; `glossarian` is an installed/workspace package).
- UTF-8 file I/O; run so the default `docs/` and `docs/glossary.md` resolve (repo root, or
  pass explicit paths).
- **One glossary in the repository.** A reference is "to the glossary" by **basename**
  (`glossary.md`) — the relative path is not resolved to prove it targets *this* file. This
  holds while there is a single `glossary.md`; revisit if a second one appears.
- Front matter is the narrow `key: scalar` subset parsed by `glossarian.model`.
- The console-script wiring (an entry point alongside `glossarian-check` in
  `glossarian.cli`) is added when the script is implemented (`2.2`).

## Anti-patterns this script must not do

- Do **not** edit, rewrite, or "auto-fix" any doc or the glossary. The only write the script
  may perform is creating the explicit `--json FILE` report.
- Do **not** overwrite or truncate an existing file for `--json FILE`; a pre-existing target
  is exit 2, never a clobber. Do not write findings anywhere except that explicit path.
- Do **not** fail-fast; collect and report **all** unresolved slugs (behavior 4–5), so one
  run is a complete worklist for `4.1`.
- Do **not** re-implement the slug, the heading scan, or the front-matter parse — consume
  `glossarian.github_slug` and `glossarian.model`. Re-inlining is exactly the drift the
  package extraction removed (the F1/F2 trap, one level down).
- Do **not** import a YAML library.
- Do **not** resolve against a hand-maintained list of expected terms; the valid anchor set
  is derived from the **live** glossary's headings every run, so the tool tracks the glossary
  as it migrates.
- Do **not** treat an **unreferenced** glossary heading (a term no doc links to) as an error.
  The check is one-directional — inbound link → must hit a heading. Orphan-heading reporting
  is out of scope for this contract.

> **Flags for the migration plan (`1.3`/`3.x`) — surfaced, not silently resolved:**
> - **Anchor set = all headings, not Definitions terms only.** Chosen for GitHub fidelity (a
>   legitimate `glossary.md#governance` link should resolve). Task 1.1 found all 49 live
>   inbound slugs are term slugs, so in practice this only widens the valid set; if the
>   migration wants link targets restricted to `## Definitions` terms, this behavior (3) is
>   amended and the version bumped.
> - **Until `3.x` lands, this tool is expected to exit `1`** against the live docs: the
>   current glossary's terms are bold paragraphs, not headings, so almost no term link
>   resolves. That failing run is the `2.4` evidence, not a tool defect — symmetric to
>   `glossary_format_check` being expected to exit `1` on the pre-migration glossary.

## Revision rules

- Changing the anchor set (behavior 3 — all-headings vs Definitions-only), the accepted link
  forms (behavior 2), or the archived-exclusion key (behavior 1) is load-bearing: bump the
  version and re-check the migration plan and the `2.3` fixtures.
- Changing the JSON findings shape (field names/structure) or the set/semantics of the
  output flags (`--quiet`/`--failures`/`--terms-only`/`--verbose`/`--debug`/`--json`),
  including the `--verbose` context-window rules, is load-bearing: bump the version and
  re-check JSON consumers and the `2.3` fixtures.
- Slug or structural-parse changes live in `glossarian.github_slug` / `glossarian.model`'s
  contracts and ripple here; this script never owns them.
- Adding any capability to the declared surface (a write, a network call, a subprocess, an
  env read) requires operator review.
- The script's file header references the contract version it was built against; v0 became
  v1 once the `2.2` implementation and `2.3` tests passed against it. Subsequent changes
  that touch an input, output, load-bearing behavior, capability, or assumption bump to v2+.

## Revision history

- v2 — standalone-repo graduation: `-h`/`--help` prints usage and exits 0 (input; behavior
  5 short-circuit), so the PATH-shim installer's `--check` has a read-nothing invocation to
  run. No link-form, anchor-set, JSON-shape, or capability change. Test path now relative to
  the repo root.
