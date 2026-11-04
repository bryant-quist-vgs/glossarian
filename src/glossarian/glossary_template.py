#!/usr/bin/env python3
"""glossary_template — write a blank, fully compliant glossary to a new file.

`glossarian-template PATH [--governs REL]` creates PATH (which must not exist) holding the
canonical glossary skeleton: front matter, `# Glossary`, the five required sections in
order, a `## Governance` field block with a `governs:` scope, one placeholder term under
`## Definitions`, and the Confusable Pairs / Renames / Reserved Targets tables. The result
passes `glossarian-check` as written, so authoring starts from a green file.

`governs` defaults to the repository root relative to PATH's directory (`../` for
`docs/glossary.md`), found by walking up for `.git`; outside a repository it defaults to
`.`. The single write is refused when PATH already exists (exit 2) — the tool never
overwrites.

Built against contract v1.
Companion contract: contracts/glossary_template_contract.md
Tests:              tests/test_glossary_template.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from glossarian import scope

USAGE = """\
Usage: glossarian-template PATH [--governs REL] [--quiet]
       glossarian-template -h | --help

Write a blank, glossarian-compliant glossary to PATH. PATH must not exist; its parent
directory must. The file passes `glossarian-check` as written.

Options:
  --governs REL  the directory the glossary governs, relative to PATH's directory
                 (default: the repository root, e.g. `../` for docs/glossary.md; `.` when
                 no `.git` is found above PATH)
  --quiet        print nothing; rely on the exit code
  -h, --help     show this help and exit 0

Exit codes: 0 written, 2 PATH exists / parent missing / bad usage."""

PLACEHOLDER_TERM = "placeholder term"


def default_governs(target: Path) -> str:
    """The repository root relative to `target`'s directory, or `.` when none is found."""
    base = target.resolve().parent
    root = scope.find_repo_root(base)
    if root is None:
        return "."
    rel = os.path.relpath(root, base)
    return "." if rel == "." else rel.replace(os.sep, "/") + "/"


def render(governs: str) -> str:
    """The template text for a glossary governing `governs` (a path relative to its directory)."""
    return f"""\
---
id: glossary
is_source_of_truth: true
---

# Glossary

Canonical vocabulary for this project. Other documents link here; they do not redefine
terms. Each `###` entry under Definitions is one term; link to it by this file's relative
path plus `#` and the term's slug.

## Governance

```glossary
governs: {governs}
```

This glossary governs every document under `{governs}` (relative to this file). Terms are
added, renamed, and retired by pull request. A renamed term keeps a row in the renames table
for one release.

## Definitions

### {PLACEHOLDER_TERM}
Replace this entry with the first real term. Keep the heading to the canonical term only,
put aliases and cross-references in a ```glossary field block, and leave a blank line
before the next `###` heading.

## Confusable Pairs

| Term | Confusable with | Distinction |
|---|---|---|

## Renames and deprecated terms

| Avoid | Use | Why |
|---|---|---|

## Reserved Targets

| Target | What it is | Local | Remote |
|---|---|---|---|
"""


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv or not argv:
        print(USAGE)
        return 0 if argv else 2
    quiet = "--quiet" in argv
    governs: str | None = None
    positional: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--quiet":
            pass
        elif tok == "--governs" or tok.startswith("--governs="):
            if "=" in tok:
                governs = tok.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    _err(quiet, "--governs requires a path argument")
                    return 2
                governs = argv[i]
        elif tok.startswith("--"):
            _err(quiet, f"unknown option: {tok}")
            return 2
        else:
            positional.append(tok)
        i += 1
    if len(positional) != 1:
        _err(quiet, "exactly one PATH is required")
        return 2
    target = Path(positional[0])
    if target.exists() or target.is_symlink():
        _err(quiet, f"refusing to overwrite: {target} already exists")
        return 2
    if not target.parent.is_dir():
        _err(quiet, f"parent directory does not exist: {target.parent}")
        return 2
    if governs is None:
        governs = default_governs(target)
    else:
        reason = scope.check_governs_syntax(governs)
        if reason is not None:
            _err(quiet, reason)
            return 2
    try:
        with target.open("x", encoding="utf-8") as fh:
            fh.write(render(governs))
    except OSError as exc:
        _err(quiet, f"cannot write {target}: {exc}")
        return 2
    if not quiet:
        print(f"wrote {target} (governs: {governs})")
    return 0


def _err(quiet: bool, msg: str) -> None:
    if not quiet:
        print(f"error: {msg}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
