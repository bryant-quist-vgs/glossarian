"""scope — the governed scope of a glossary, shared across glossarian.

A glossary declares the directory it governs with a `governs:` field in the field block under
`## Governance` (model contract v3). The value is a path **relative to the glossary's own
directory** (`../` for `docs/glossary.md` governing the whole repository). This module turns
that declaration into a resolved directory and enforces the two safety rules every consumer
relies on:

  1. a scope never extends above the repository root (the nearest ancestor holding `.git`,
     or an explicit `repo_root`), and
  2. a glossary lives inside the scope it governs (the scope is an ancestor-or-self of the
     glossary's directory).

`glossary_format_check` uses it to validate the field; `gather_reference_terms` uses it to
decide whether a linking document is governed by the glossary it links to. One definition,
no drift.

Built against contract v1.
Companion contract: contracts/scope_contract.md
Tests:              tests/test_scope.py
"""

from __future__ import annotations

import re
from pathlib import Path

GOVERNS_KEY = "governs"
_DRIVE_RE = re.compile(r"^[A-Za-z]:")  # a Windows drive prefix is absolute on any platform


class ScopeError(ValueError):
    """A `governs` value that is malformed or violates a safety rule. `str(exc)` is the reason."""


def find_repo_root(start: Path) -> Path | None:
    """Nearest ancestor-or-self of `start` (resolved) containing `.git` (dir or file), else None."""
    here = start.resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def check_governs_syntax(value: str) -> str | None:
    """Return a reason the raw `governs` value is malformed, or None when it is syntactically fine.

    Pure string check (no filesystem). Rejects empty values, absolute paths, home-relative
    paths, and anything that looks like a URL. Containment is checked by `resolve_scope`.
    """
    v = value.strip()
    if not v:
        return "`governs` must not be empty (use `.` for the glossary's own directory)"
    if v.startswith("~"):
        return f"`governs` must be relative to the glossary's directory, not home-relative ({v!r})"
    if "://" in v:
        return f"`governs` must be a filesystem path, not a URL ({v!r})"
    if Path(v).is_absolute() or v.startswith("/") or _DRIVE_RE.match(v):
        return f"`governs` must be relative to the glossary's directory, not absolute ({v!r})"
    if "\\" in v:
        return f"`governs` must use `/` as the path separator ({v!r})"
    if "\x00" in v:
        return "`governs` contains a NUL byte"
    return None


def resolve_scope(glossary_path: Path, governs: str, repo_root: Path | None = None) -> Path:
    """Resolve `governs` against the glossary's directory and enforce the safety rules.

    Returns the resolved (symlink-free, absolute) scope directory. Raises `ScopeError` with a
    human-readable reason when the value is malformed, the directory does not exist, no
    repository root can be found (and none was given), the scope escapes the repository root,
    or the glossary does not live inside its own scope.
    """
    reason = check_governs_syntax(governs)
    if reason is not None:
        raise ScopeError(reason)
    base = glossary_path.resolve().parent
    scope = (base / governs.strip()).resolve()
    if not scope.is_dir():
        raise ScopeError(f"`governs: {governs.strip()}` resolves to {scope}, which is not a directory")
    root = repo_root.resolve() if repo_root is not None else find_repo_root(base)
    if root is None:
        raise ScopeError(
            f"no repository root (a directory containing `.git`) found above {glossary_path}; "
            "pass --repo-root to name it"
        )
    if not scope.is_relative_to(root):
        raise ScopeError(f"`governs: {governs.strip()}` escapes the repository root {root} (resolves to {scope})")
    if not base.is_relative_to(scope):
        raise ScopeError(
            f"`governs: {governs.strip()}` resolves to {scope}, which does not contain the glossary's own "
            f"directory {base}; a glossary must live inside the scope it governs"
        )
    return scope


def governs_path(scope: Path, path: Path) -> bool:
    """True when `path` (resolved) lies inside the resolved `scope` directory (or is it)."""
    return path.resolve().is_relative_to(scope.resolve())
