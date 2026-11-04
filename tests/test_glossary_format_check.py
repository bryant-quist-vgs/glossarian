"""test_glossary_format_check — tests for glossarian.glossary_format_check, contract v6.

v6 coverage (appended at the end of the file):
  - Rule 4 (v6): `## Reserved Targets` is the fifth required section.
  - Rule 4b: the Governance field block — missing block, missing `governs`, unknown key,
    malformed value (absolute / home-relative / URL), and the filesystem half: a scope that
    escapes the repository root, one that excludes the glossary, a missing directory, and the
    `--repo-root` override; the pure-text API skips the filesystem half.
  - Rule 5c/5d (v6): `reserved-for` is open — it must name a `reserved-for-target: true`
    term; `reserved-for-target` must be true/false; each target needs a row under
    `## Reserved Targets` and each row must name a target.
  - Rule 7 (v6): fixable violations carry `fix`, the report prints the `glossarian-fix`
    hint and the summary count, and non-fixable ones do not.

Coverage (one test or more per contract rule / load-bearing behavior). The linter is pure
*policy* over the glossarian.model parse:
  - Happy path: a fully compliant glossary validates clean (exit 0, entry count).
  - Rule 2 (front matter): missing block, unterminated block, wrong id, and the
    is_source_of_truth recommendation as a non-fatal warning.
  - Rule 3 (H1): missing, duplicate, and mis-named top-level heading.
  - Rule 4 (sections): missing section, casing mismatch, out-of-order sections, extra
    sections permitted, and a duplicate required section flagged (F3).
  - Rule 5 (definition shape, v4 relaxed): bold-paragraph entry, empty body, missing blank
    line between blocks, wrong heading level, empty Definitions section, AND a multi-paragraph
    body with blank lines + a table validating clean (no longer flagged as stray).
  - Rule 5b (v4): a polluted term heading — parenthetical qualifier, inline alias, co-defined
    slash, arrow — is rejected; a clean term-only heading is not.
  - Rule 5c (v4): the ```glossary``` field block — unknown key rejected, invalid reserved-for
    rejected, dangling `see` rejected, valid block accepted.
  - Rule 6 (slugs): duplicate term-heading slug, via the shared github_slug (the
    exhaustive slug cases live in test_github_slug.py).
  - Behavior 7: collects all violations rather than stopping at the first.
  - Fence-awareness: a `###` inside a fenced code block is not treated as a heading.
  - Capability boundary: exit 2 on missing/unreadable path; the script never writes.
  - Behavior 8 (v5): -h/--help prints usage to stdout, exits 0, reads nothing (load-bearing
    for the installer's --check).

Run with:  uv run pytest tests/test_glossary_format_check.py
"""

from __future__ import annotations

from pathlib import Path

from glossarian import glossary_format_check as gfc

# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

VALID = """\
---
id: glossary
is_source_of_truth: true
---

# Glossary

Intro prose pointing readers at the sections below.

## Governance

```glossary
governs: ../
```

Rules about how the glossary is maintained.

## Definitions

### working agent
The write-capable agent that performs an item's work.

### human_holds
A completability gate value; the human holds the token.

## Confusable Pairs

| Term | Confusable with | Distinction |
|---|---|---|
| a | b | c |

## Renames and deprecated terms

| Avoid | Use | Why |
|---|---|---|
| x | y | z |

## Reserved Targets

None.
"""

GOVERNANCE_BLOCK = "```glossary\ngoverns: ../\n```\n\n"


def repo_glossary(tmp_path: Path, text: str = VALID) -> Path:
    """Write `text` as <tmp>/repo/docs/glossary.md inside a fake repository (a `.git` dir)."""
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    docs = tmp_path / "repo" / "docs"
    docs.mkdir()
    p = docs / "glossary.md"
    p.write_text(text, encoding="utf-8")
    return p


def msgs(text: str) -> list[str]:
    """Violation messages from validate(), order-independent for assertions."""
    violations, _warnings, _count = gfc.validate(text)
    return [v.msg for v in violations]


def warns(text: str) -> list[str]:
    _v, warnings, _c = gfc.validate(text)
    return warnings


def has(substr: str, items: list[str]) -> bool:
    return any(substr in it for it in items)


# --------------------------------------------------------------------------- #
# Happy path                                                                   #
# --------------------------------------------------------------------------- #


def test_valid_glossary_is_clean() -> None:
    violations, warnings, count = gfc.validate(VALID)
    assert violations == []
    assert warnings == []
    assert count == 2  # two ### term entries; table rows in other sections ignored


def test_valid_glossary_main_exit_zero(tmp_path: Path) -> None:
    assert gfc.main([str(repo_glossary(tmp_path))]) == 0


# --------------------------------------------------------------------------- #
# Rule 2 — front matter                                                        #
# --------------------------------------------------------------------------- #


def test_missing_frontmatter() -> None:
    text = VALID.split("---\n", 2)[2]  # drop the leading front-matter block
    assert has("missing front matter", msgs(text))


def test_unterminated_frontmatter() -> None:
    text = "---\nid: glossary\n# Glossary\n"  # no closing ---
    assert has("unterminated front matter", msgs(text))


def test_wrong_id_is_violation() -> None:
    text = VALID.replace("id: glossary", "id: not-glossary")
    assert has("id: glossary", msgs(text))


def test_missing_is_source_of_truth_is_warning_not_violation() -> None:
    text = VALID.replace("is_source_of_truth: true\n", "")
    # Load-bearing: rule 2 says is_source_of_truth absence is advisory, not fatal.
    assert msgs(text) == []
    assert has("is_source_of_truth", warns(text))


# --------------------------------------------------------------------------- #
# Rule 3 — top-level heading                                                   #
# --------------------------------------------------------------------------- #


def test_missing_h1() -> None:
    text = VALID.replace("# Glossary\n", "", 1)
    assert has("missing top-level `# Glossary`", msgs(text))


def test_multiple_h1() -> None:
    text = VALID.replace("## Governance", "# Glossary\n\n## Governance", 1)
    assert has("more than one top-level heading", msgs(text))


def test_wrong_h1_name() -> None:
    text = VALID.replace("# Glossary", "# Glosary", 1)
    assert has("must be `# Glossary`", msgs(text))


# --------------------------------------------------------------------------- #
# Rule 4 — required sections, casing, order                                    #
# --------------------------------------------------------------------------- #


def test_missing_required_section() -> None:
    text = VALID.replace("## Governance\n\n" + GOVERNANCE_BLOCK + "Rules about how the glossary is maintained.\n\n", "")
    assert has("missing required section `## Governance`", msgs(text))


def test_section_casing_mismatch_is_violation() -> None:
    # The live glossary uses `## Confusable pairs` (lowercase p); the spec requires `Pairs`.
    text = VALID.replace("## Confusable Pairs", "## Confusable pairs")
    assert has("missing required section `## Confusable Pairs`", msgs(text))


def test_wrong_section_order() -> None:
    # Swap Governance and Definitions so the required four appear out of canonical order.
    text = VALID.replace(
        "## Governance\n\n" + GOVERNANCE_BLOCK + "Rules about how the glossary is maintained.\n\n## Definitions",
        "## Definitions",
    )
    text = text.replace(
        "## Confusable Pairs",
        "## Governance\n\n" + GOVERNANCE_BLOCK + "Moved out of order.\n\n## Confusable Pairs",
    )
    assert has("malformed section order", msgs(text))


def test_extra_section_is_allowed() -> None:
    # An additional ## section interspersed is not a violation (required-present policy).
    text = VALID.replace(
        "## Confusable Pairs",
        "## Reserved for sister projects\n\nNeighbouring vocab.\n\n## Confusable Pairs",
    )
    assert msgs(text) == []


def test_duplicate_required_section_flagged() -> None:
    # F3 fix: a repeated required `##` section must be flagged, not silently tolerated.
    text = VALID.replace(
        "## Confusable Pairs",
        "## Definitions\n\n### dupe\nbody.\n\n## Confusable Pairs",
    )
    assert has("duplicate required section `## Definitions`", msgs(text))


# --------------------------------------------------------------------------- #
# Rule 5 — definition-entry shape                                              #
# --------------------------------------------------------------------------- #


def test_bold_paragraph_entry_rejected() -> None:
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "**working agent**\nThe write-capable agent that performs an item's work.",
    )
    assert has("bold-paragraph entry", msgs(text))


def test_empty_definition_body() -> None:
    text = VALID.replace(
        "### human_holds\nA completability gate value; the human holds the token.",
        "### human_holds\n",
    )
    assert has("empty definition body", msgs(text))


def test_missing_blank_line_between_entries() -> None:
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.\n\n### human_holds",
        "### working agent\nThe write-capable agent that performs an item's work.\n### human_holds",
    )
    assert has("missing blank line", msgs(text))


def test_wrong_term_heading_level() -> None:
    text = VALID.replace("### working agent", "#### working agent")
    assert has("must be level `###`", msgs(text))


def test_empty_definitions_section() -> None:
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.\n\n"
        "### human_holds\nA completability gate value; the human holds the token.\n\n",
        "",
    )
    assert has("no definition entries", msgs(text))


# --------------------------------------------------------------------------- #
# Rule 6 — slugs                                                               #
# --------------------------------------------------------------------------- #


def test_duplicate_term_slug() -> None:
    # "working agent" and "working-agent" both slug to "working-agent".
    text = VALID.replace(
        "### human_holds\nA completability gate value; the human holds the token.",
        "### working-agent\nA collision with the working agent slug.",
    )
    assert has("duplicate term-heading slug 'working-agent'", msgs(text))


def test_slug_is_the_shared_library_function() -> None:
    # F2: the slug used to build term-heading slugs is the shared github_slug, not a local
    # copy, so it cannot drift from gather_reference_terms (2.2). The slug is consumed in
    # glossarian.model now; assert the wiring there plus a representative case.
    from glossarian import model
    from glossarian.github_slug import github_slug

    assert model.github_slug is github_slug
    assert github_slug("working agent") == "working-agent"


# --------------------------------------------------------------------------- #
# Rule 5 (v4 relaxed body) — multi-paragraph / table bodies are clean          #
# --------------------------------------------------------------------------- #


def test_relaxed_body_with_blank_lines_and_table_is_clean() -> None:
    # Load-bearing (rule 5, v4): a term body may span blank lines and contain a table; the
    # second paragraph and the table rows are body, NOT orphan/stray violations.
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\nThe write-capable agent that performs an item's work.\n\n"
        "A second paragraph after a blank line.\n\n| a | b |\n|---|---|\n| 1 | 2 |",
    )
    assert msgs(text) == []


def test_field_block_only_no_prose_is_empty_body() -> None:
    # body_line_count excludes the field block (model v2), so a field-block-only entry
    # still flags as empty-bodied (rule 5).
    text = VALID.replace(
        "### human_holds\nA completability gate value; the human holds the token.",
        "### human_holds\n```glossary\naliases: hold\n```",
    )
    assert has("empty definition body", msgs(text))


def test_mid_section_bold_entry_rejected() -> None:
    # Load-bearing (F1 regression guard): an unconverted `**bold**` entry sitting BETWEEN two
    # converted `###` entries — the partial-migration state — must be flagged, not silently
    # absorbed into the preceding definition's body. This is the relaxed-body regression the
    # assessment caught; the test pins that the detection is restored.
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\nThe write-capable agent that performs an item's work.\n\n"
        "**leftover unconverted entry**\nNever converted to a heading during migration.",
    )
    msg = msgs(text)
    assert has("unexpected bold-paragraph entry where a `###` term heading was expected", msg)
    # the bold entry is not counted as a real definition
    _v, _w, count = gfc.validate(text)
    assert count == 2


def test_bold_first_body_line_not_flagged() -> None:
    # A bold lead on the first body line is legitimate body, not a stray (no false positive).
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\n**Bold lead** then prose, one paragraph.",
    )
    assert not has("where a `###` term heading was expected", msgs(text))


# --------------------------------------------------------------------------- #
# Rule 5b (v4) — term heading is the canonical term only                       #
# --------------------------------------------------------------------------- #


def test_heading_with_parenthetical_qualifier_rejected() -> None:
    # `### Verification (the act)` slugs to `verification-the-act`, not `#verification`.
    text = VALID.replace("### working agent", "### working agent (the act)")
    assert has("term heading must contain only the canonical term", msgs(text))


def test_heading_with_inline_alias_rejected() -> None:
    text = VALID.replace("### working agent", "### working agent (alias: **doer**)")
    assert has("term heading must contain only the canonical term", msgs(text))


def test_heading_with_codefined_slash_rejected() -> None:
    text = VALID.replace("### working agent", "### managed_by / worker")
    assert has("term heading must contain only the canonical term", msgs(text))


def test_heading_with_arrow_rejected() -> None:
    text = VALID.replace("### working agent", "### requirements→items LLM")
    assert has("term heading must contain only the canonical term", msgs(text))


def test_clean_heading_not_flagged() -> None:
    # underscores and hyphens are legitimate (human_holds, capability-grant); not flagged.
    assert not has("term heading must contain only the canonical term", msgs(VALID))


# --------------------------------------------------------------------------- #
# Rule 5c (v4) — the ```glossary``` field block                                #
# --------------------------------------------------------------------------- #


def _with_field_block(body: str) -> str:
    return VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        f"### working agent\n```glossary\n{body}\n```\nThe write-capable agent that performs an item's work.",
    )


def test_valid_field_block_is_clean() -> None:
    text = _with_field_block("aliases: doer\nshort: completes one item end to end\nconfusable: assessor LLM")
    assert msgs(text) == []


def test_unknown_field_key_rejected() -> None:
    text = _with_field_block("definition: not an allowed key")
    assert has("unknown field-block key `definition`", msgs(text))


def test_reserved_for_must_name_a_reserved_target() -> None:
    # v6: `reserved-for` is open, but its value must be the slug of a reserved-target term.
    text = _with_field_block("reserved-for: martians")
    assert has("`reserved-for: martians` in term `working agent` does not name a reserved target", msgs(text))


def test_reserved_for_resolving_to_target_accepted() -> None:
    text = _with_field_block("reserved-for: human_holds")
    text = text.replace("### human_holds\n", "### human_holds\n```glossary\nreserved-for-target: true\n```\n").replace(
        "## Reserved Targets\n\nNone.", RESERVED_TABLE + "| [human_holds](glossary.md#human_holds) | gate | | |"
    )
    assert not has("reserved", msgs(text))


RESERVED_TABLE = "## Reserved Targets\n\n| Target | What it is | Local | Remote |\n|---|---|---|---|\n"


def test_dangling_see_rejected() -> None:
    text = _with_field_block("see: nonexistent-term")
    assert has("does not resolve", msgs(text))


def test_see_resolves_to_existing_slug() -> None:
    # human_holds is a real term in VALID; `see: human_holds` resolves to its slug.
    text = _with_field_block("see: human_holds")
    assert not has("does not resolve", msgs(text))


def test_unterminated_field_block_rejected() -> None:
    # F3: an unclosed ```glossary``` fence gets a specific diagnostic at the fence line,
    # not just a misleading downstream "empty definition body".
    text = VALID.replace(
        "### working agent\nThe write-capable agent that performs an item's work.",
        "### working agent\n```glossary\naliases: doer\nthis fence is never closed",
    )
    assert has("unterminated ```glossary``` field block", msgs(text))


# --------------------------------------------------------------------------- #
# Behavior 7 — collect all violations                                          #
# --------------------------------------------------------------------------- #


def test_collects_multiple_violations() -> None:
    text = VALID.replace("id: glossary", "id: wrong").replace("### working agent", "#### working agent")
    found = msgs(text)
    assert has("id: glossary", found)
    assert has("must be level `###`", found)
    assert len(found) >= 2  # not fail-fast


# --------------------------------------------------------------------------- #
# Fence-awareness                                                              #
# --------------------------------------------------------------------------- #


def test_heading_inside_code_fence_ignored() -> None:
    # A fenced `## Definitions` / `### term` example must not be read as real headings.
    # Without fence-awareness the fake `## Definitions` in Governance would shadow the
    # real section and break entry counting, so this is a true discriminator.
    text = VALID.replace(
        "Rules about how the glossary is maintained.",
        "Example of the format:\n\n```\n## Definitions\n### sample term\nsample body\n```",
    )
    violations, _w, count = gfc.validate(text)
    assert violations == []  # fenced lines are inert
    assert count == 2  # the real ## Definitions still has exactly two entries


# --------------------------------------------------------------------------- #
# Capability boundary — exit codes and read-only                              #
# --------------------------------------------------------------------------- #


def test_missing_file_exit_2(tmp_path: Path) -> None:
    assert gfc.main([str(tmp_path / "nope.md")]) == 2


def test_directory_path_exit_2(tmp_path: Path) -> None:
    # A directory is unreadable as a file -> exit 2, not a crash.
    assert gfc.main([str(tmp_path)]) == 2


def test_violations_exit_one(tmp_path: Path) -> None:
    p = tmp_path / "g.md"
    p.write_text("# Glossary\n", encoding="utf-8")  # missing front matter + sections
    assert gfc.main([str(p)]) == 1


def test_script_never_writes(tmp_path: Path) -> None:
    # Load-bearing capability boundary: validator is read-only — no file output.
    p = repo_glossary(tmp_path)
    before_listing = sorted(str(x) for x in tmp_path.rglob("*"))
    before_content = p.read_text(encoding="utf-8")
    gfc.main([str(p)])
    gfc.main([str(p), "--quiet"])
    assert sorted(str(x) for x in tmp_path.rglob("*")) == before_listing  # no new files
    assert p.read_text(encoding="utf-8") == before_content  # input untouched


def test_help_prints_usage_exit_0_reads_nothing(tmp_path: Path, capsys) -> None:
    # Load-bearing behavior 8: glossarian_install.sh --check runs `glossarian-check --help`.
    for flag in ("--help", "-h"):
        rc = gfc.main([flag])
        out = capsys.readouterr().out
        assert rc == 0
        assert out.startswith("Usage: glossarian-check")
        assert "--quiet" in out
    # Help wins even when a missing path is also given (nothing is read -> not exit 2).
    assert gfc.main([str(tmp_path / "nope.md"), "--help"]) == 0
    capsys.readouterr()
    # Negative control: without the flag the same missing path is exit 2.
    assert gfc.main([str(tmp_path / "nope.md")]) == 2


def test_quiet_suppresses_output(tmp_path: Path, capsys) -> None:
    p = tmp_path / "g.md"
    p.write_text("# Glossary\n", encoding="utf-8")
    rc = gfc.main([str(p), "--quiet"])
    out = capsys.readouterr().out
    assert rc == 1  # still reports failure via exit code
    assert out == ""  # but prints nothing


# --------------------------------------------------------------------------- #
# v6 — Rule 4: the fifth required section                                      #
# --------------------------------------------------------------------------- #


def test_reserved_targets_is_required_and_fixable() -> None:
    text = VALID.replace("\n## Reserved Targets\n\nNone.\n", "")
    violations, _w, _c = gfc.validate(text)
    v = next(v for v in violations if v.code == "section-missing")
    assert "`## Reserved Targets`" in v.msg
    assert v.fix is not None and "append `## Reserved Targets`" in v.fix


def test_reserved_targets_must_be_last_in_order() -> None:
    renames = "## Renames and deprecated terms\n\n| Avoid | Use | Why |\n|---|---|---|\n| x | y | z |\n\n"
    text = VALID.replace(
        renames + "## Reserved Targets\n\nNone.\n",
        "## Reserved Targets\n\nNone.\n\n## Renames and deprecated terms\n\nNone yet.\n",
    )
    assert has("malformed section order", msgs(text))


# --------------------------------------------------------------------------- #
# v6 — Rule 4b: the Governance field block and the `governs` scope             #
# --------------------------------------------------------------------------- #


def codes(text: str, **kw: object) -> list[str]:
    violations, _w, _c = gfc.validate(text, **kw)  # type: ignore[arg-type]
    return [v.code for v in violations]


def test_governance_block_missing_is_violation() -> None:
    text = VALID.replace(GOVERNANCE_BLOCK, "")
    assert "governance-block-missing" in codes(text)


def test_governs_key_missing_is_violation() -> None:
    text = VALID.replace("governs: ../", "scope: ../")
    found = codes(text)
    assert "governs-missing" in found and "governance-key-unknown" in found


def test_governs_absolute_home_and_url_rejected_without_filesystem() -> None:
    for bad in ("/etc", "~/docs", "https://example.com/docs"):
        assert "governs-invalid" in codes(VALID.replace("governs: ../", f"governs: {bad}")), bad
    assert "governs-invalid" not in codes(VALID.replace("governs: ../", "governs: ../../../../../"))  # text API: no fs


def test_governs_escaping_repo_root_rejected_on_disk(tmp_path: Path) -> None:
    # Load-bearing: no glossary may govern above its repository root.
    p = repo_glossary(tmp_path, VALID.replace("governs: ../", "governs: ../../"))
    violations, _w, _c = gfc.validate(p.read_text(encoding="utf-8"), glossary_path=p)
    assert any(v.code == "governs-invalid" and "escapes the repository root" in v.msg for v in violations)
    assert gfc.main([str(p)]) == 1


def test_governs_must_contain_the_glossary(tmp_path: Path) -> None:
    p = repo_glossary(tmp_path)
    (tmp_path / "repo" / "src").mkdir()
    text = VALID.replace("governs: ../", "governs: ../src")
    p.write_text(text, encoding="utf-8")
    violations, _w, _c = gfc.validate(text, glossary_path=p)
    assert any(v.code == "governs-invalid" and "does not contain the glossary" in v.msg for v in violations)


def test_governs_missing_directory_rejected(tmp_path: Path) -> None:
    p = repo_glossary(tmp_path, VALID.replace("governs: ../", "governs: ../nope"))
    assert gfc.main([str(p)]) == 1


def test_governs_dot_and_repo_root_override(tmp_path: Path) -> None:
    # `.` is the glossary's own directory; --repo-root bounds the scope when no .git exists.
    docs = tmp_path / "plain" / "docs"
    docs.mkdir(parents=True)
    p = docs / "glossary.md"
    p.write_text(VALID.replace("governs: ../", "governs: ."), encoding="utf-8")
    assert gfc.main([str(p)]) == 1  # no .git above, no override -> cannot bound the scope
    assert gfc.main([str(p), "--repo-root", str(tmp_path / "plain")]) == 0
    assert gfc.main([str(p), f"--repo-root={tmp_path / 'plain'}"]) == 0


def test_bad_usage_exits_2(tmp_path: Path) -> None:
    p = repo_glossary(tmp_path)
    assert gfc.main([str(p), "--repo-root"]) == 2
    assert gfc.main([str(p), "--bogus"]) == 2
    assert gfc.main([str(p), "extra"]) == 2


# --------------------------------------------------------------------------- #
# v6 — Rule 5d: reserved targets                                               #
# --------------------------------------------------------------------------- #


def _with_target(rows: str, flag: str = "true") -> str:
    text = VALID.replace("### human_holds\n", f"### human_holds\n```glossary\nreserved-for-target: {flag}\n```\n")
    return text.replace("## Reserved Targets\n\nNone.", RESERVED_TABLE + rows)


def test_reserved_target_needs_a_row() -> None:
    assert "reserved-target-no-row" in codes(_with_target(""))


def test_reserved_row_link_or_plain_text_names_target() -> None:
    assert "reserved-target-no-row" not in codes(_with_target("| [gate](glossary.md#human_holds) | g | | |"))
    assert codes(_with_target("| `human_holds` | g | ~/x | https://x |")) == []


def test_reserved_row_naming_non_target_is_violation() -> None:
    text = _with_target(
        "| [human_holds](glossary.md#human_holds) | g | | |\n| [working agent](glossary.md#working-agent) | g | | |"
    )
    assert "reserved-row-unknown" in codes(text)


def test_reserved_for_target_false_is_not_a_target() -> None:
    text = _with_target("", flag="false")
    assert "reserved-target-no-row" not in codes(text)
    assert "field-reserved-for-target-value" in codes(_with_target("", flag="yes"))


def test_reserved_for_term_form_gets_fix_hint() -> None:
    text = _with_target("| [human_holds](glossary.md#human_holds) | g | | |")
    text = text.replace(
        "### working agent\n", "### working agent\n```glossary\nreserved-for: Human_Holds, martians\n```\n"
    )
    violations, _w, _c = gfc.validate(text)
    rf = [v for v in violations if v.code == "field-reserved-for-unresolved"]
    assert len(rf) == 2
    assert any(v.fix and "as the slug `human_holds`" in v.fix for v in rf)  # github_slug form offered
    assert any(v.fix is None for v in rf)  # martians cannot be guessed


# --------------------------------------------------------------------------- #
# v6 — Rule 7: fix hints in the report                                         #
# --------------------------------------------------------------------------- #


def test_fixable_violations_print_fix_command(tmp_path: Path, capsys) -> None:
    text = VALID.replace("## Confusable Pairs", "## Confusable pairs").replace("is_source_of_truth: true\n", "")
    p = repo_glossary(tmp_path, text)
    assert gfc.main([str(p)]) == 1
    out = capsys.readouterr().out
    assert f"fixable: `glossarian-fix {p}` would rename `## Confusable pairs` to `## Confusable Pairs`" in out
    assert "would add `is_source_of_truth: true`" in out
    assert f"2 issues can be repaired automatically: run `glossarian-fix {p}`" in out


def test_non_fixable_violation_has_no_hint(tmp_path: Path, capsys) -> None:
    p = repo_glossary(tmp_path, VALID.replace("### working agent", "### working (agent)"))
    gfc.main([str(p)])
    out = capsys.readouterr().out
    assert "  fixable:" not in out and "can be repaired automatically" not in out
