"""test_glossary_fix — tests for glossarian.glossary_fix, contract v1.

Coverage:
  - Each repair: blank line before a `###`, mis-cased section, missing placeholder section
    (inserted at its canonical position), `see:` and `reserved-for:` term→slug, missing
    `is_source_of_truth`.
  - Ordering: repairs apply to the line numbers the check reported even when an earlier
    insertion shifts the file (the front-matter line goes in last).
  - Idempotence: a second run changes nothing and reports "nothing to repair".
  - Non-fixable violations are left and reported as "still failing" (exit 1).
  - --dry-run prints the plan and writes nothing; the write is atomic and leaves no temp file.
  - Usage / path errors are exit 2.
"""

from __future__ import annotations

from pathlib import Path

from glossarian import glossary_fix as gfx
from glossarian import glossary_format_check as gfc

BROKEN = """\
---
id: glossary
---

# Glossary

## Governance

```glossary
governs: ../
```
Rules.

## Definitions

### working agent
```glossary
see: human holds
reserved-for: Lacey Tool
```
Body.
### human holds
Body two.

### Lacey Tool
```glossary
reserved-for-target: true
```
A tool.

## Confusable pairs

| a | b | c |
|---|---|---|

## Reserved Targets

| Target | What | Local | Remote |
|---|---|---|---|
| [Lacey Tool](glossary.md#lacey-tool) | tool | ~/lacey | github.com/x/lacey |
"""


def repo_glossary(tmp_path: Path, text: str = BROKEN) -> Path:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "repo" / "docs").mkdir()
    p = tmp_path / "repo" / "docs" / "glossary.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_fix_repairs_everything_fixable_and_is_green(tmp_path: Path, capsys) -> None:
    p = repo_glossary(tmp_path)
    assert gfc.main([str(p), "--quiet"]) == 1
    assert gfx.main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "6 repairs applied" in out and out.rstrip().endswith(f"OK: {p}")
    text = p.read_text(encoding="utf-8")
    assert "is_source_of_truth: true" in text
    assert "see: human-holds" in text and "reserved-for: lacey-tool" in text
    assert "Body.\n\n### human holds" in text  # blank inserted before the heading, not elsewhere
    assert "```\nBody.\n" in text  # no stray blank between the fence and the body
    assert "## Confusable Pairs" in text
    assert "## Renames and deprecated terms\n\nNone yet.\n\n## Reserved Targets" in text  # canonical position
    assert gfc.main([str(p), "--quiet"]) == 0


def test_fix_is_idempotent(tmp_path: Path, capsys) -> None:
    p = repo_glossary(tmp_path)
    gfx.main([str(p), "--quiet"])
    after = p.read_text(encoding="utf-8")
    assert gfx.main([str(p)]) == 0
    assert "nothing to repair" in capsys.readouterr().out
    assert p.read_text(encoding="utf-8") == after


def test_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    p = repo_glossary(tmp_path)
    assert gfx.main([str(p), "--dry-run"]) == 0  # would be valid after the planned repairs
    out = capsys.readouterr().out
    assert "would insert a blank line" in out and "6 repairs planned (dry run, nothing written)" in out
    assert p.read_text(encoding="utf-8") == BROKEN
    assert sorted(x.name for x in p.parent.iterdir()) == ["glossary.md"]  # no temp file left behind


def test_non_fixable_left_and_reported(tmp_path: Path, capsys) -> None:
    text = BROKEN.replace("### human holds", "### human (holds)")
    p = repo_glossary(tmp_path, text)
    assert gfx.main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "still failing: term heading must contain only the canonical term" in out
    assert "### human (holds)" in p.read_text(encoding="utf-8")  # untouched


def test_nothing_to_repair_on_valid_file_exit_0(tmp_path: Path, capsys) -> None:
    p = repo_glossary(tmp_path)
    gfx.main([str(p), "--quiet"])
    assert gfx.main([str(p)]) == 0
    assert "nothing to repair" in capsys.readouterr().out


def test_only_the_glossary_is_written(tmp_path: Path) -> None:
    p = repo_glossary(tmp_path)
    before = sorted(str(x) for x in tmp_path.rglob("*"))
    gfx.main([str(p), "--quiet"])
    assert sorted(str(x) for x in tmp_path.rglob("*")) == before


def test_usage_and_path_errors(tmp_path: Path, capsys) -> None:
    assert gfx.main(["-h"]) == 0
    assert capsys.readouterr().out.startswith("Usage: glossarian-fix")
    assert gfx.main([]) == 2
    assert gfx.main([str(tmp_path / "nope.md")]) == 2
    assert gfx.main([str(tmp_path)]) == 2
    p = repo_glossary(tmp_path)
    assert gfx.main([str(p), "--bogus"]) == 2
    assert gfx.main([str(p), "--repo-root"]) == 2
    assert p.read_text(encoding="utf-8") == BROKEN
