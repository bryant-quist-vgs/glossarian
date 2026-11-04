#!/usr/bin/env python3
"""gather_reference_terms — inbound glossary-link resolver.

Scan a documentation tree (default ``docs/``) for inbound ``glossary.md#<slug>`` fragment
links, resolve each link's **path** relative to the file that holds it (as GitHub does) to
find the glossary it targets, check that the linking file lies inside the **scope that
glossary governs** (its ``governs:`` declaration, via ``glossarian.scope``), build the set of
anchors the glossary actually exposes (``github_slug`` of every ATX heading, via
``glossarian.model``), and **fail when any reference does not fully resolve** — a missing
glossary file, a file that is not a glossary, an unsafe scope, a linking file outside the
scope, or a slug on no heading. The link-integrity complement of ``glossary_format_check``.

Several glossaries may coexist in one tree (v3); each link is checked against the one its
path names. ``--glossary PATH`` narrows the report to the references that target that file.

Read-only except for one optional, never-overwriting ``--json FILE`` artifact. Never edits
any documentation or glossary file. The exit code is the load-bearing signal:
  0 = every reference resolves · 1 = read OK but one or more do not ·
  2 = path/JSON-target/usage error.

Built against contract v3 (v2 + path resolution, scope check, multi-glossary report).
Companion contract: contracts/gather_reference_terms_contract.md
Tests:              tests/test_gather_reference_terms.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from glossarian import github_slug, model, scope

DEFAULT_DOCS_ROOT = "docs"
DEFAULT_VERBOSE_N = 3

# The framed-block rule rendered above/below each --verbose source-context window.
_FRAME = "    " + "-" * 26

# An inbound glossary reference: an optional path prefix ending in `glossary.md`, then
# `#<fragment>`. The fragment runs to the first link-terminating character (whitespace, a
# paren/bracket/angle, a quote, a backtick, or `#`). The leading negative lookbehind keeps
# `myglossary.md#x` from matching as a bare `glossary.md#x` (basename must be exact). The
# path prefix (`./`, `../`, `sub/`, ...) is resolved against the linking file's directory (v3).
_LINK_CHARS = r"[^\s()<>\"'`#\[\]]"
_GLOSSARY_REF = re.compile(rf"(?<![\w.\-])(?P<prefix>(?:{_LINK_CHARS}*/)?)glossary\.md#(?P<frag>{_LINK_CHARS}+)")

_NUMBERISH = re.compile(r"-?\d+")

# Reference statuses, in the order the text report explains them.
RESOLVED = "resolved"
MISSING_GLOSSARY = "missing-glossary"  # the link's path names no file
NOT_A_GLOSSARY = "not-a-glossary"  # the file exists but its front matter lacks `id: glossary`
INVALID_SCOPE = "invalid-scope"  # the glossary's `governs` is absent or unsafe (see glossary.error)
OUT_OF_SCOPE = "out-of-scope"  # the linking file is not inside the glossary's governed scope
UNRESOLVED_ANCHOR = "unresolved-anchor"  # the glossary has no heading with this slug


# --------------------------------------------------------------------------- #
# Errors / findings structures                                                 #
# --------------------------------------------------------------------------- #


class _Exit2(Exception):
    """A path / JSON-target / usage failure that maps to exit code 2."""

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


@dataclass
class Reference:
    file: str
    line: int
    status: str  # one of the statuses above


@dataclass
class TermFinding:
    glossary: str  # display path of the glossary the links name (normalised, as linked)
    slug: str
    references: list[Reference]  # sorted by (file, line)

    @property
    def key(self) -> str:
        return f"{self.glossary}#{self.slug}"

    @property
    def resolved(self) -> bool:
        return all(r.status == RESOLVED for r in self.references)

    @property
    def status(self) -> str:
        """The worst status among the references (RESOLVED only when all resolve)."""
        for r in self.references:
            if r.status != RESOLVED:
                return r.status
        return RESOLVED


@dataclass
class GlossaryInfo:
    """What the resolver learned about one linked glossary file."""

    path: str  # display path
    exists: bool
    is_glossary: bool = False
    anchors: set[str] = field(default_factory=set)
    governs: str | None = None  # the raw `governs` value, when declared
    scope: Path | None = None  # the resolved scope directory, when valid
    error: str | None = None  # why the scope is invalid, when it is


@dataclass
class Findings:
    docs_root: str
    glossary_filter: str | None  # the --glossary argument, when given
    files: list[str]  # sorted scanned (non-archived) files
    glossaries: dict[str, GlossaryInfo]  # display path -> info, for every linked glossary
    terms: list[TermFinding]  # sorted by (glossary, slug)


@dataclass
class Args:
    docs_root: str = DEFAULT_DOCS_ROOT
    glossary: str | None = None  # None = report every linked glossary
    repo_root: str | None = None
    quiet: bool = False
    failures: bool = False
    terms_only: bool = False
    verbose_n: int | None = None  # None = not requested
    debug: bool = False
    json_requested: bool = False
    json_file: str | None = None  # None + json_requested => JSON to stdout


# --------------------------------------------------------------------------- #
# Argument parsing (manual: --verbose [N] and --json [FILE] have optional args) #
# --------------------------------------------------------------------------- #


def _parse_verbose_n(s: str) -> int:
    if not _NUMBERISH.fullmatch(s):
        raise _Exit2(f"--verbose N must be a non-negative integer (got {s!r})")
    val = int(s)
    if val < 0:
        raise _Exit2(f"--verbose N must be non-negative (got {val})")
    return val


USAGE = """\
Usage: glossarian-gather [DOCS_ROOT] [--glossary PATH] [--repo-root DIR] [--failures]
                         [--terms-only | --verbose [N]] [--json [FILE]] [--debug] [--quiet]
       glossarian-gather -h | --help

Resolve inbound glossary.md#slug links under DOCS_ROOT (default docs/). Each link's path is
resolved relative to the file holding it; the linking file must lie inside the scope that
glossary governs (`governs:` under its ## Governance), and the slug must match one of the
glossary's headings. Read-only except for --json FILE (never overwrites).

Options:
  --glossary PATH   report only the references that target this glossary file
  --repo-root DIR   the repository root a `governs` scope may not escape (default: the
                    nearest ancestor of each glossary containing `.git`)
  --failures        list only unresolved terms
  --terms-only      term names only, no file:line references (excludes --verbose)
  --verbose [N]     quote N source lines of context around each reference (default 3)
  --json [FILE]     emit findings as JSON to stdout, or to FILE (must not exist)
  --debug           trace files/refs/resolutions to stderr
  --quiet           print nothing; rely on the exit code
  -h, --help        show this help and exit 0

Exit codes: 0 all links resolve, 1 unresolved links, 2 path/JSON-target/usage error."""


def _parse_args(argv: list[str]) -> Args:
    a = Args()
    docs_root_set = False
    i, n = 0, len(argv)
    while i < n:
        tok = argv[i]
        if tok == "--quiet":
            a.quiet = True
        elif tok == "--failures":
            a.failures = True
        elif tok == "--terms-only":
            a.terms_only = True
        elif tok == "--debug":
            a.debug = True
        elif tok == "--glossary" or tok.startswith("--glossary="):
            if "=" in tok:
                a.glossary = tok.split("=", 1)[1]
            else:
                i += 1
                if i >= n:
                    raise _Exit2("--glossary requires a path argument")
                a.glossary = argv[i]
        elif tok == "--repo-root" or tok.startswith("--repo-root="):
            if "=" in tok:
                a.repo_root = tok.split("=", 1)[1]
            else:
                i += 1
                if i >= n:
                    raise _Exit2("--repo-root requires a directory argument")
                a.repo_root = argv[i]
        elif tok == "--verbose" or tok.startswith("--verbose="):
            if "=" in tok:
                a.verbose_n = _parse_verbose_n(tok.split("=", 1)[1])
            elif i + 1 < n and _NUMBERISH.fullmatch(argv[i + 1]):
                i += 1
                a.verbose_n = _parse_verbose_n(argv[i])
            else:
                a.verbose_n = DEFAULT_VERBOSE_N
        elif tok == "--json" or tok.startswith("--json="):
            a.json_requested = True
            if "=" in tok:
                a.json_file = tok.split("=", 1)[1]
            elif i + 1 < n and not argv[i + 1].startswith("-"):
                i += 1
                a.json_file = argv[i]
            # else: JSON to stdout
        elif tok.startswith("--"):
            raise _Exit2(f"unknown option: {tok}")
        else:
            if docs_root_set:
                raise _Exit2(f"unexpected extra positional argument: {tok}")
            a.docs_root = tok
            docs_root_set = True
        i += 1
    return a


# --------------------------------------------------------------------------- #
# Scan / resolve                                                               #
# --------------------------------------------------------------------------- #


def _load_glossary(display: str, path: Path, repo_root: Path | None, dbg: Callable[[str], None]) -> GlossaryInfo:
    """Read one linked glossary: its anchors and its governed scope (or why it has none)."""
    if not path.is_file():
        dbg(f"glossary {display}: missing")
        return GlossaryInfo(path=display, exists=False)
    gtext = path.read_text(encoding="utf-8")
    gmodel = model.parse(gtext)
    info = GlossaryInfo(path=display, exists=True)
    if gmodel.frontmatter.get("id") != "glossary":
        info.error = "front matter does not declare `id: glossary`"
        dbg(f"glossary {display}: not a glossary")
        return info
    info.is_glossary = True
    info.anchors = {github_slug(ln.htext) for ln in gmodel.body if ln.is_heading}
    governs = gmodel.governance.fields.get(scope.GOVERNS_KEY) if gmodel.governance.present else None
    info.governs = governs
    if governs is None:
        info.error = "no `governs:` declared in the `## Governance` field block"
    else:
        try:
            info.scope = scope.resolve_scope(path, governs, repo_root)
        except scope.ScopeError as exc:
            info.error = str(exc)
    dbg(f"glossary {display}: {len(info.anchors)} heading anchors; scope={info.scope} error={info.error}")
    return info


def _scan(
    docs_root: Path, glossary_filter: str | None, repo_root: Path | None, dbg: Callable[[str], None]
) -> tuple[Findings, dict[str, list[str]]]:
    """Build the findings and a per-file line cache (for --verbose context)."""
    filter_real = Path(glossary_filter).resolve() if glossary_filter is not None else None
    glossaries: dict[str, GlossaryInfo] = {}  # display path -> info
    real_to_display: dict[Path, str] = {}
    references: dict[tuple[str, str], dict[tuple[str, int], str]] = {}
    file_lines: dict[str, list[str]] = {}
    scanned: list[str] = []

    for path in sorted(docs_root.rglob("*.md"), key=str):
        text = path.read_text(encoding="utf-8")
        if model.parse(text).frontmatter.get("archived", "").strip().lower() == "true":
            dbg(f"skip archived: {path}")
            continue
        fkey = str(path)
        scanned.append(fkey)
        lines = text.splitlines()
        file_lines[fkey] = lines
        for lineno, raw in enumerate(lines, start=1):
            for m in _GLOSSARY_REF.finditer(raw):
                frag = m.group("frag")
                target = Path(os.path.normpath(path.parent / m.group("prefix") / "glossary.md"))
                target_real = target.resolve()
                if filter_real is not None and target_real != filter_real:
                    dbg(f"skip reference to other glossary {target} at {fkey}:{lineno}")
                    continue
                display = real_to_display.setdefault(target_real, str(target))
                if display not in glossaries:
                    glossaries[display] = _load_glossary(display, target, repo_root, dbg)
                info = glossaries[display]
                if not info.exists:
                    status = MISSING_GLOSSARY
                elif not info.is_glossary:
                    status = NOT_A_GLOSSARY
                elif info.scope is None:
                    status = INVALID_SCOPE
                elif not scope.governs_path(info.scope, path):
                    status = OUT_OF_SCOPE
                elif frag not in info.anchors:
                    status = UNRESOLVED_ANCHOR
                else:
                    status = RESOLVED
                references.setdefault((display, frag), {})[(fkey, lineno)] = status
                dbg(f"reference {display}#{frag} at {fkey}:{lineno}: {status}")

    terms: list[TermFinding] = []
    for (display, slug), refs in sorted(references.items()):
        ordered = [Reference(f, ln, st) for (f, ln), st in sorted(refs.items())]
        terms.append(TermFinding(glossary=display, slug=slug, references=ordered))

    findings = Findings(
        docs_root=str(docs_root),
        glossary_filter=glossary_filter,
        files=sorted(scanned),
        glossaries=dict(sorted(glossaries.items())),
        terms=terms,
    )
    return findings, file_lines


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #


def findings_to_json(f: Findings) -> dict[str, Any]:
    """The machine contract shape (independent of the verbosity flags)."""
    resolved = sum(1 for t in f.terms if t.resolved)
    unresolved = len(f.terms) - resolved
    by_status: dict[str, int] = {}
    for t in f.terms:
        for r in t.references:
            by_status[r.status] = by_status.get(r.status, 0) + 1
    return {
        "docs_root": f.docs_root,
        "glossary": f.glossary_filter,
        "glossaries": {
            g.path: {
                "exists": g.exists,
                "is_glossary": g.is_glossary,
                "anchor_count": len(g.anchors),
                "governs": g.governs,
                "scope": str(g.scope) if g.scope is not None else None,
                "error": g.error,
            }
            for g in f.glossaries.values()
        },
        "files_scanned": len(f.files),
        "files": f.files,
        "terms": {
            t.key: {
                "glossary": t.glossary,
                "slug": t.slug,
                "resolved": t.resolved,
                "status": t.status,
                "reference_count": len(t.references),
                "references": [{"file": r.file, "line": r.line, "status": r.status} for r in t.references],
            }
            for t in f.terms
        },
        "summary": {
            "files_scanned": len(f.files),
            "glossaries": len(f.glossaries),
            "terms_total": len(f.terms),
            "resolved": resolved,
            "unresolved": unresolved,
            "references_by_status": dict(sorted(by_status.items())),
            "result": "FAILED" if unresolved else "OK",
        },
    }


def _context_block(file_lines: dict[str, list[str]], ref: Reference, n: int) -> list[str]:
    """A framed, line-numbered window of `n` lines before/after the reference, clamped."""
    lines = file_lines.get(ref.file, [])
    total = len(lines)
    start = max(1, ref.line - n)
    end = min(total, ref.line + n) if total else ref.line
    width = len(str(end))
    block = [_FRAME]
    for no in range(start, end + 1):
        raw = lines[no - 1] if 1 <= no <= total else ""
        block.append(f"    {no:>{width}}  {raw}")
    block.append(_FRAME)
    return block


def render_text(
    f: Findings,
    file_lines: dict[str, list[str]],
    failures_only: bool,
    terms_only: bool,
    verbose_n: int | None,
) -> list[str]:
    resolved = [t for t in f.terms if t.resolved]
    unresolved = [t for t in f.terms if not t.resolved]
    out = [f"Scanning: {f.docs_root}"]
    if f.glossary_filter is not None:
        out.append(f"Glossary: {f.glossary_filter}")
    else:
        out.append(f"Glossaries: {len(f.glossaries)}")
    for g in f.glossaries.values():
        if not g.exists:
            out.append(f"  {g.path} — missing")
        elif g.error is not None:
            out.append(f"  {g.path} — {g.error}")
        else:
            out.append(f"  {g.path} — governs {g.governs} ({len(g.anchors)} anchors)")
    out.append("")

    groups: list[tuple[str, list[TermFinding]]] = []
    if not failures_only:
        groups.append(("Resolved", resolved))
    groups.append(("Unresolved", unresolved))

    for gi, (label, terms) in enumerate(groups):
        if gi > 0:
            while out and out[-1] == "":
                out.pop()
            out.append("")
        out.append(f"{label} ({len(terms)}):")
        for t in terms:
            tag = "" if t.resolved else f"  [{t.status}]"
            out.append(f"  {t.key}{tag}")
            if terms_only:
                continue
            for r in t.references:
                rtag = "" if t.resolved else f"  [{r.status}]"
                out.append(f"    {r.file}:{r.line}{rtag}")
                if verbose_n is not None:
                    out.extend(_context_block(file_lines, r, verbose_n))
                    out.append("")

    while out and out[-1] == "":
        out.pop()
    out.append("")
    out.append(
        f"Files scanned: {len(f.files)} | Glossaries: {len(f.glossaries)} | "
        f"Terms resolved: {len(resolved)} | Terms unresolved: {len(unresolved)}"
    )
    out.append("FAILED" if unresolved else "OK")
    return out


# --------------------------------------------------------------------------- #
# JSON target guard / write                                                    #
# --------------------------------------------------------------------------- #


def _check_json_target(path: Path) -> None:
    """Fail fast (exit 2) before any scanning if the --json target is unusable."""
    if path.exists():
        raise _Exit2(f"--json target already exists (never overwritten): {path}")
    parent = path.parent
    if not parent.is_dir():
        raise _Exit2(f"--json target directory does not exist: {parent}")
    if not os.access(parent, os.W_OK):
        raise _Exit2(f"--json target directory is not writable: {parent}")


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError as exc:
        raise _Exit2(f"cannot write --json target {path}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Driver                                                                       #
# --------------------------------------------------------------------------- #


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    quiet = "--quiet" in argv
    try:
        args = _parse_args(argv)
        quiet = args.quiet
        if args.verbose_n is not None and args.terms_only:
            raise _Exit2("--verbose and --terms-only are mutually exclusive")
        if args.json_file is not None:
            _check_json_target(Path(args.json_file))

        docs_root = Path(args.docs_root)
        if not docs_root.is_dir():
            raise _Exit2(f"docs_root is not a readable directory: {docs_root}")
        if args.glossary is not None and not Path(args.glossary).is_file():
            raise _Exit2(f"--glossary is not a readable file: {args.glossary}")
        repo_root = Path(args.repo_root) if args.repo_root is not None else None
        if repo_root is not None and not repo_root.is_dir():
            raise _Exit2(f"--repo-root is not a directory: {repo_root}")

        def dbg(msg: str) -> None:
            if args.debug and not quiet:
                print(f"[debug] {msg}", file=sys.stderr)

        try:
            findings, file_lines = _scan(docs_root, args.glossary, repo_root, dbg)
        except (FileNotFoundError, IsADirectoryError, PermissionError, UnicodeDecodeError, OSError) as exc:
            raise _Exit2(f"cannot read: {exc}") from exc

        if args.json_file is not None:
            _write_json(Path(args.json_file), findings_to_json(findings))
    except _Exit2 as e:
        if not quiet:
            print(f"error: {e.msg}", file=sys.stderr)
        return 2

    unresolved = sum(1 for t in findings.terms if not t.resolved)

    if not quiet:
        if args.json_requested and args.json_file is None:
            print(json.dumps(findings_to_json(findings), indent=2, ensure_ascii=False))
        else:
            print("\n".join(render_text(findings, file_lines, args.failures, args.terms_only, args.verbose_n)))

    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
