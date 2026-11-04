"""test_glossary_template — tests for glossarian.glossary_template, contract v1.

Coverage:
  - Behavior 1: the written file passes glossary_format_check on disk (exit 0).
  - Behavior 2: `governs` defaults to the repository root relative to the file (`../` for
    docs/glossary.md, `.` at the root, `.` outside any repository); `--governs` overrides and
    is syntax-checked.
  - Behavior 3: an existing path (file, symlink, directory) is refused with exit 2 and left
    untouched; a missing parent is exit 2; nothing else is ever written.
  - Behavior 4: usage — no PATH, two PATHs, unknown option are exit 2; -h/--help exit 0.
"""

from __future__ import annotations

from pathlib import Path

from glossarian import glossary_format_check as gfc
from glossarian import glossary_template as gt


def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / ".git").mkdir(parents=True)
    (r / "docs").mkdir()
    return r


def test_template_passes_check_on_disk(tmp_path: Path, capsys) -> None:
    r = repo(tmp_path)
    target = r / "docs" / "glossary.md"
    assert gt.main([str(target)]) == 0
    assert "wrote" in capsys.readouterr().out
    assert gfc.main([str(target), "--quiet"]) == 0  # Load-bearing: the template is green as written
    text = target.read_text(encoding="utf-8")
    assert "governs: ../" in text
    for name in gfc.REQUIRED_SECTIONS:
        assert f"## {name}" in text


def test_default_governs_at_repo_root_and_outside(tmp_path: Path) -> None:
    r = repo(tmp_path)
    assert gt.default_governs(r / "glossary.md") == "."
    assert gt.default_governs(r / "docs" / "glossary.md") == "../"
    (r / "a" / "b").mkdir(parents=True)
    assert gt.default_governs(r / "a" / "b" / "glossary.md") == "../../"
    loose = tmp_path / "loose"
    loose.mkdir()
    if gt.scope.find_repo_root(loose) is None:
        assert gt.default_governs(loose / "glossary.md") == "."


def test_governs_override_and_syntax(tmp_path: Path) -> None:
    r = repo(tmp_path)
    target = r / "docs" / "glossary.md"
    assert gt.main([str(target), "--governs", "."]) == 0
    assert "governs: ." in target.read_text(encoding="utf-8")
    other = r / "docs" / "other.md"
    assert gt.main([str(other), "--governs=/abs"]) == 2
    assert not other.exists()


def test_refuses_existing_path(tmp_path: Path) -> None:
    r = repo(tmp_path)
    f = r / "docs" / "glossary.md"
    f.write_text("mine", encoding="utf-8")
    assert gt.main([str(f)]) == 2
    assert f.read_text(encoding="utf-8") == "mine"
    d = r / "docs" / "dir.md"
    d.mkdir()
    assert gt.main([str(d)]) == 2
    link = r / "docs" / "link.md"
    link.symlink_to(f)
    assert gt.main([str(link)]) == 2


def test_missing_parent_exit_2_nothing_written(tmp_path: Path) -> None:
    r = repo(tmp_path)
    before = sorted(str(p) for p in r.rglob("*"))
    assert gt.main([str(r / "nope" / "glossary.md")]) == 2
    assert sorted(str(p) for p in r.rglob("*")) == before


def test_usage(tmp_path: Path, capsys) -> None:
    assert gt.main([]) == 2
    assert gt.main(["-h"]) == 0
    assert capsys.readouterr().out.startswith("Usage: glossarian-template")
    r = repo(tmp_path)
    assert gt.main([str(r / "a.md"), str(r / "b.md")]) == 2
    assert gt.main([str(r / "a.md"), "--bogus"]) == 2
    assert gt.main([str(r / "a.md"), "--governs"]) == 2
    assert not (r / "a.md").exists()
