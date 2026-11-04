"""glossarian.cli — console entry points for the standalone tools.

`glossarian-check [PATH] [--repo-root DIR] [--quiet]` validates a glossary's structure
(defaults to `docs/glossary.md`), exiting 0/1/2 — the CI / pre-commit guard.
`glossarian-gather [DOCS_ROOT] [...]` resolves inbound `glossary.md#slug` links against the
glossaries they name and the scopes those govern, exiting 0/1/2.
`glossarian-template PATH [--governs REL]` writes a blank, compliant glossary to a new file.
`glossarian-fix PATH [--dry-run]` repairs the trivial issues the check marks as fixable.
"""

from __future__ import annotations

import sys

from glossarian import gather_reference_terms, glossary_fix, glossary_format_check, glossary_template


def check() -> None:
    """Entry point for `glossarian-check`: validate a glossary file."""
    raise SystemExit(glossary_format_check.main(sys.argv[1:]))


def gather() -> None:
    """Entry point for `glossarian-gather`: resolve inbound glossary links."""
    raise SystemExit(gather_reference_terms.main(sys.argv[1:]))


def template() -> None:
    """Entry point for `glossarian-template`: write a blank compliant glossary."""
    raise SystemExit(glossary_template.main(sys.argv[1:]))


def fix() -> None:
    """Entry point for `glossarian-fix`: repair trivial glossary issues."""
    raise SystemExit(glossary_fix.main(sys.argv[1:]))
