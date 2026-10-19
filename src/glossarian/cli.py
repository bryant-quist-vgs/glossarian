"""glossarian.cli — console entry points for the standalone tools.

`glossarian-check [PATH] [--quiet]` validates a glossary's structure (defaults to
`docs/glossary.md`), exiting 0/1/2 — the CI / pre-commit guard.
`glossarian-gather [DOCS_ROOT] [...]` resolves inbound `glossary.md#slug` links against
the glossary's heading anchors, exiting 0/1/2. Future generators get their entry points
here too.
"""

from __future__ import annotations

import sys

from glossarian import gather_reference_terms, glossary_format_check


def check() -> None:
    """Entry point for `glossarian-check`: validate a glossary file."""
    raise SystemExit(glossary_format_check.main(sys.argv[1:]))


def gather() -> None:
    """Entry point for `glossarian-gather`: resolve inbound glossary links."""
    raise SystemExit(gather_reference_terms.main(sys.argv[1:]))
