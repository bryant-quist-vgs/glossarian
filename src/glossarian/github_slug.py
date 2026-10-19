"""github_slug — GitHub heading-anchor slug, shared across glossarian.

A tiny single-purpose function: compute the fragment anchor GitHub auto-generates
for a markdown heading, matching `github-slugger` (the algorithm GitHub itself uses).
`model.py` uses it to compute a slug per term heading; `glossary_format_check.py`
relies on those slugs (duplicate detection) and the future `gather_reference_terms`
matches inbound `glossary.md#slug` links against them. One definition, no drift.

Built against contract v3 (relocated into the glossarian package; behavior unchanged).
Companion contract: contracts/github_slug_contract.md
Tests:              tests/test_github_slug.py
"""

from __future__ import annotations

import re

# Characters github-slugger strips: ASCII punctuation EXCEPT hyphen (`-`) and underscore
# (`_`), plus the Unicode General Punctuation (U+2000-U+206F) and Supplemental
# Punctuation (U+2E00-U+2E7F) blocks (em-dash, en-dash, bullet, ellipsis, smart quotes).
# Spaces are handled separately (each becomes a hyphen). Characters OUTSIDE the removal
# set are kept and lowercased — including the Arrows block (U+2192) and Mathematical
# Operators (U+2265), which github-slugger does NOT strip, and accented letters. (We also
# strip ASCII control chars / DEL, a harmless superset on real heading input.) The Unicode
# ranges are written as \u escapes so the source stays pure-ASCII (no ambiguous literals).
_STRIP = re.compile(r"[\x00-\x1f!-,./:-@\[-\^`{-~\x7f\u2000-\u206f\u2e00-\u2e7f]")
_HTML_TAG = re.compile(r"<[^>]+>")


def github_slug(text: str) -> str:
    """Return GitHub's auto-generated anchor slug for a heading's text.

    Mirrors github-slugger's base slug (the per-heading transform, *not* its
    duplicate `-1`/`-2` disambiguation, which is the caller's concern):

      1. strip inline HTML tags,
      2. remove the punctuation set above — ASCII punctuation (hyphen and underscore
         survive) plus the Unicode General + Supplemental Punctuation blocks,
      3. replace each space with a hyphen (runs are NOT collapsed: `a  b` -> `a--b`),
      4. lowercase.

    Characters outside the removal set are preserved and lowercased — the Arrows block,
    Mathematical Operators, and accented letters — so `requirements -> items` keeps its
    arrow, while the General/Supplemental Punctuation blocks ARE stripped (an em-dash
    surrounded by spaces collapses to a double hyphen).
    """
    s = _HTML_TAG.sub("", text)
    s = _STRIP.sub("", s)
    s = s.replace(" ", "-")
    return s.lower()
