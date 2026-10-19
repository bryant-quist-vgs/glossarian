Contract version: v3

# github_slug — GitHub heading-anchor slug: Contract

A tiny shared function, `github_slug(text) -> str`, that computes the fragment anchor
GitHub auto-generates for a markdown heading. It exists so the glossary tooling shares
**one** definition that cannot drift: `glossarian.model` computes a slug per term heading,
and through that model `glossary_format_check.py` (duplicate-heading detection, rule 6) and
the future `gather_reference_terms` (matching inbound `glossary.md#slug` links to term
headings) compare those slugs against GitHub's real anchors.

> **v3 — relocated into the `glossarian` package. Behavior unchanged.** The function moved
> from `scripts/docs/github_slug.py` (a gitignored sibling reached via a `sys.path`
> bootstrap) into `glossarian/github_slug.py`, imported as `from glossarian.github_slug
> import github_slug`. The removal-set algorithm is byte-for-byte the v2 algorithm; only
> the import mechanism and home changed.
>
> **v2 — F1 fidelity correction (retained).** github-slugger (the named reference) strips
> the Unicode General Punctuation (U+2000–U+206F) and Supplemental Punctuation
> (U+2E00–U+2E7F) blocks (em-dash, en-dash, bullet, ellipsis, smart quotes) in addition to
> the ASCII set. Arrows (U+2192) and Math Operators (U+2265) live in other blocks and
> remain preserved.

## Inputs

- **`text`** — a string, required: the text content of a markdown heading (the part after
  the `#` markers, already whitespace-trimmed by the caller). **Trust:** repository
  content, trusted-at-rest; the function only transforms the string.

(No CLI, no stdin, no files, no environment.)

## Outputs

- **Return value** — the lowercased anchor slug string.
  `Load-bearing: glossarian.model compares these for duplicate term anchors, and
  gather_reference_terms compares them against inbound link fragments to decide whether a
  glossary.md#slug link resolves. Both depend on the slug matching GitHub's actual anchor.`

(No stdout, stderr, exit code, or file output — this is a library function, not a CLI.)

## Behaviors

1. **GitHub / github-slugger base-slug algorithm.** In order: (a) strip inline HTML tags
   (`<...>`); (b) remove the punctuation set — ASCII punctuation **except** hyphen `-` and
   underscore `_`, plus the Unicode General Punctuation (U+2000–U+206F) and Supplemental
   Punctuation (U+2E00–U+2E7F) blocks (and, harmlessly, ASCII control chars / DEL, which
   cannot appear in a heading line); (c) replace each space with a hyphen; (d) lowercase.
   `Load-bearing: must equal GitHub's emitted anchor so link-resolution is correct.`
2. **Underscores and hyphens are preserved** (not in the removal set), so identifier-style
   terms like `human_holds` / `managed_by` slug to themselves.
3. **Unicode handling matches github-slugger, not "ASCII-only".** The two Unicode
   punctuation blocks above ARE stripped (em-dash, en-dash, bullet, ellipsis, smart
   quotes) — e.g. an em-dash surrounded by spaces collapses to `--`. Characters in OTHER
   blocks are preserved and lowercased: the Arrows block (U+2192), Mathematical Operators
   (U+2265), and accented letters. `Load-bearing: this is the F1 fidelity fix; dropping or
   keeping ALL non-ASCII both mis-resolve real anchors.`
4. **Spaces are not collapsed.** Each space becomes one hyphen, so `a  b` -> `a--b`.
5. **Base slug only.** The function does NOT perform github-slugger's duplicate
   disambiguation (`-1`, `-2`). Detecting duplicate slugs is the caller's job (rule 6 of
   `glossary_format_check`).

The source character class is written with `\u` escapes so the module source stays
pure-ASCII (no ambiguous-Unicode lint), but the compiled behavior is exactly the above.
Anything else is undeclared drift.

## Declared capability surface

- **Filesystem reads:** None. **Filesystem writes:** None. **Network:** None.
- **Subprocess:** None. **Environment variables:** None. **Secrets:** None.
- **Privilege escalation:** None.

A pure string→string function over the `re` module; a reviewer should find no I/O.

## Assumptions for operation

- Python >= 3.14. Standard library only (`re`).
- Imported as a package module: `from glossarian.github_slug import github_slug`. The
  prior `sys.path` sibling bootstrap (when this lived in the non-package `scripts/`) is
  gone — `glossarian` is an installed/workspace package.
- Input is the heading's already-trimmed text; leading/trailing whitespace, if present,
  would become leading/trailing hyphens (faithful to GitHub).

## Anti-patterns this function must not do

- Do **not** reintroduce a second copy of this algorithm in any caller (the F2 trap). One
  shared definition; a copy can silently drift.
- Do **not** drift from github-slugger's exact removal set (the F1 trap, hit twice):
  dropping ALL non-ASCII loses GitHub-kept characters; keeping ALL non-ASCII fails to strip
  the General/Supplemental Punctuation blocks GitHub removes.
- Do **not** add duplicate-suffix (`-1`) logic here; that is the caller's concern.

## Revision rules

- Any change to the character set, ordering, or casing is load-bearing: bump the version
  and re-verify every importer (`glossarian.model`, and through it
  `glossary_format_check` and `gather_reference_terms`) plus their fixtures.
- Added assumptions never relax previous assumptions.
