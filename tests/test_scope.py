"""test_scope — tests for glossarian.scope, contract v1.

Coverage:
  - find_repo_root: nearest ancestor with `.git` (directory or worktree file); None outside.
  - check_governs_syntax: empty, absolute, home-relative, URL, NUL rejected; relative accepted.
  - resolve_scope: `.`/`../` resolve inside the repo; escaping the root, excluding the
    glossary, a missing directory, no root and no override are ScopeError; the repo_root
    override bounds the check; symlinked glossary directories are resolved first.
  - governs_path: containment is decided on resolved paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from glossarian import scope


def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / ".git").mkdir(parents=True)
    (r / "docs" / "sub").mkdir(parents=True)
    (r / "docs" / "glossary.md").write_text("x", encoding="utf-8")
    return r


def test_find_repo_root_walks_up(tmp_path: Path) -> None:
    r = repo(tmp_path)
    assert scope.find_repo_root(r / "docs" / "sub") == r.resolve()
    assert scope.find_repo_root(r) == r.resolve()
    assert scope.find_repo_root(tmp_path) is None or scope.find_repo_root(tmp_path) != r.resolve()


def test_find_repo_root_accepts_worktree_git_file(tmp_path: Path) -> None:
    r = tmp_path / "wt"
    (r / "docs").mkdir(parents=True)
    (r / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    assert scope.find_repo_root(r / "docs") == r.resolve()


@pytest.mark.parametrize("bad", ["", "   ", "/abs", "~/x", "https://h/p", "C:\\x", "a\x00b"])
def test_governs_syntax_rejects(bad: str) -> None:
    assert scope.check_governs_syntax(bad) is not None


@pytest.mark.parametrize("ok", [".", "./", "../", "../..", "sub", "./sub/"])
def test_governs_syntax_accepts_relative(ok: str) -> None:
    assert scope.check_governs_syntax(ok) is None


def test_resolve_scope_parent_and_self(tmp_path: Path) -> None:
    r = repo(tmp_path)
    g = r / "docs" / "glossary.md"
    assert scope.resolve_scope(g, "../") == r.resolve()
    assert scope.resolve_scope(g, ".") == (r / "docs").resolve()
    assert scope.resolve_scope(g, "./") == (r / "docs").resolve()


def test_resolve_scope_rejects_escape(tmp_path: Path) -> None:
    # Load-bearing: a glossary never governs above its repository root.
    g = repo(tmp_path) / "docs" / "glossary.md"
    with pytest.raises(scope.ScopeError, match="escapes the repository root"):
        scope.resolve_scope(g, "../../")
    with pytest.raises(scope.ScopeError, match="escapes the repository root"):
        scope.resolve_scope(g, "../../../../../../../../")


def test_resolve_scope_rejects_sibling_excluding_glossary(tmp_path: Path) -> None:
    g = repo(tmp_path) / "docs" / "glossary.md"
    with pytest.raises(scope.ScopeError, match="does not contain the glossary"):
        scope.resolve_scope(g, "sub")


def test_resolve_scope_rejects_missing_dir_and_malformed(tmp_path: Path) -> None:
    g = repo(tmp_path) / "docs" / "glossary.md"
    with pytest.raises(scope.ScopeError, match="not a directory"):
        scope.resolve_scope(g, "../nope")
    with pytest.raises(scope.ScopeError, match="not absolute"):
        scope.resolve_scope(g, "/etc")


def test_resolve_scope_needs_a_root(tmp_path: Path) -> None:
    d = tmp_path / "loose" / "docs"
    d.mkdir(parents=True)
    g = d / "glossary.md"
    g.write_text("x", encoding="utf-8")
    if scope.find_repo_root(d) is None:  # the temp dir itself is not inside a repository
        with pytest.raises(scope.ScopeError, match="no repository root"):
            scope.resolve_scope(g, ".")
    # An explicit root bounds the scope exactly like a `.git` would.
    assert scope.resolve_scope(g, "../", repo_root=tmp_path / "loose") == (tmp_path / "loose").resolve()
    with pytest.raises(scope.ScopeError, match="escapes the repository root"):
        scope.resolve_scope(g, "../", repo_root=d)


def test_resolve_scope_through_symlink(tmp_path: Path) -> None:
    r = repo(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(r / "docs")
    # The glossary reached via a symlink resolves to its real directory, so `../` is the repo.
    assert scope.resolve_scope(link / "glossary.md", "../") == r.resolve()


def test_governs_path_containment(tmp_path: Path) -> None:
    r = repo(tmp_path)
    assert scope.governs_path(r / "docs", r / "docs" / "sub" / "x.md")
    assert scope.governs_path(r / "docs", r / "docs")
    assert not scope.governs_path(r / "docs", r / "README.md")
