Contract version: v1

# glossary_fix — Trivial-issue repairer: Contract

`glossarian-fix GLOSSARY_PATH [--repo-root DIR] [--dry-run] [--quiet]` applies the repairs
that `glossary_format_check` marks as fixable (`Violation.fix`), re-validates, and reports
what changed and what still fails. It is the **only** glossarian tool that edits a glossary,
and it edits exactly one file, in place, atomically, only when a repair applies.

> **Division of labour.** The linter decides *what* is fixable and describes the change (so
> `glossarian-check` can print the hint and the command); this module performs it. Adding a
> repair means adding a `fix` description to the linter rule **and** an `apply` branch here.

## Inputs

- **Argv positional `GLOSSARY_PATH`** — exactly one. **Trust:** operator-provided.
- **`--repo-root DIR`** — passed to the check (bounds the `governs` scope).
- **`--dry-run`** — plan and print; write nothing.
- **`--quiet`**, **`-h` / `--help`** — as for the other tools.
- **The glossary text** — UTF-8. **Trust:** repository content; parsed, never executed.

## Outputs

- **The rewritten glossary** at GLOSSARY_PATH (not under `--dry-run`, not when nothing is
  repairable): written to a temp file in the same directory, then `os.replace`d, so a crash
  leaves either the old or the new file, never a partial one, and no temp file.
- **stdout:** one line per repair (`PATH:LINE: <description>` or `PATH: <description>`,
  prefixed `would ` under `--dry-run`), sorted by line; a count line (`N repairs applied` /
  `… planned (dry run, nothing written)` / `nothing to repair`); one `still failing: …` line
  per remaining violation; `OK: PATH` when none remain.
- **Exit codes:** `0` valid after the run (the dry-run answer is "would be valid") · `1`
  violations remain · `2` path missing/unreadable/unwritable, bad usage.

## Behaviors

1. **The repair set** (each keyed by the linter's violation `code`):
   - `term-no-blank-before-heading` — insert one blank line before the reported heading.
   - `section-case` — rewrite the mis-cased required `##` heading to its canonical text.
   - `section-missing` — for `Confusable Pairs`, `Renames and deprecated terms`, `Reserved
     Targets` only (`SECTION_STUBS`): insert `## <name>` + placeholder body before the first
     later required section that is present, else at end of file. Governance and
     Definitions are never stubbed.
   - `field-see-unresolved` / `field-reserved-for-unresolved` — when the linter offered a
     slug (the value's `github_slug` resolves), rewrite the value in place.
   - the `is_source_of_truth` warning — insert `is_source_of_truth: true` after the `id:`
     line of a well-formed front matter (or correct an existing non-true value).
2. **Order preserves line numbers.** Per pass: line-anchored repairs bottom-up, then section
   insertions, then the front-matter insertion. `Load-bearing: a repair applied at a stale
   line number corrupts the file; the test suite pins a case where all three kinds coexist.`
3. **Bounded passes.** Up to 3 validate→repair passes (a repair may expose the next fixable
   issue); stops early when a pass changes nothing.
4. **Idempotent.** A second run on the output reports `nothing to repair`, exit 0, and the
   file is byte-identical.
5. **Leaves the rest.** Non-fixable violations are reported as `still failing` and the file
   content around them is untouched.

## Declared capability surface

- **Filesystem:** read GLOSSARY_PATH; write one temp file in its directory and rename it over
  GLOSSARY_PATH (not under `--dry-run`); the `.git` search of `glossarian.scope` via the
  check.
- **Network / subprocess / environment / secrets:** None.

## Anti-patterns this script must not do

- Do **not** guess content: never stub Governance or Definitions, never invent a `governs`,
  never demote/promote heading levels, never reorder sections.
- Do **not** touch any file other than GLOSSARY_PATH.
- Do **not** write when `--dry-run` or when no repair applies.

## Revision history

- v1 — created 2026-11-04.
