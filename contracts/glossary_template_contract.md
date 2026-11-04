Contract version: v1

# glossary_template — Blank compliant glossary generator: Contract

`glossarian-template PATH [--governs REL] [--quiet]` writes a blank, fully compliant glossary
to a **new** file: front matter, `# Glossary`, the five required sections in canonical order,
a `## Governance` field block declaring `governs:`, one placeholder term, and the three
tables. The file passes `glossarian-check` as written, so authoring starts green. The single
write is refused when PATH already exists.

## Inputs

- **Argv positional `PATH`** — exactly one; the file to create. Its parent directory must
  exist. **Trust:** operator-provided.
- **`--governs REL`** — the scope to declare, relative to PATH's directory. Syntax-checked by
  `glossarian.scope.check_governs_syntax` (not resolved: the directory may be created later).
  Default: the repository root relative to PATH's directory (`../` for `docs/glossary.md`,
  `.` at the root), found by `scope.find_repo_root`; `.` when no `.git` is found.
- **`--quiet`**, **`-h` / `--help`** — as for the other tools.

## Outputs

- **The file at PATH**, UTF-8, created with `open(..., "x")` (fails if it appears between
  the check and the write). Its content is `render(governs)`.
- **stdout:** `wrote PATH (governs: REL)`. **stderr:** `error: …` on exit 2.
- **Exit codes:** `0` written · `2` PATH exists (file, directory, or symlink), parent
  missing, malformed `--governs`, no/too many positionals, unknown option, or no arguments.
  (No exit 1: there is no "checked but failed" state.)

## Behaviors

1. **Green as written.** `render(governs)` produces a document that `glossary_format_check`
   accepts: required sections, a well-formed Governance block, one entry under Definitions
   (`placeholder term`) with a body telling the author to replace it, header-only tables.
   `Load-bearing: tests run glossarian-check on the written file and require exit 0.`
2. **Never overwrite.** Refuse any existing PATH (including a symlink or directory) before
   writing; exit 2; nothing touched.
3. **Default scope = repository root.** Computed relative to PATH's directory with
   `os.path.relpath`, normalised to `/` separators and a trailing `/` (`../`, `../../`).
4. **No literal link pattern in the prose.** The template text never contains the sequence
   `glossary.md#`, so a template placed under a docs tree adds no references for
   `glossarian-gather` to resolve.

## Declared capability surface

- **Filesystem:** the one `open("x")` write at PATH; `exists`/`is_symlink`/`is_dir` checks
  on PATH and its parent; the `.git` search of `glossarian.scope`.
- **Network / subprocess / environment / secrets:** None.

## Revision history

- v1 — created 2026-11-04.
