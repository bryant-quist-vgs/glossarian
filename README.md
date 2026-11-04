# glossarian

Parse, model, lint, and link-check a deterministically-structured, GitHub-anchor-faithful
markdown glossary. A small, **stdlib-only** package built on **one parser** and **one slug**,
exposed through several faces so "structurally compliant," "the slug GitHub emits," and "this
inbound link resolves" can never drift apart.

## Writing a compliant glossary

`GLOSSARIAN_SPEC.md` is the distributable, tool-accurate specification for authors and agents
that need to produce a glossary and docs tree that pass both tools. `examples/tally/` is a
small doc set built from that spec alone (task prompt in `examples/tally/TASK.md`); it passes
both tools unmodified.

## Modules

| Module | Role | API / CLI |
|---|---|---|
| **`github_slug`** | The GitHub heading-anchor slug (matches `github-slugger`). One definition, shared everywhere. | `github_slug(text) -> str` |
| **`model`** | The structural parse. Records what the document *is* — front matter, fence-aware headings, `## Definitions` as typed term/stray blocks. Parse-only; no validity judgment. | `parse(text) -> GlossaryModel` |
| **`scope`** | The **governed-scope rules**. Resolves a glossary's `governs:` declaration and enforces that no scope escapes the repository root or excludes its glossary. | `resolve_scope(path, governs)` |
| **`glossary_format_check`** | The **linter / CI guard**. Applies the canonical-structure rules to the model, including the Governance scope and reserved targets. | `validate(text)` · `glossarian-check` |
| **`gather_reference_terms`** | The **inbound-link resolver**. Scans a docs tree for `glossary.md#slug` links, resolves each link's path to the glossary it names, checks the linking file is inside that glossary's scope, and fails when a slug lands on no heading. | `main(argv)` · `glossarian-gather` |
| **`glossary_template`** | Writes a blank, compliant glossary to a new file. | `glossarian-template` |
| **`glossary_fix`** | Repairs the trivial issues the linter marks as fixable. | `glossarian-fix` |

The two checks are complements: `glossary_format_check` validates the glossary's own *shape*;
`gather_reference_terms` validates that the rest of the docs *link into it correctly*. Both
compute anchors via the same `model` + `github_slug` and scope via the same `scope`, so a
link "resolves" by exactly the machinery that decides a term is parseable and a glossary is
safely scoped.

## Why it's a package (and why it's standalone)

The glossary is a source-of-truth doc shape that two consumers must agree on:

1. a **standalone linter / CI guard** any project can run when its glossary changes, and
2. **Sedric's runtime glossary query tool** (`contracts.15`), which builds a semantic
   term/alias index over the *same* parse.

If those used two parsers they would drift — "structurally compliant" would stop meaning
"parseable by Sedric." So the parser is single-sourced here: the linter and link-checker ship
today; the semantic index layers on `model` later, without a second parser. The package began
life as a uv-workspace member of the Sedric repo and graduated to this repository on
2026-10-18 once a second consumer (`microservice_relation_mapping`) appeared. It carries no
Sedric dependency.

## Install the commands on PATH

The supported way to run the tools from any directory in any repository is the PATH-shim
installer. It writes four small shims (`glossarian-check`, `glossarian-gather`,
`glossarian-template`, `glossarian-fix`) into `~/.local/bin` that run the console scripts
out of this checkout via `uv`, so `git pull` is the upgrade path.

```bash
bash ~/bryant_repos/glossarian/glossarian_install.sh          # install (or repair) the shims
bash ~/bryant_repos/glossarian/glossarian_install.sh --check  # run each shim with --help
```

`--prefix DIR` chooses another bin directory, `--uninstall` removes only the shims this
installer wrote (marked `# managed-by: glossarian-install`), and `--dry-run` shows what would
happen. The installer never overwrites an unmarked file. Requirements at run time: `uv` on
PATH and a Python ≥ 3.14 visible to it; the shims never exec `python3` directly. Full
semantics: `glossarian_install_contract.md`. Hermetic suite: `bash glossarian_install_test.sh`.

The installer embeds this checkout's absolute path. If you move the checkout, re-run the
installer; `--check` reports the breakage until you do.

## CLI

All tools share the exit-code convention **`0` = clean · `1` = read OK but check failed ·
`2` = bad input/usage** (the exit code is the load-bearing signal; the text report is for
humans). All accept `-h` / `--help`.

### `glossarian-check` — validate glossary structure

```bash
glossarian-check                      # defaults to docs/glossary.md
glossarian-check docs/glossary.md
glossarian-check docs/glossary.md --quiet   # exit code only, no output
glossarian-check docs/glossary.md --repo-root .   # bound the governs scope explicitly
```

Checks YAML front matter (`id: glossary`), a single `# Glossary` H1, the five required `##`
sections in canonical order (`Governance`, `Definitions`, `Confusable Pairs`, `Renames and
deprecated terms`, `Reserved Targets`), the `## Governance` field block's `governs:` scope
(a relative directory that exists, never escapes the repository root, and contains the
glossary), the definition-entry shape under `## Definitions` (a `###` term heading + optional
field block + body + blank-line terminator, no duplicate slugs), and reserved targets (every
`reserved-for` value names a `reserved-for-target: true` term that has a row under
`## Reserved Targets`). Read-only. When a violation is one `glossarian-fix` can repair, the
report prints the command and what it would change.

### `glossarian-gather` — resolve inbound `glossary.md#slug` links

```bash
glossarian-gather                     # scan docs/ (every glossary the links name)
glossarian-gather docs/ --glossary docs/glossary.md   # report only links to that glossary
glossarian-gather --failures          # list only the unresolved terms
glossarian-gather --failures --verbose 3   # + 3 lines of source context per reference
glossarian-gather --terms-only        # term names only, no file:line lines
glossarian-gather --json report.json  # write findings JSON (never overwrites)
glossarian-gather --quiet             # exit code only
```

Recursively scans a docs tree for inbound `glossary.md#<slug>` fragment links, resolves each
link's path **relative to the file holding it** (as GitHub does) to find the glossary it
names, requires the linking file to lie inside the scope that glossary **governs**, skips
files whose front matter has `archived: true`, builds the valid anchor set from **every**
heading in that glossary, and exits `1` if any reference fails. Each reference gets a status:
`resolved`, `missing-glossary`, `not-a-glossary`, `invalid-scope`, `out-of-scope`, or
`unresolved-anchor`. Several glossaries may coexist in one tree.

| Flag | Effect |
|---|---|
| `docs_root` (positional) | Directory to scan. Default `docs/`. |
| `--glossary PATH` | Report only references that resolve to this glossary file. Default: all. |
| `--repo-root DIR` | Repository root a `governs` scope may not escape. Default: nearest `.git`. |
| `--failures` | *Scope:* list only unresolved terms (omit the resolved listing). |
| `--terms-only` | *Detail:* term names only, no per-reference `file:line`. Mutually exclusive with `--verbose`. |
| `--verbose [N]` | *Detail:* under each reference, quote `N` source lines before/after (clamped; default `3`). Mutually exclusive with `--terms-only`. |
| `--json [FILE]` | Emit findings as JSON — to stdout (no FILE) or to a never-overwritten FILE. |
| `--debug` | Trace files/refs/resolutions to stderr. |
| `--quiet` | Suppress all stdout/stderr; rely on the exit code (a `--json FILE` artifact is still written). |

The JSON shape (`docs_root`, `glossary`, `glossaries`, `files_scanned`, `files`, `terms`
keyed `<glossary>#<slug>` with per-reference `status`, `summary`) is the machine contract for
downstream consumers (evidence capture, CI).

### `glossarian-template` — start a new glossary

```bash
glossarian-template docs/glossary.md              # governs: ../ (the repository root)
glossarian-template kb/glossary.md --governs .    # governs only its own directory
```

Writes a blank, fully compliant glossary (front matter, the five sections, a `governs`
block, one placeholder term, header-only tables) that passes `glossarian-check` as written.
Refuses to overwrite an existing path (exit 2).

### `glossarian-fix` — repair trivial issues

```bash
glossarian-fix docs/glossary.md --dry-run   # show what would change
glossarian-fix docs/glossary.md             # apply, then re-check
```

Repairs exactly the issues `glossarian-check` marks `fixable:` — a missing blank line before
a `###` heading, a mis-cased required section heading, a missing Confusable Pairs / Renames /
Reserved Targets section (placeholder body), a `see:` or `reserved-for:` written as a term
instead of its slug, and a missing `is_source_of_truth: true`. Rewrites the file in place,
atomically, only when a repair applies. Exit `0` when the glossary is valid afterwards, `1`
when violations remain.

### Using the tools from another repository

Once the shims are installed, a consumer's `Makefile` or pre-commit hook calls the bare names:

```make
docs-lint:
	glossarian-check docs/glossary.md
	glossarian-gather docs/
```

Without the shims, the equivalent one-off invocation is
`uv run --project ~/bryant_repos/glossarian --no-dev glossarian-check docs/glossary.md`.

## Python API

```python
from glossarian import parse, validate, github_slug

model = parse(open("docs/glossary.md").read())          # GlossaryModel (structure only)
violations, warnings, count = validate(model_text)       # linter policy over the model
anchor = github_slug("requirements → items LLM")         # 'requirements-→-items-llm'

# The link-resolver is driven through its main() (argv in, exit code out):
from glossarian import gather_reference_terms
rc = gather_reference_terms.main(["docs/", "--glossary", "docs/glossary.md", "--quiet"])
```

## Layout

```
src/glossarian/
  github_slug.py               # shared GitHub-anchor slug
  model.py                     # structural parse -> GlossaryModel
  scope.py                     # governs: resolution + repository-root containment
  glossary_format_check.py     # linter rules over the model (+ main)
  gather_reference_terms.py    # inbound glossary.md#slug link resolver (+ main)
  glossary_template.py         # blank compliant glossary writer (+ main)
  glossary_fix.py              # trivial-issue repairer (+ main)
  cli.py                       # glossarian-check / -gather / -template / -fix entry points
tests/                         # one test module per source module
contracts/                     # auditable-script contracts (one per module)
glossarian_install.sh          # PATH-shim installer (+ _contract.md, _test.sh)
pyproject.toml                 # stdlib-only; hatchling; ruff; mypy; console scripts
```

## Development

```bash
make check            # test + lint + format check + typecheck
make test             # uv run pytest
make lint             # ruff check + ruff format --check
make typecheck        # mypy --strict over src/
make install-test     # the installer's hermetic bash suite
```

Every module is an **auditable script**: it ships with a natural-language contract in
`contracts/<module>_contract.md` (the authoritative description of inputs, outputs, behaviors,
and the declared capability surface) and a test module in `tests/test_<module>.py`. The
modules are stdlib-only and perform no network, subprocess, or environment access; the single
declared filesystem write in the whole package is `gather_reference_terms`' optional,
never-overwriting `--json FILE`.
