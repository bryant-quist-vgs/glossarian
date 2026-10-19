# glossarian

Parse, model, lint, and link-check a deterministically-structured, GitHub-anchor-faithful
markdown glossary. A small, **stdlib-only** package built on **one parser** and **one slug**,
exposed through several faces so "structurally compliant," "the slug GitHub emits," and "this
inbound link resolves" can never drift apart.

## Modules

| Module | Role | API / CLI |
|---|---|---|
| **`github_slug`** | The GitHub heading-anchor slug (matches `github-slugger`). One definition, shared everywhere. | `github_slug(text) -> str` |
| **`model`** | The structural parse. Records what the document *is* — front matter, fence-aware headings, `## Definitions` as typed term/stray blocks. Parse-only; no validity judgment. | `parse(text) -> GlossaryModel` |
| **`glossary_format_check`** | The **linter / CI guard**. Applies the canonical-structure rules to the model. | `validate(text)` · `glossarian-check` |
| **`gather_reference_terms`** | The **inbound-link resolver**. Scans a docs tree for `glossary.md#slug` links and fails when a slug lands on no glossary heading. | `main(argv)` · `glossarian-gather` |

The two checks are complements: `glossary_format_check` validates the glossary's own *shape*;
`gather_reference_terms` validates that the rest of the docs *link into it correctly*. Both
compute anchors via the same `model` + `github_slug`, so a link "resolves" by exactly the
machinery that decides a term is parseable.

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
installer. It writes two small shims (`glossarian-check`, `glossarian-gather`) into
`~/.local/bin` that run the console scripts out of this checkout via `uv`, so `git pull` is
the upgrade path.

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

Both tools share the exit-code convention **`0` = clean · `1` = read OK but check failed ·
`2` = bad input/usage** (the exit code is the load-bearing signal; the text report is for
humans). Both accept `-h` / `--help`.

### `glossarian-check` — validate glossary structure

```bash
glossarian-check                      # defaults to docs/glossary.md
glossarian-check docs/glossary.md
glossarian-check docs/glossary.md --quiet   # exit code only, no output
```

Checks YAML front matter (`id: glossary`), a single `# Glossary` H1, the four required `##`
sections in canonical order, and the definition-entry shape under `## Definitions` (a `###`
term heading + body + blank-line terminator, no duplicate slugs). Read-only.

### `glossarian-gather` — resolve inbound `glossary.md#slug` links

```bash
glossarian-gather                     # scan docs/ against docs/glossary.md
glossarian-gather docs/ --glossary docs/glossary.md
glossarian-gather --failures          # list only the unresolved terms
glossarian-gather --failures --verbose 3   # + 3 lines of source context per reference
glossarian-gather --terms-only        # term names only, no file:line lines
glossarian-gather --json report.json  # write findings JSON (never overwrites)
glossarian-gather --quiet             # exit code only
```

Recursively scans a docs tree for inbound `glossary.md#<slug>` fragment links (direct,
`./`, `../`, and `docs/`-prefixed forms), skips files whose front matter has
`archived: true`, builds the valid anchor set from **every** heading in the glossary, and
exits `1` if any referenced slug resolves to no heading.

| Flag | Effect |
|---|---|
| `docs_root` (positional) | Directory to scan. Default `docs/`. |
| `--glossary PATH` | Glossary whose headings define valid anchors. Default `docs/glossary.md`. |
| `--failures` | *Scope:* list only unresolved terms (omit the resolved listing). |
| `--terms-only` | *Detail:* term names only, no per-reference `file:line`. Mutually exclusive with `--verbose`. |
| `--verbose [N]` | *Detail:* under each reference, quote `N` source lines before/after (clamped; default `3`). Mutually exclusive with `--terms-only`. |
| `--json [FILE]` | Emit findings as JSON — to stdout (no FILE) or to a never-overwritten FILE. |
| `--debug` | Trace files/refs/resolutions to stderr. |
| `--quiet` | Suppress all stdout/stderr; rely on the exit code (a `--json FILE` artifact is still written). |

The JSON shape (`docs_root`, `glossary`, `files_scanned`, `files`, `terms`, `summary`) is the
machine contract for downstream consumers (evidence capture, CI).

### Using the tools from another repository

Once the shims are installed, a consumer's `Makefile` or pre-commit hook calls the bare names:

```make
docs-lint:
	glossarian-check docs/glossary.md
	glossarian-gather docs/ --glossary docs/glossary.md
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
  glossary_format_check.py     # linter rules over the model (+ main)
  gather_reference_terms.py    # inbound glossary.md#slug link resolver (+ main)
  cli.py                       # glossarian-check / glossarian-gather entry points
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
