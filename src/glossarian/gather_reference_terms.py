#!/usr/bin/env python3
"""gather_reference_terms — inbound glossary-link resolver.

Scan a documentation tree (default ``docs/``) for inbound ``glossary.md#<slug>`` fragment
links, deduplicate the referenced slugs, build the set of anchors the glossary actually
exposes (``github_slug`` of every ATX heading in the glossary, via ``glossarian.model``),
and **fail when a referenced slug resolves to no heading**. The link-integrity half of the
glossary-anchor repair — the complement of ``glossary_format_check`` (which validates the
glossary's own shape).

Read-only except for one optional, never-overwriting ``--json FILE`` artifact. Never edits
any documentation or glossary file. The exit code is the load-bearing signal:
  0 = every referenced slug resolves · 1 = read OK but one or more unresolved ·
  2 = path/JSON-target/usage error.

Built against contract v2 (v1 + `-h`/`--help` usage, behavior 5).
Companion contract: contracts/gather_reference_terms_contract.md
Tests:              tests/test_gather_reference_terms.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from glossarian import github_slug, model

DEFAULT_DOCS_ROOT = "docs"
DEFAULT_GLOSSARY = "docs/glossary.md"
DEFAULT_VERBOSE_N = 3

# The framed-block rule rendered above/below each --verbose source-context window.
_FRAME = "    " + "-" * 26

# An inbound glossary reference: an optional path prefix ending in `glossary.md`, then
# `#<fragment>`. The fragment runs to the first link-terminating character (whitespace, a
# paren/bracket/angle, a quote, a backtick, or `#`). The leading negative lookbehind keeps
# `myglossary.md#x` from matching as a bare `glossary.md#x` (basename must be exact). The
# optional path prefix (ending in `/`) accepts `./`, `../`, and `docs/` forms; matching is
# by basename only (contract assumption: the relative path is not resolved to this file).
_LINK_CHARS = r"[^\s()<>\"'`#\[\]]"
_GLOSSARY_REF = re.compile(rf"(?<![\w.\-])(?:{_LINK_CHARS}*/)?glossary\.md#(?P<frag>{_LINK_CHARS}+)")

_NUMBERISH = re.compile(r"-?\d+")


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


@dataclass
class TermFinding:
    slug: str
    resolved: bool
    references: list[Reference]  # sorted by (file, line)


@dataclass
class Findings:
    docs_root: str
    glossary: str
    files: list[str]  # sorted scanned (non-archived) files
    terms: list[TermFinding]  # sorted by slug


@dataclass
class Args:
    docs_root: str = DEFAULT_DOCS_ROOT
    glossary: str = DEFAULT_GLOSSARY
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
Usage: glossarian-gather [DOCS_ROOT] [--glossary PATH] [--failures] [--terms-only | --verbose [N]]
                         [--json [FILE]] [--debug] [--quiet]
       glossarian-gather -h | --help

Resolve inbound glossary.md#slug links under DOCS_ROOT (default docs/) against the headings
of the glossary (default docs/glossary.md). Read-only except for --json FILE (never overwrites).

Options:
  --glossary PATH   glossary whose headings define the valid anchors
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


def _scan(docs_root: Path, glossary: Path, dbg: Callable[[str], None]) -> tuple[Findings, dict[str, list[str]]]:
    """Build the findings and a per-file line cache (for --verbose context)."""
    gtext = glossary.read_text(encoding="utf-8")
    gmodel = model.parse(gtext)
    anchors = {github_slug(ln.htext) for ln in gmodel.body if ln.is_heading}
    dbg(f"glossary {glossary}: {len(anchors)} heading anchors")

    references: dict[str, set[tuple[str, int]]] = {}
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
                references.setdefault(frag, set()).add((fkey, lineno))
                dbg(f"reference {frag} at {fkey}:{lineno}")

    terms: list[TermFinding] = []
    for slug in sorted(references):
        refs = [Reference(f, ln) for f, ln in sorted(references[slug])]
        resolved = slug in anchors
        dbg(f"resolve {slug}: {'ok' if resolved else 'UNRESOLVED'} ({len(refs)} refs)")
        terms.append(TermFinding(slug=slug, resolved=resolved, references=refs))

    findings = Findings(docs_root=str(docs_root), glossary=str(glossary), files=sorted(scanned), terms=terms)
    return findings, file_lines


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #


def findings_to_json(f: Findings) -> dict[str, Any]:
    """The machine contract shape (independent of the verbosity flags)."""
    resolved = sum(1 for t in f.terms if t.resolved)
    unresolved = len(f.terms) - resolved
    return {
        "docs_root": f.docs_root,
        "glossary": f.glossary,
        "files_scanned": len(f.files),
        "files": f.files,
        "terms": {
            t.slug: {
                "resolved": t.resolved,
                "reference_count": len(t.references),
                "references": [{"file": r.file, "line": r.line} for r in t.references],
            }
            for t in f.terms
        },
        "summary": {
            "files_scanned": len(f.files),
            "terms_total": len(f.terms),
            "resolved": resolved,
            "unresolved": unresolved,
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
    out = [f"Scanning: {f.docs_root}", f"Glossary: {f.glossary}", ""]

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
            out.append(f"  {t.slug}")
            if terms_only:
                continue
            for r in t.references:
                out.append(f"    {r.file}:{r.line}")
                if verbose_n is not None:
                    out.extend(_context_block(file_lines, r, verbose_n))
                    out.append("")

    while out and out[-1] == "":
        out.pop()
    out.append("")
    out.append(f"Files scanned: {len(f.files)} | Terms resolved: {len(resolved)} | Terms unresolved: {len(unresolved)}")
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
        glossary = Path(args.glossary)
        if not docs_root.is_dir():
            raise _Exit2(f"docs_root is not a readable directory: {docs_root}")

        def dbg(msg: str) -> None:
            if args.debug and not quiet:
                print(f"[debug] {msg}", file=sys.stderr)

        try:
            findings, file_lines = _scan(docs_root, glossary, dbg)
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
