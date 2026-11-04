# Glossarian compliance specification

Rules for writing a documentation tree whose glossary passes `glossarian-check` and whose
inbound glossary links pass `glossarian-gather`. Written for agents. Every rule below is
enforced by the tools unless marked *convention*.

## 1. Tools

| Command | Does | Default input |
|---|---|---|
| `glossarian-check [GLOSSARY]` | validates the glossary file's own structure | `docs/glossary.md` |
| `glossarian-gather [DOCS_ROOT]` | resolves every `glossary.md#slug` link under `DOCS_ROOT` against the glossary its path names, and checks the linking file is inside that glossary's governed scope | `docs/` |
| `glossarian-template PATH` | writes a blank, compliant glossary to a new file | |
| `glossarian-fix GLOSSARY [--dry-run]` | repairs the trivial issues `check` marks as fixable | |

Exit codes for all four: `0` clean, `1` violations, `2` bad path or usage. The command names
are hyphenated (`glossarian-check`, not `glossarian check`). Run from the repository root,
or pass explicit paths:

```bash
glossarian-check docs/glossary.md
glossarian-gather docs/
```

`check` and `gather` locate the repository root by walking up for `.git`; outside a
repository pass `--repo-root DIR` to both. When `check` reports an issue `fix` can repair,
it prints the exact `glossarian-fix` command and what would change.

## 2. Layout

- A glossary is a markdown file whose basename is exactly `glossary.md`, conventionally
  `docs/glossary.md`. A repository may hold several (for example one for the tooling and one
  for a knowledge base), each in its own directory.
- Every glossary declares the directory it **governs** (§3, `governs:`), relative to its own
  directory: `../` for `docs/glossary.md` governing the whole repository, `.` for a glossary
  governing only its own directory. A scope never extends above the repository root and
  always contains the glossary itself.
- A document may link only to a glossary whose scope contains it. With nested scopes a
  document may link to any glossary that governs it.
- `glossarian-gather` scans every `*.md` under `DOCS_ROOT` recursively, including the
  glossaries. A scanned file whose front matter contains `archived: true` is skipped. Front
  matter is optional on every file except the glossary.
- To start a new glossary, run `glossarian-template docs/glossary.md`; it writes a file that
  already passes `check`, with `governs` set to the repository root.

## 3. Glossary file structure

The file must contain, in this order:

1. **Front matter.** Line 1 is `---`. A later line is `---`. Between them, `key: value`
   lines. Required: `id: glossary`. Recommended: `is_source_of_truth: true` (its absence
   prints a `warning:` line but exit stays `0`; `fix` adds it). Quotes around values are
   stripped.
2. **Exactly one H1**, text exactly `Glossary`: `# Glossary`. No other `#` heading anywhere
   in the file (headings inside fenced code are ignored).
3. **Five `##` sections, verbatim, each exactly once, in this order:**
   ```
   ## Governance
   ## Definitions
   ## Confusable Pairs
   ## Renames and deprecated terms
   ## Reserved Targets
   ```
   Case and spelling are exact (`Pairs` capitalised; `deprecated terms` lower-case;
   `Targets` capitalised). Additional `##` sections are permitted anywhere and are ignored
   by the order check. Prose may appear between the H1 and `## Governance`.
4. **`## Governance` opens with a field block declaring the scope:**
   ````
   ## Governance

   ```glossary
   governs: ../
   ```
   ````
   The block must be the section's first non-blank content; prose follows it. `governs` is
   the only allowed key. Its value is a relative path (never absolute, `~`, a URL, or a
   backslash path) that resolves to an existing directory at or below the repository root
   and at or above the glossary's own directory. Missing block, missing key, or an unsafe
   value fails the check.

The `## Definitions` section runs from its heading to the next `##` heading (or end of
file), so an extra `##` placed inside it ends it early. Everything inside it is parsed as
term entries by the grammar in §4. Content of the other sections is not validated except
the Reserved Targets table (§4.5); they may use `###` or deeper headings freely (they
become anchors, §5); see §7 for conventions.

## 4. Term entry grammar

Inside `## Definitions`, every entry is:

```
### <term>
<optional field block>
<body>
<blank line>
```

### 4.1 Heading

- Level is exactly `###`. **Any heading of any other level inside `## Definitions` is an
  error**, so never use `####` sub-headings inside a definition body.
- The heading text is the canonical term only. It must not contain any of `(`, `)`, `*`,
  `/`, `:`, `→`. Put qualifiers, aliases, and co-defined forms in the field block or body.
- Backticks, hyphens, underscores, and spaces are allowed. Backticks are stripped from the
  slug; prefer plain text.
- Each heading's slug (§5) must be unique in the file. `Foo bar`, `foo-bar`, and `Foo Bar`
  all slug to `foo-bar` and therefore collide.
- No content may appear between `## Definitions` and the first `###` heading.

### 4.2 Field block (optional)

A fenced block with info string `glossary`, placed as the first non-blank content after the
heading (a `glossary` fence later in the body is ordinary body text):

````
### working agent
```glossary
aliases: worker, write agent
short: The agent that performs an item's work.
confusable: reviewing agent
see: managed-by
reserved-for: lacey
```
````

- Each line is `key: value`. Allowed keys: `aliases`, `short`, `confusable`, `see`,
  `reserved-for`, `reserved-for-target`. Any other key is an error. A line splits on its
  first `:`, so values may contain colons. `aliases`, `short`, and `confusable` are free
  text. *Convention:* separate multiple `aliases` or `confusable` values with commas; name
  terms in `confusable` as plain text, not slugs.
- `see` must be the **slug** (§5) of another `###` term in this file, e.g. `see: working-agent`,
  not `see: working agent`. Exactly one slug. (`fix` rewrites a term-form value to its slug.)
- `reserved-for` lists one or more **reserved targets** (§4.5) by slug, comma-separated:
  `reserved-for: lacey, auditable-script`. Each must be a term in this file whose own field
  block declares `reserved-for-target: true`.
- `reserved-for-target: true` marks the term as a reserved target (§4.5). `false` or absent
  means it is not one. Any other value is an error.
- The closing fence is required.
- The field block does not count as body. An entry with only a field block has an empty
  body and fails.
- Position matters. The block must come before any prose. A block placed after a body line
  is silently treated as ordinary body: the linter does not complain, but every field in it
  is ignored and a bad `see` goes unreported.

  ````
  WRONG                             RIGHT
  ### token                         ### token
  A unit of text.                   ```glossary
  ```glossary                       aliases: word
  aliases: word                     ```
  ```                               A unit of text.
  ````

### 4.3 Body

- Runs from after the field block to the next heading of any level, or to the end of the
  section. Must contain at least one non-blank line; a list item, table row, or code fence
  counts. *Convention:* start with one plain prose sentence.
- May contain multiple paragraphs, blank lines, lists, tables, and fenced code.
- **A paragraph whose first line begins with `**` is an error** when it follows a blank
  line and is not the body's first line. The linter treats it as an unconverted bold-style
  term. So never start a paragraph with `**Note:**`, `**Example:**`, `**Warning**`, etc.
  Use `Note:` or a list item (`- **Note:**`) instead. Bold inside a line is fine; bold on
  the body's very first line is fine.
- The body's last line must be followed by a blank line before the next `###` heading
  (`fix` inserts a missing one).
- Do not use any `#`-style heading inside a body (see §4.1).

### 4.4 Minimal valid entry

```
### retry budget
The number of times a job may be re-queued before it is marked failed.

```

### 4.5 Reserved targets

A *reserved target* is anything a term can be reserved for: a tool, a convention, a policy,
a repository, a sister project. Each one is itself a term under `## Definitions` with
`reserved-for-target: true`, so links to it resolve, and each one has a row under
`## Reserved Targets`:

````
### lacey
```glossary
reserved-for-target: true
```
The sister project that consumes this vocabulary.

### capability grant
```glossary
reserved-for: lacey
```
A token lacey issues; the term is reserved for lacey's use.

## Reserved Targets

| Target | What it is | Local | Remote |
|---|---|---|---|
| [lacey](glossary.md#lacey) | sister project | ~/repos/lacey | github.com/org/lacey |
````

Rules: every `reserved-for` value is the slug of a `reserved-for-target: true` term; every
such term has exactly one row whose **first cell** names it, as a link to its slug (`#lacey`;
the fragment is matched, not the link text) or as its plain, backticked, or bold text; no row
names anything else. Columns after the
first are free text; *convention:* `What it is`, `Local` (where it lives on disk), `Remote`
(where it lives upstream), the last two optional. With no targets, write `None.` under the
heading or keep a header-only table.

## 5. Slugs

The anchor for a heading is computed as GitHub does:

1. remove inline HTML tags;
2. remove ASCII punctuation except `-` and `_`, and remove Unicode General/Supplemental
   punctuation (em dash, en dash, smart quotes, ellipsis);
3. replace every space with `-` (runs are not collapsed: two spaces give `--`);
4. lower-case.

Examples: `Working Agent` → `working-agent`; `human_holds` → `human_holds`;
`` `tally` file `` → `tally-file`; `v2.0 API` → `v20-api`; `A - B` → `a---b`.

Write headings with single spaces and no punctuation beyond `-` and `_` so the slug is
predictable. Every heading in the glossary at every level is a valid anchor, including
`# Glossary` (`#glossary`) and the five sections (`#governance`, `#definitions`,
`#confusable-pairs`, `#renames-and-deprecated-terms`, `#reserved-targets`).

## 6. Linking to the glossary from other docs

- Link form: `[text](<path>glossary.md#<slug>)` where `<path>` is the relative path from the
  **linking file's directory** to the glossary: empty for a sibling, `../` from a
  subdirectory, `../docs/` from a sibling tree. The path is resolved exactly as GitHub
  resolves it, so a `docs/`-prefixed link written inside `docs/sub/` points at
  `docs/sub/docs/glossary.md` and fails as `missing-glossary`.
- The linking file must lie inside the scope that glossary governs (§3). A link from
  outside fails as `out-of-scope`, even if the slug exists.
- `<slug>` must equal the slug of a heading in that glossary. Compute it with §5; do not
  guess from the display text. A miss fails as `unresolved-anchor`.
- The fragment ends at the first whitespace, `(`, `)`, `[`, `]`, `<`, `>`, quote, backtick,
  or `#`.
- The scan is textual and not fence-aware. `glossary.md#anything` inside a code span,
  a fenced code block, or an HTML comment is still a reference and must resolve. When
  documenting the link syntax itself, write it so the literal `glossary.md#` does not
  appear, e.g. `glossary.md` + `#slug`.
- Links from a glossary to itself are scanned too and must resolve.
- A link to `glossary.md` with no `#fragment` is not checked.
- Plain mentions of a term without a link are never checked. *Convention:* link the first
  mention of each glossary term in each document.
- `glossarian-gather` reports each reference's status (`resolved`, `missing-glossary`,
  `not-a-glossary`, `invalid-scope`, `out-of-scope`, `unresolved-anchor`) and lists every
  glossary it found with the scope it governs. `--glossary PATH` narrows the report to one
  glossary; `--failures` lists only failures.

## 7. Section conventions (not linted)

- **Governance:** after the field block, who may edit the glossary, how terms are added,
  renamed, and retired, and the rule that other docs link rather than redefine.
- **Confusable Pairs:** a table `| Term | Confusable with | Distinction |`. Use the slug of
  each term (as a `glossary.md#slug` link, which is checked) or plain text.
- **Renames and deprecated terms:** a table `| Avoid | Use | Why |`. If there is nothing to
  list, write a single line such as `None yet.`; the section must still exist.
- **Reserved Targets:** the table of §4.5, or `None.`

## 8. Complete minimal glossary

````markdown
---
id: glossary
is_source_of_truth: true
---

# Glossary

Canonical vocabulary for the project. Other documents link here; they do not redefine terms.

## Governance

```glossary
governs: ../
```

This glossary governs the whole repository. Terms are added by pull request. A rename keeps
the old term in the [renames table](glossary.md#renames-and-deprecated-terms) for one release.

## Definitions

### working agent
```glossary
aliases: worker
short: The agent that performs an item's work.
see: reviewing-agent
reserved-for: lacey
```
The write-capable agent that executes an item. Compare the
[reviewing agent](glossary.md#reviewing-agent), which only reads.

### reviewing agent
The read-only agent that assesses a [working agent](glossary.md#working-agent)'s output.

Note: a reviewing agent never writes to the repository.

### human_holds
A gate value meaning a human currently holds the completion token.

### lacey
```glossary
reserved-for-target: true
```
The sister project that consumes this vocabulary and reserves some of its terms.

## Confusable Pairs

| Term | Confusable with | Distinction |
|---|---|---|
| [working agent](glossary.md#working-agent) | [reviewing agent](glossary.md#reviewing-agent) | Working writes; reviewing reads. |

## Renames and deprecated terms

| Avoid | Use | Why |
|---|---|---|
| worker | working agent | Ambiguous with OS worker processes. |

## Reserved Targets

| Target | What it is | Local | Remote |
|---|---|---|---|
| [lacey](glossary.md#lacey) | sister project | ~/repos/lacey | github.com/org/lacey |
````

## 9. Pre-flight checklist

Before running the tools, confirm:

- [ ] file starts with `---` and front matter has `id: glossary`
- [ ] exactly one `#` heading, text `Glossary`
- [ ] the five `##` sections, spelled exactly, in order
- [ ] `## Governance` opens with a ```glossary block whose only key is `governs`, and the
      value is relative, inside the repository, and contains the glossary's directory
- [ ] every heading under `## Definitions` is `###`; none is `####` or deeper
- [ ] no `(`, `)`, `*`, `/`, `:`, `→` in any `###` heading
- [ ] no two `###` headings share a slug
- [ ] every body has prose; no body paragraph (after the first) starts with `**`
- [ ] a blank line precedes every `###` heading
- [ ] every field block uses only `aliases`, `short`, `confusable`, `see`, `reserved-for`,
      `reserved-for-target`; every `see` value is a slug of a defined term
- [ ] every `reserved-for` value is the slug of a `reserved-for-target: true` term, and
      every such term has one row under `## Reserved Targets` whose first cell names it
- [ ] every `glossary.md#slug` in every file (including inside code) uses the right relative
      path, comes from a file inside that glossary's scope, and names a real heading slug

Then run both commands from the repository root and require exit `0` from each. If `check`
prints `fixable:` lines, run the `glossarian-fix` command it names and re-check.
