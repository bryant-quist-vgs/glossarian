"""test_github_slug — tests for glossarian.github_slug, built against contract v3.

Coverage (behavior unchanged from the pre-package v2; only the import path moved):
  - Behavior 1 (base algorithm): spaces->hyphens, lowercase, ASCII punctuation dropped.
  - Behavior 2: hyphen and underscore preserved (identifier-style terms).
  - Behavior 3 (F1 fidelity): github-slugger's actual removal set — Unicode General
    Punctuation (U+2000-U+206F) and Supplemental Punctuation (U+2E00-U+2E7F) are
    STRIPPED (em-dash, en-dash, bullet, ellipsis, smart quotes); characters in other
    blocks — Arrows (`→`), Math Operators (`≥`), accented letters — are PRESERVED.
  - Behavior 4: spaces are not collapsed (`a  b` -> `a--b`).
  - Behavior 5: base slug only — no duplicate `-1` disambiguation.
  - The task-1.1 inbound-slug case table is reproduced verbatim.

Run with:  uv run pytest tests/test_github_slug.py
"""

from __future__ import annotations

from glossarian.github_slug import github_slug as slug

# --- Behaviors 1 & 2: base algorithm, hyphen/underscore preserved (task-1.1 cases) --- #


def test_task_1_1_inbound_slug_cases() -> None:
    assert slug("working agent") == "working-agent"
    assert slug("assessor LLM") == "assessor-llm"
    assert slug("LLM role") == "llm-role"
    assert slug("human_holds") == "human_holds"  # underscore preserved
    assert slug("managed_by") == "managed_by"
    assert slug("llm_with_human_assistance") == "llm_with_human_assistance"
    assert slug("state.json") == "statejson"  # '.' dropped, no separator left


def test_ascii_punctuation_dropped_and_backticks() -> None:
    assert slug("`code` term") == "code-term"
    assert slug("submit_assessment()") == "submit_assessment"
    assert slug("a, b & c?") == "a-b--c"  # punctuation gone; spaces -> hyphens, uncollapsed


# --- Behavior 3 (F1 fidelity): github-slugger's real Unicode removal set --- #


def test_unicode_punctuation_blocks_stripped() -> None:
    # github-slugger strips Unicode General Punctuation (U+2000-U+206F) and Supplemental
    # Punctuation (U+2E00-U+2E7F) — matching real GitHub anchors.
    assert slug("em — dash") == "em--dash"  # em-dash U+2014 stripped
    assert slug("bullet • point") == "bullet--point"  # bullet U+2022 stripped
    assert slug("ellipsis … here") == "ellipsis--here"  # … U+2026 stripped
    assert slug("smart \u2018quote\u2019") == "smart-quote"  # U+2018/U+2019 smart quotes stripped


def test_non_punctuation_unicode_preserved() -> None:
    # Characters OUTSIDE those blocks are kept (and lowercased), as GitHub does.
    assert slug("requirements → items LLM") == "requirements-→-items-llm"  # → U+2192 Arrows
    assert slug("≥ threshold") == "≥-threshold"  # ≥ U+2265 Math Operators
    assert slug("café") == "café"  # Latin-1 accented letter


# --- Behavior 4: spaces not collapsed --- #


def test_spaces_not_collapsed() -> None:
    assert slug("a  b") == "a--b"
    assert slug("a - b") == "a---b"  # existing hyphen kept + two spaces -> hyphens


# --- Behavior 5: base slug only --- #


def test_no_duplicate_suffix_added() -> None:
    # Calling twice yields the same slug; no -1/-2 disambiguation here.
    assert slug("working agent") == slug("working agent") == "working-agent"
