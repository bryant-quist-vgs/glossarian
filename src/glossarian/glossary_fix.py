#!/usr/bin/env python3
"""glossary_fix — repair the trivial, mechanically safe glossary issues.

`glossarian-fix GLOSSARY [--dry-run]` runs the linter (`glossary_format_check.validate`),
applies every repair the linter marked as fixable (`Violation.fix`), re-validates, and
reports what changed and what still fails. The repairs are deliberately small and
content-preserving:

  - `term-no-blank-before-heading`  insert the missing blank line before a `###` heading
  - `section-case`                  rename a mis-cased required `##` heading
  - `section-missing`               append a missing Confusable Pairs / Renames / Reserved
                                    Targets section with its placeholder body
  - `field-see-unresolved`          rewrite a `see:` written as a term into its slug
  - `field-reserved-for-unresolved` rewrite a `reserved-for:` written as a term into its slug
  - (warning) missing `is_source_of_truth: true` in the front matter

Everything else (empty bodies, duplicate slugs, section order, stray paragraphs, an unsafe
`governs`) needs a human: the tool prints those and leaves them. The file is rewritten in
place, atomically (temp file + rename in the same directory), only when at least one repair
applies and not under `--dry-run`.

Exit codes: 0 = the glossary is valid after the run (whether or not anything changed) ·
1 = violations remain · 2 = path missing / unreadable / unwritable / bad usage.

Built against contract v1.
Companion contract: contracts/glossary_fix_contract.md
Tests:              tests/test_glossary_fix.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from glossarian import glossary_format_check as gfc
from glossarian import model
from glossarian.github_slug import github_slug

USAGE = """\
Usage: glossarian-fix GLOSSARY_PATH [--repo-root DIR] [--dry-run] [--quiet]
       glossarian-fix -h | --help

Repair the trivial issues glossarian-check marks as fixable (missing blank lines before term
headings, mis-cased required section headings, missing placeholder sections, `see:` /
`reserved-for:` values written as terms instead of slugs, a missing `is_source_of_truth`),
then re-check. Rewrites GLOSSARY_PATH in place unless --dry-run.

Options:
  --repo-root DIR  passed through to the check (bounds the `governs` scope)
  --dry-run        print the repairs without writing
  --quiet          print nothing; rely on the exit code
  -h, --help       show this help and exit 0

Exit codes: 0 valid after the run, 1 violations remain, 2 path/usage error."""

MAX_PASSES = 3  # a repair can expose the next fixable issue (e.g. a stubbed section); bounded

_SEE_LINE = re.compile(r"^(\s*see\s*:\s*)(.+?)\s*$")
_RESERVED_LINE = re.compile(r"^(\s*reserved-for\s*:\s*)(.+?)\s*$")
_H2_LINE = re.compile(r"^(##\s+)(.+?)(\s*#*\s*)$")


@dataclass
class Repair:
    line: int | None
    description: str


def _rewrite_field_value(lines: list[str], block_line: int, pattern: re.Pattern[str], old: str, new: str) -> bool:
    """Within the field block opened at 1-based `block_line`, rewrite `key: old` to `key: new`."""
    k = block_line  # index of the line after the opening fence (0-based == block_line)
    while k < len(lines) and not lines[k].lstrip().startswith(("```", "~~~")):
        m = pattern.match(lines[k])
        if m and m.group(2).strip() == old:
            lines[k] = f"{m.group(1)}{new}"
            return True
        k += 1
    return False


def _append_section(lines: list[str], name: str, stub: str) -> None:
    """Append `## name` + stub at the canonical position: before the first later required
    section that is present, else at the end of the file."""
    idx = gfc.REQUIRED_SECTIONS.index(name)
    later = set(gfc.REQUIRED_SECTIONS[idx + 1 :])
    insert_at = len(lines)
    in_fence = False
    for i, raw in enumerate(lines):
        s = raw.lstrip()
        if s.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _H2_LINE.match(raw)
        if m and m.group(2).strip() in later:
            insert_at = i
            break
    block = [f"## {name}", "", stub, ""]
    # Keep one blank line between the previous content and the new heading.
    if insert_at > 0 and lines[insert_at - 1].strip() != "":
        block.insert(0, "")
    lines[insert_at:insert_at] = block


def plan_and_apply(
    text: str, *, glossary_path: Path | None = None, repo_root: Path | None = None
) -> tuple[str, list[Repair], list[gfc.Violation]]:
    """Apply every fixable repair to `text`. Returns (new_text, repairs, remaining_violations)."""
    repairs: list[Repair] = []
    current = text
    for _ in range(MAX_PASSES):
        violations, warnings, _count = gfc.validate(current, glossary_path=glossary_path, repo_root=repo_root)
        lines = current.splitlines()
        changed = False
        m = model.parse(current)

        # Line-anchored repairs first, bottom-up, so every reported line number stays valid;
        # the structural and front-matter insertions (which shift lines) come after.
        for v in sorted((v for v in violations if v.fix is not None), key=lambda v: -(v.line or 0)):
            if v.code == "term-no-blank-before-heading" and v.line is not None:
                lines.insert(v.line - 1, "")
                changed = True
                repairs.append(Repair(v.line, v.fix or ""))
            elif v.code == "section-case" and v.line is not None:
                h = _H2_LINE.match(lines[v.line - 1])
                canonical = next(
                    (n for n in gfc.REQUIRED_SECTIONS if h and h.group(2).strip().lower() == n.lower()), None
                )
                if h and canonical:
                    lines[v.line - 1] = f"{h.group(1)}{canonical}"
                    changed = True
                    repairs.append(Repair(v.line, v.fix or ""))
            elif v.code == "field-see-unresolved" and v.line is not None:
                old = v.msg.split("`see: ", 1)[1].split("`", 1)[0]
                if _rewrite_field_value(lines, v.line, _SEE_LINE, old, github_slug(old)):
                    changed = True
                    repairs.append(Repair(v.line, v.fix or ""))
            elif v.code == "field-reserved-for-unresolved" and v.line is not None:
                old = v.msg.split("`reserved-for: ", 1)[1].split("`", 1)[0]
                if _rewrite_field_value(lines, v.line, _RESERVED_LINE, old, github_slug(old)):
                    changed = True
                    repairs.append(Repair(v.line, v.fix or ""))

        # Structural repairs (no stable line) last.
        for v in violations:
            if v.code == "section-missing" and v.fix is not None:
                name = v.msg.split("`## ", 1)[1].split("`", 1)[0]
                stub = gfc.SECTION_STUBS.get(name)
                if stub is not None:
                    _append_section(lines, name, stub)
                    changed = True
                    repairs.append(Repair(None, v.fix))

        # Warning: is_source_of_truth — insert after the `id:` line of a well-formed front matter.
        if any("is_source_of_truth" in w for w in warnings) and m.frontmatter_error is None:
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    break
                key = lines[i].split(":", 1)[0].strip()
                if key == "is_source_of_truth":
                    lines[i] = "is_source_of_truth: true"
                    changed = True
                    break
                if key == "id":
                    lines.insert(i + 1, "is_source_of_truth: true")
                    changed = True
                    break
            if changed and not any(r.description.startswith("add `is_source_of_truth") for r in repairs):
                repairs.append(Repair(2, "add `is_source_of_truth: true` to the front matter"))

        if not changed:
            return current, repairs, violations
        current = "\n".join(lines) + ("\n" if text.endswith("\n") or not lines else "")

    violations, _w, _c = gfc.validate(current, glossary_path=glossary_path, repo_root=repo_root)
    return current, repairs, violations


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    quiet = "--quiet" in argv
    dry_run = "--dry-run" in argv
    repo_root: Path | None = None
    positional: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in {"--quiet", "--dry-run"}:
            pass
        elif tok == "--repo-root" or tok.startswith("--repo-root="):
            if "=" in tok:
                repo_root = Path(tok.split("=", 1)[1])
            else:
                i += 1
                if i >= len(argv):
                    _err(quiet, "--repo-root requires a directory argument")
                    return 2
                repo_root = Path(argv[i])
        elif tok.startswith("--"):
            _err(quiet, f"unknown option: {tok}")
            return 2
        else:
            positional.append(tok)
        i += 1
    if len(positional) != 1:
        _err(quiet, "exactly one GLOSSARY_PATH is required")
        return 2
    path = Path(positional[0])
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError, UnicodeDecodeError) as exc:
        _err(quiet, f"cannot read {path}: {exc}")
        return 2

    new_text, repairs, remaining = plan_and_apply(text, glossary_path=path, repo_root=repo_root)

    if repairs and not dry_run:
        try:
            _write_atomic(path, new_text)
        except OSError as exc:
            _err(quiet, f"cannot write {path}: {exc}")
            return 2

    if not quiet:
        verb = "would " if dry_run else ""
        for r in sorted(repairs, key=lambda r: (r.line is None, r.line or 0)):
            loc = f"{path}:{r.line}" if r.line is not None else f"{path}"
            print(f"{loc}: {verb}{r.description}")
        if not repairs:
            print(f"{path}: nothing to repair")
        elif dry_run:
            print(f"{len(repairs)} repair{'s' if len(repairs) != 1 else ''} planned (dry run, nothing written)")
        else:
            print(f"{len(repairs)} repair{'s' if len(repairs) != 1 else ''} applied")
        for v in remaining:
            loc = f"{path}:{v.line}" if v.line is not None else f"{path}"
            print(f"{loc}: still failing: {v.msg}")
        if not remaining:
            print(f"OK: {path}")
    return 1 if remaining else 0


def _err(quiet: bool, msg: str) -> None:
    if not quiet:
        print(f"error: {msg}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
