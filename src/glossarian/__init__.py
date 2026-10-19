"""glossarian — parse, model, and lint a deterministically-structured markdown glossary.

The shared parser for the "compliant glossary" doc shape. `model.parse` turns glossary
text into a structural model; `glossary_format_check.validate` lints that model against
the canonical structure; `github_slug` is the GitHub-anchor-faithful slug both rely on.

One parser, two consumers: the standalone linter / CI guard here, and (incrementally)
Sedric's runtime glossary query tool, which layers a semantic term/alias index over the
same model so "structurally compliant" and "parseable by Sedric" cannot diverge.
"""

from __future__ import annotations

from glossarian.github_slug import github_slug
from glossarian.glossary_format_check import validate
from glossarian.model import GlossaryModel, Line, StrayBlock, TermBlock, parse

__all__ = [
    "GlossaryModel",
    "Line",
    "StrayBlock",
    "TermBlock",
    "github_slug",
    "parse",
    "validate",
]
