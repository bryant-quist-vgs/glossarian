"""test_gather_reference_terms — tests for glossarian.gather_reference_terms, contract v3.

v3 coverage (appended at the end of the file): link paths resolve relative to the linking
file (a `docs/`-prefixed link from a subdirectory is `missing-glossary`); a linking file
outside the glossary's `governs` scope is `out-of-scope`; a target without `id: glossary`
is `not-a-glossary`; a glossary with an unsafe/absent `governs` is `invalid-scope`; several
glossaries are reported side by side; `--glossary` narrows the report; `--repo-root` bounds
the scope; the JSON carries `glossaries` and per-reference `status`.

Coverage (one or more tests per contract behavior / load-bearing annotation):
  - Behavior 1 (scan set): archived docs (front-matter `archived: true`) are skipped;
    files_scanned counts the non-archived `*.md` set.
  - Behavior 2 (extract refs): direct, relative (`./`, `../`), and path-prefixed
    (`docs/glossary.md#`) link forms; duplicate references on one line deduplicate to a
    single file:line; underscore and hyphenated slugs; `myglossary.md#` is NOT a match.
  - Behaviors 3 & 4 (anchor set + resolution): anchors are github_slug of every heading
    (section headings like `definitions` resolve too); a hand-written slug github_slug
    would not emit (the `requirements → items LLM` arrow case, and a bold-paragraph
    glossary) is reported unresolved — GitHub-fidelity via the shared github_slug.
  - Behavior 5 (up-front validation): `--verbose` with `--terms-only` and an invalid
    `--verbose N` are usage errors (exit 2); a pre-existing `--json` target exits 2 and is
    never clobbered; a missing `--json` parent dir exits 2; (v2) -h/--help prints usage,
    exits 0, and reads nothing (load-bearing for the installer's --check).
  - Behavior 6 (render): default scope lists resolved + unresolved; `--failures` only
    unresolved; `--terms-only` names only; `--verbose [N]` context-window math — N=0, N=1,
    default N=3, clamping at the file's first/last line (a window spanning two lines).
  - Behavior 7/8 (JSON + exit code): the machine JSON shape; exit 0 (all resolve), 1
    (some unresolved), 2 (bad path); the JSON FILE artifact is written even under --quiet.
  - Capability boundary: the only write is the explicit `--json FILE`; no doc/glossary
    file is ever modified.

Run with:  uv run pytest tests/test_gather_reference_terms.py
"""

from __future__ import annotations

import json
from pathlib import Path

from glossarian import gather_reference_terms as grt
from glossarian.github_slug import github_slug

# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

# A glossary whose definitions are real `###` headings (post-migration shape), plus an
# arrow term whose github_slug keeps the arrow.
GLOSSARY = """\
---
id: glossary
---

# Glossary

## Governance

```glossary
governs: ../
```

## Definitions

### working agent
The write-capable agent.

### human_holds
A gate value held by the human.

### requirements → items LLM
Splits requirements into items.
"""

# refs.md line map (1-based):
#  2: two working-agent links on ONE line (dedup), 3: underscore slug,
#  4: arrow-mismatch (unresolved), 5: ghost (unresolved).
REFS_MD = (
    "# Refs\n"
    "Inline [working agent](glossary.md#working-agent), repeat [again](glossary.md#working-agent).\n"
    "Underscore [holds](glossary.md#human_holds).\n"
    "Arrow mismatch [req](glossary.md#requirements-items-llm).\n"
    "Ghost [g](glossary.md#ghost-term).\n"
)

# A subdir doc exercising the relative (`../`) link form, including to a section anchor.
SYS_MD = "# Sys\nRelative [wa](../glossary.md#working-agent).\nSection [def](../glossary.md#definitions).\n"

# Archived: must be skipped; its reference must never appear in the findings.
ARCHIVED_MD = "---\narchived: true\n---\n# Archived\n[no](glossary.md#archived-only).\n"


def make_tree(tmp_path: Path, glossary_text: str, docs: dict[str, str]) -> Path:
    """Write docs/glossary.md + the given docs under a fresh docs/ root inside a fake repository
    (tmp_path/.git bounds every `governs` scope); return the root."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "glossary.md").write_text(glossary_text, encoding="utf-8")
    for rel, content in docs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def run_json(tmp_path: Path, root: Path, *flags: str) -> tuple[int, dict | None]:
    """Run with --quiet --json FILE and return (exit_code, parsed findings)."""
    out = tmp_path / "out.json"
    rc = grt.main([str(root), "--glossary", str(root / "glossary.md"), "--quiet", "--json", str(out), *flags])
    data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return rc, data


def std_tree(tmp_path: Path) -> Path:
    return make_tree(tmp_path, GLOSSARY, {"refs.md": REFS_MD, "diagrams/sys.md": SYS_MD, "archived.md": ARCHIVED_MD})


def T(data: dict, slug: str) -> dict:
    """The term finding for `slug` (v3 keys are `<glossary>#<slug>`; the std tree has one glossary)."""
    matches = [v for k, v in data["terms"].items() if k.endswith(f"#{slug}")]
    assert len(matches) == 1, f"expected one finding for {slug}, got {list(data['terms'])}"
    return matches[0]


def has_term(data: dict, slug: str) -> bool:
    return any(k.endswith(f"#{slug}") for k in data["terms"])


# --------------------------------------------------------------------------- #
# Happy path + resolution (behaviors 3, 4, 8)                                  #
# --------------------------------------------------------------------------- #


def test_resolution_summary_and_exit_code(tmp_path: Path) -> None:
    rc, data = run_json(tmp_path, std_tree(tmp_path))
    s = data["summary"]
    assert s["terms_total"] == 5
    assert s["resolved"] == 3  # working-agent, human_holds, definitions
    assert s["unresolved"] == 2  # requirements-items-llm (arrow), ghost-term
    assert s["result"] == "FAILED"
    assert rc == 1  # Load-bearing: callers gate on the exit code, 1 == some link unresolved


def test_all_resolved_exits_zero(tmp_path: Path) -> None:
    # Every reference lands on a heading anchor -> exit 0.
    root = make_tree(tmp_path, GLOSSARY, {"d.md": "[a](glossary.md#working-agent) [b](glossary.md#human_holds)\n"})
    rc, data = run_json(tmp_path, root)
    assert data["summary"]["result"] == "OK"
    assert rc == 0


def test_section_heading_resolves(tmp_path: Path) -> None:
    # Load-bearing behavior 3: the anchor set is ALL headings, not Definitions terms only,
    # so a link to `#definitions` resolves.
    _rc, data = run_json(tmp_path, std_tree(tmp_path))
    assert T(data, "definitions")["resolved"] is True


def test_arrow_slug_fidelity(tmp_path: Path) -> None:
    # Load-bearing behavior 4: the heading slug keeps the arrow (github_slug fidelity), so a
    # hand-written hyphen-only inbound slug does NOT resolve. Proves the shared slug is used.
    assert github_slug("requirements → items LLM") == "requirements-→-items-llm"
    _rc, data = run_json(tmp_path, std_tree(tmp_path))
    assert T(data, "requirements-items-llm")["resolved"] is False


def test_bold_paragraph_glossary_resolves_nothing(tmp_path: Path) -> None:
    # The pre-migration glossary defines terms as bold paragraphs (not headings); none of
    # the term anchors exist, so the term links are unresolved (the tool's 2.4 evidence).
    bold = (
        "---\nid: glossary\n---\n\n# Glossary\n\n## Governance\n\n```glossary\ngoverns: ../\n```\n\n"
        "## Definitions\n\n**working agent**\nThe agent.\n"
    )
    root = make_tree(tmp_path, bold, {"d.md": "[wa](glossary.md#working-agent)\n"})
    rc, data = run_json(tmp_path, root)
    assert T(data, "working-agent")["resolved"] is False
    assert T(data, "working-agent")["status"] == "unresolved-anchor"
    assert rc == 1


# --------------------------------------------------------------------------- #
# Reference extraction (behavior 2)                                            #
# --------------------------------------------------------------------------- #


def test_link_forms_all_extracted(tmp_path: Path) -> None:
    # Load-bearing behavior 2: direct and relative (../) forms resolve to the same glossary.
    _rc, data = run_json(tmp_path, std_tree(tmp_path))
    files_for_wa = {r["file"] for r in T(data, "working-agent")["references"]}
    # direct (refs.md) + relative ../glossary.md (diagrams/sys.md) both counted
    assert any(f.endswith("refs.md") for f in files_for_wa)
    assert any(f.endswith("sys.md") for f in files_for_wa)
    # the section anchor linked relatively from the subdir doc resolves too
    assert any(r["file"].endswith("sys.md") for r in T(data, "definitions")["references"])


def test_duplicate_references_on_one_line_dedupe(tmp_path: Path) -> None:
    # Load-bearing behavior 2: two working-agent links share refs.md:2 -> one file:line.
    _rc, data = run_json(tmp_path, std_tree(tmp_path))
    refs = T(data, "working-agent")["references"]
    refs_in_refs_md = [r for r in refs if r["file"].endswith("refs.md")]
    assert refs_in_refs_md == [{"file": refs_in_refs_md[0]["file"], "line": 2, "status": "resolved"}]  # one, line 2
    assert T(data, "working-agent")["reference_count"] == len(refs)


def test_underscore_and_hyphen_slugs(tmp_path: Path) -> None:
    # Load-bearing behavior 2: underscore slugs (human_holds) and hyphenated (working-agent)
    # are both captured verbatim (underscores preserved by github_slug).
    _rc, data = run_json(tmp_path, std_tree(tmp_path))
    assert has_term(data, "human_holds") and T(data, "human_holds")["resolved"] is True
    assert has_term(data, "working-agent")


def test_myglossary_basename_not_matched(tmp_path: Path) -> None:
    # Basename must be exactly glossary.md: `myglossary.md#x` is NOT an inbound reference.
    root = make_tree(tmp_path, GLOSSARY, {"d.md": "[x](myglossary.md#working-agent)\n"})
    _rc, data = run_json(tmp_path, root)
    assert data["terms"] == {}


# --------------------------------------------------------------------------- #
# Scan set / archived skip (behavior 1)                                        #
# --------------------------------------------------------------------------- #


def test_archived_doc_skipped(tmp_path: Path) -> None:
    # Load-bearing behavior 1: skip files whose front matter has archived: true.
    _rc, data = run_json(tmp_path, std_tree(tmp_path))
    assert not has_term(data, "archived-only")
    assert data["files_scanned"] == 3  # glossary.md + refs.md + diagrams/sys.md
    assert not any("archived.md" in f for f in data["files"])


# --------------------------------------------------------------------------- #
# Reporting — scope & detail (behavior 6)                                      #
# --------------------------------------------------------------------------- #


def test_default_scope_lists_resolved_and_unresolved(tmp_path: Path, capsys) -> None:
    grt.main([str(std_tree(tmp_path)), "--glossary", str(tmp_path / "docs" / "glossary.md")])
    out = capsys.readouterr().out
    assert "Resolved (3):" in out
    assert "Unresolved (2):" in out
    assert out.rstrip().endswith("FAILED")
    assert "Files scanned: 3 | Glossaries: 1 | Terms resolved: 3 | Terms unresolved: 2" in out


def test_failures_scope_omits_resolved(tmp_path: Path, capsys) -> None:
    grt.main([str(std_tree(tmp_path)), "--glossary", str(tmp_path / "docs" / "glossary.md"), "--failures"])
    out = capsys.readouterr().out
    assert "Resolved (" not in out
    assert "Unresolved (2):" in out
    assert "ghost-term" in out and "#working-agent" not in out


def test_terms_only_omits_file_lines(tmp_path: Path, capsys) -> None:
    grt.main([str(std_tree(tmp_path)), "--glossary", str(tmp_path / "docs" / "glossary.md"), "--terms-only"])
    out = capsys.readouterr().out
    assert "ghost-term" in out
    assert ".md:" not in out  # no per-reference file:line lines


# --------------------------------------------------------------------------- #
# --verbose context-window math (behavior 6)                                   #
# --------------------------------------------------------------------------- #

# Single-reference docs so exactly ONE verbose block renders (isolating the window math).
# TOP_DOC: the only reference is on line 1; BOTTOM_DOC: the only reference is on line 5.
TOP_DOC = (
    "[first](glossary.md#working-agent) on line one\n"  # 1
    "beta\n"  # 2
    "gamma\n"  # 3
    "delta\n"  # 4
    "epsilon\n"  # 5
)
BOTTOM_DOC = (
    "alpha\n"  # 1
    "beta\n"  # 2
    "gamma\n"  # 3
    "delta\n"  # 4
    "[last](glossary.md#working-agent)\n"  # 5
)


def _verbose_out(tmp_path: Path, capsys, doc: str, *flags: str) -> str:
    root = make_tree(tmp_path, GLOSSARY, {"v.md": doc})
    grt.main([str(root), "--glossary", str(root / "glossary.md"), *flags])
    return capsys.readouterr().out


def test_verbose_n0_quotes_only_reference_line(tmp_path: Path, capsys) -> None:
    out = _verbose_out(tmp_path, capsys, TOP_DOC, "--verbose", "0")
    assert "    1  [first](glossary.md#working-agent) on line one" in out
    assert "    2  beta" not in out  # N=0 -> only the reference's own line


def test_verbose_n1_spans_two_lines_clamped_at_top(tmp_path: Path, capsys) -> None:
    # Load-bearing behavior 6: clamping at the file's start. Reference on line 1, N=1, the
    # window is lines 1 to 2 (a context window spanning two physical lines).
    out = _verbose_out(tmp_path, capsys, TOP_DOC, "--verbose", "1")
    assert "    1  [first](glossary.md#working-agent) on line one" in out
    assert "    2  beta" in out
    assert "    3  gamma" not in out


def test_verbose_default_n3(tmp_path: Path, capsys) -> None:
    # --verbose with no N defaults to 3: reference on line 1 -> window lines 1 to 4 (top clamp).
    out = _verbose_out(tmp_path, capsys, TOP_DOC, "--verbose")
    assert "    4  delta" in out
    assert "    5  epsilon" not in out  # 1+3=4, clamped below line 5


def test_verbose_clamps_at_file_end(tmp_path: Path, capsys) -> None:
    # Load-bearing behavior 6: reference on the last line (5), N=3 -> window lines 2 to 5.
    out = _verbose_out(tmp_path, capsys, BOTTOM_DOC, "--verbose", "3")
    assert "    2  beta" in out
    assert "    5  [last](glossary.md#working-agent)" in out
    assert "    1  alpha" not in out  # 5-3=2, clamped above line 1


# --------------------------------------------------------------------------- #
# Up-front validation / usage errors (behavior 5)                              #
# --------------------------------------------------------------------------- #


def test_help_prints_usage_exit_0_reads_nothing(tmp_path: Path, capsys) -> None:
    # Load-bearing behavior 5 (v2): glossarian_install.sh --check runs `glossarian-gather --help`.
    for flag in ("--help", "-h"):
        rc = grt.main([flag])
        out = capsys.readouterr().out
        assert rc == 0
        assert out.startswith("Usage: glossarian-gather")
        assert "--glossary PATH" in out
    # Help wins over a missing docs root and even over an otherwise-fatal flag conflict.
    assert grt.main([str(tmp_path / "nope"), "--verbose", "--terms-only", "--help"]) == 0
    capsys.readouterr()
    # Negative control: the same argv without --help is a usage error.
    assert grt.main([str(tmp_path / "nope"), "--verbose", "--terms-only"]) == 2


def test_verbose_with_terms_only_is_usage_error() -> None:
    assert grt.main(["--verbose", "--terms-only"]) == 2  # mutually exclusive


def test_invalid_verbose_n_is_usage_error() -> None:
    assert grt.main(["--verbose=-1"]) == 2  # negative
    assert grt.main(["--verbose=foo"]) == 2  # non-integer


def test_preexisting_json_target_exits_2_and_is_not_clobbered(tmp_path: Path) -> None:
    # Load-bearing behavior 5: a pre-existing --json target exits 2 and is never overwritten.
    root = std_tree(tmp_path)
    out = tmp_path / "exists.json"
    out.write_text("ORIGINAL", encoding="utf-8")
    rc = grt.main([str(root), "--glossary", str(root / "glossary.md"), "--json", str(out)])
    assert rc == 2
    assert out.read_text(encoding="utf-8") == "ORIGINAL"  # untouched


def test_json_parent_dir_missing_exits_2(tmp_path: Path) -> None:
    root = std_tree(tmp_path)
    target = tmp_path / "nope" / "sub" / "r.json"
    assert grt.main([str(root), "--glossary", str(root / "glossary.md"), "--json", str(target)]) == 2


# --------------------------------------------------------------------------- #
# JSON shape + --quiet artifact (behaviors 7, 8)                               #
# --------------------------------------------------------------------------- #


def test_json_shape_is_the_machine_contract(tmp_path: Path) -> None:
    # Load-bearing: the JSON shape is the contract for downstream consumers (2.4/5.1, CI).
    _rc, data = run_json(tmp_path, std_tree(tmp_path))
    assert set(data) == {"docs_root", "glossary", "glossaries", "files_scanned", "files", "terms", "summary"}
    assert set(data["summary"]) == {
        "files_scanned",
        "glossaries",
        "terms_total",
        "resolved",
        "unresolved",
        "references_by_status",
        "result",
    }
    term = T(data, "working-agent")
    assert set(term) == {"glossary", "slug", "resolved", "status", "reference_count", "references"}
    assert set(term["references"][0]) == {"file", "line", "status"}
    (ginfo,) = data["glossaries"].values()
    assert set(ginfo) == {"exists", "is_glossary", "anchor_count", "governs", "scope", "error"}
    assert ginfo["governs"] == "../" and ginfo["error"] is None
    # deterministic ordering: terms keys sorted, references sorted by (file, line)
    assert list(data["terms"]) == sorted(data["terms"])
    refs = T(data, "working-agent")["references"]
    assert refs == sorted(refs, key=lambda r: (r["file"], r["line"]))


def test_quiet_writes_json_but_no_stdout(tmp_path: Path, capsys) -> None:
    # Load-bearing: --quiet suppresses all reporting but the --json FILE artifact is written.
    root = std_tree(tmp_path)
    out = tmp_path / "q.json"
    rc = grt.main([str(root), "--glossary", str(root / "glossary.md"), "--quiet", "--json", str(out)])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == "" and captured.err == ""
    assert out.exists()  # artifact still produced


def test_json_to_stdout_replaces_text_report(tmp_path: Path, capsys) -> None:
    root = std_tree(tmp_path)
    grt.main([str(root), "--glossary", str(root / "glossary.md"), "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)  # stdout is JSON, not the text report
    assert data["summary"]["result"] == "FAILED"
    assert "Scanning:" not in out


# --------------------------------------------------------------------------- #
# Path errors + capability boundary                                            #
# --------------------------------------------------------------------------- #


def test_missing_docs_root_exits_2(tmp_path: Path) -> None:
    assert grt.main([str(tmp_path / "nope")]) == 2


def test_missing_glossary_exits_2(tmp_path: Path) -> None:
    root = std_tree(tmp_path)
    assert grt.main([str(root), "--glossary", str(tmp_path / "ghost.md")]) == 2


def test_only_write_is_json_file_inputs_untouched(tmp_path: Path) -> None:
    # Load-bearing capability boundary: the sole write is --json FILE; docs/glossary never
    # modified, and no other files appear.
    root = std_tree(tmp_path)
    before = {p: p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.md"))}
    before_names = sorted(p.name for p in tmp_path.rglob("*"))

    grt.main([str(root), "--glossary", str(root / "glossary.md"), "--quiet"])  # no --json
    assert sorted(p.name for p in tmp_path.rglob("*")) == before_names  # nothing created

    out = tmp_path / "report.json"
    grt.main([str(root), "--glossary", str(root / "glossary.md"), "--quiet", "--json", str(out)])
    assert out.exists()  # the one declared write
    for p, content in before.items():
        assert p.read_text(encoding="utf-8") == content  # every input byte-for-byte unchanged


# --------------------------------------------------------------------------- #
# v3 — path resolution, governed scope, several glossaries                      #
# --------------------------------------------------------------------------- #


def test_docs_prefixed_link_from_subdir_is_missing_glossary(tmp_path: Path) -> None:
    # v3: paths resolve relative to the linking file, as GitHub does. From docs/diagrams/,
    # `docs/glossary.md` names docs/diagrams/docs/glossary.md, which does not exist.
    root = make_tree(tmp_path, GLOSSARY, {"diagrams/s.md": "[d](docs/glossary.md#working-agent)\n"})
    out = tmp_path / "r.json"
    rc = grt.main([str(root), "--quiet", "--json", str(out)])  # no --glossary filter
    data = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1
    assert T(data, "working-agent")["status"] == "missing-glossary"
    missing = next(g for g in data["glossaries"].values() if not g["exists"])
    assert missing["is_glossary"] is False


def test_link_from_outside_scope_is_out_of_scope(tmp_path: Path) -> None:
    # Load-bearing v3: a glossary governing only its own directory does not cover a sibling.
    glossary = GLOSSARY.replace("governs: ../", "governs: .")
    root = make_tree(tmp_path, glossary, {"in.md": "[a](glossary.md#working-agent)\n"})
    outside = tmp_path / "notes"
    outside.mkdir()
    (outside / "o.md").write_text("[b](../docs/glossary.md#working-agent)\n", encoding="utf-8")
    rc = grt.main([str(tmp_path), "--quiet", "--json", str(tmp_path / "r.json")])
    data = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert rc == 1
    term = T(data, "working-agent")
    statuses = {Path(r["file"]).name: r["status"] for r in term["references"]}
    assert statuses == {"in.md": "resolved", "o.md": "out-of-scope"}
    assert term["status"] == "out-of-scope" and term["resolved"] is False
    assert root.exists()


def test_target_without_glossary_id_is_not_a_glossary(tmp_path: Path) -> None:
    root = make_tree(tmp_path, GLOSSARY.replace("id: glossary", "id: notes"), {"d.md": "[a](glossary.md#x)\n"})
    rc, data = run_json(tmp_path, root)
    assert rc == 1 and T(data, "x")["status"] == "not-a-glossary"


def test_glossary_with_unsafe_or_missing_governs_is_invalid_scope(tmp_path: Path) -> None:
    cases = {
        "escape": GLOSSARY.replace("governs: ../", "governs: ../../../"),
        "absent": GLOSSARY.replace("governs: ../\n", ""),
    }
    for name, glossary in cases.items():
        base = tmp_path / name
        base.mkdir()
        root = make_tree(base, glossary, {"d.md": "[a](glossary.md#working-agent)\n"})
        rc, data = run_json(base, root)
        assert rc == 1
        assert T(data, "working-agent")["status"] == "invalid-scope"
        (ginfo,) = data["glossaries"].values()
        assert ginfo["error"]


def test_two_glossaries_reported_side_by_side(tmp_path: Path, capsys) -> None:
    root = make_tree(tmp_path, GLOSSARY, {"d.md": "[a](glossary.md#working-agent) [k](../kb/glossary.md#kb-term)\n"})
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "glossary.md").write_text(
        GLOSSARY.replace("governs: ../", "governs: .").replace("### working agent", "### kb term"), encoding="utf-8"
    )
    (kb / "n.md").write_text("[k](glossary.md#kb-term) [w](../docs/glossary.md#working-agent)\n", encoding="utf-8")
    rc = grt.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1  # docs/d.md -> kb glossary is out of scope (kb governs only kb/)
    assert "Glossaries: 2" in out
    assert "#kb-term  [out-of-scope]" in out
    assert "n.md:1  [resolved]" in out  # the in-scope reference is tagged under the failing term
    assert root.exists()


def test_glossary_flag_narrows_the_report(tmp_path: Path) -> None:
    root = make_tree(tmp_path, GLOSSARY, {"d.md": "[a](glossary.md#working-agent) [m](../other/glossary.md#x)\n"})
    rc, data = run_json(tmp_path, root)  # run_json passes --glossary docs/glossary.md
    assert rc == 0  # the dangling ../other/glossary.md link is outside the filter
    assert list(data["glossaries"]) == [str(root / "glossary.md")]
    assert data["glossary"] == str(root / "glossary.md")
    out = tmp_path / "all.json"
    assert grt.main([str(root), "--quiet", "--json", str(out)]) == 1  # no filter: everything is checked
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["glossaries"] == 2


def test_repo_root_override_bounds_scope(tmp_path: Path) -> None:
    # Without a .git the scope cannot be bounded (invalid-scope); --repo-root supplies the bound.
    root = tmp_path / "loose" / "docs"
    root.mkdir(parents=True)
    (root / "glossary.md").write_text(GLOSSARY, encoding="utf-8")
    (root / "d.md").write_text("[a](glossary.md#working-agent)\n", encoding="utf-8")
    if grt.scope.find_repo_root(root) is None:
        assert grt.main([str(root), "--quiet"]) == 1
    assert grt.main([str(root), "--repo-root", str(tmp_path / "loose"), "--quiet"]) == 0
    assert grt.main([str(root), "--repo-root", str(tmp_path / "nope"), "--quiet"]) == 2
