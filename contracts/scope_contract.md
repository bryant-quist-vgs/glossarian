Contract version: v1

# scope — Governed-scope resolution: Contract

`glossarian.scope` turns a glossary's `governs:` declaration (the field block under
`## Governance`, model contract v3) into a resolved directory and enforces the two safety
rules every consumer relies on: **a scope never extends above the repository root**, and **a
glossary lives inside the scope it governs**. `glossary_format_check` calls it to validate
the field (rule 4b); `gather_reference_terms` calls it to decide whether a linking document
is governed by the glossary it links to. One definition, shared, so "this `governs` is
valid" and "this file is governed" can never drift apart.

> **Why a shared module.** The 2026-11-04 round added multi-glossary repositories (a tooling
> glossary and a knowledge-base glossary side by side). The value is *potentially dangerous*
> — a glossary that governs `../../../` would claim documents outside its repository — so
> the containment check is written once, with the repository root as the hard ceiling.

## Inputs

- **`glossary_path: Path`** — the glossary file. Resolved (symlinks followed) before use; only
  its parent directory matters. **Trust:** operator/caller-provided.
- **`governs: str`** — the raw field value. **Trust:** repository content, untrusted; it is
  string-checked before it touches the filesystem.
- **`repo_root: Path | None`** — an explicit ceiling. When `None`, the nearest ancestor-or-self
  of the glossary's directory containing `.git` (a directory **or** a file, so worktrees
  count) is used.

## Outputs

- `check_governs_syntax(value) -> str | None` — a reason string when the raw value is
  malformed, else `None`. Pure; no filesystem.
- `find_repo_root(start) -> Path | None` — the resolved repository root, or `None`.
- `resolve_scope(glossary_path, governs, repo_root=None) -> Path` — the resolved scope
  directory, or raises **`ScopeError`** whose `str()` is a human-readable reason.
- `governs_path(scope, path) -> bool` — containment on resolved paths.
- `GOVERNS_KEY = "governs"` — the field name, so the linter and the parser agree.

## Behaviors

1. **Syntax.** Reject an empty value, a home-relative value (`~…`), a URL (`://`), an
   absolute path (POSIX `/…` or a Windows drive prefix `X:`), a backslash separator, or a
   NUL byte. Everything else is a relative path candidate. `Load-bearing: this runs before
   any path is resolved, so a hostile value never reaches the filesystem.`
2. **Resolution.** `scope = (glossary_dir / governs).resolve()`. It must be an existing
   directory.
3. **Ceiling.** The repository root is `repo_root` (resolved) when given, else behavior 4's
   search; **no root is an error**, never a silent pass. The scope must be the root or inside
   it. `Load-bearing: "no glossary governs above its repository root."`
4. **Root search.** Walk from the glossary's resolved directory upward; the first directory
   containing `.git` wins.
5. **Self-containment.** The glossary's own directory must be inside the scope (the scope is
   `.`, `../`, `../../`, … relative to the glossary, never a sibling). A glossary that does not
   govern itself cannot resolve its own self-links, so it is rejected.
6. **Containment query.** `governs_path` compares resolved paths with `is_relative_to`.

Anything not listed is undeclared drift.

## Declared capability surface

- **Filesystem reads:** `Path.resolve()`, `is_dir()`, and `.git` existence checks on the
  glossary's ancestors and the candidate scope. No file contents are read.
- **Writes / network / subprocess / environment / secrets:** None.

## Assumptions for operation

- Python >= 3.14, standard library only (`re`, `pathlib`).
- A repository is identified by a `.git` entry; nested repositories bound to the nearest.

## Anti-patterns this module must not do

- Do **not** treat a missing repository root as "unbounded"; fail closed.
- Do **not** compare unresolved paths (symlinked docs directories must resolve first).
- Do **not** accept a sibling scope that excludes the glossary.

## Revision history

- v1 — created for the governs/scope feature (2026-11-04), extracted as a shared module so
  the linter and the link resolver use one containment rule.
