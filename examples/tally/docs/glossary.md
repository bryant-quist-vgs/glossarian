---
id: glossary
is_source_of_truth: true
---

# Glossary

Canonical vocabulary for `tally`. Other documents link here; they do not redefine terms.

## Governance

```glossary
governs: ../
```

This glossary governs the whole repository. Maintainers add terms by pull request. A rename keeps
the old term in the [renames table](glossary.md#renames-and-deprecated-terms) for one release.
Other documents link to terms here rather than redefining them.

## Definitions

### tally
The command-line tool that counts word occurrences in text files.

It exposes the subcommands `count`, `top`, `merge`, and `export`.

### token
A single word extracted from input text after splitting on whitespace and punctuation.

Tokens are filtered by [minimum length](glossary.md#minimum-length) and by [stopword](glossary.md#stopword) before they are counted.

### occurrence count
The number of times one [token](glossary.md#token) appears across the input files.

### report
```glossary
aliases: tally report, counts file
short: A JSON file holding the occurrence counts from one run.
confusable: export
```
A JSON file written by `tally count` that records every [token](glossary.md#token) with its
[occurrence count](glossary.md#occurrence-count).

A report also stores the settings that were in effect, so two reports can be checked for
compatibility before they are merged.

### merge
```glossary
short: Combine several reports into one.
see: report
```
The operation performed by `tally merge`, which sums the counts of identical tokens across
several [reports](glossary.md#report) and writes a new report.

### stopword
```glossary
aliases: stop word
confusable: token
```
A token that is excluded from counting because it carries little meaning, such as "the" or "and".

Stopwords are configured with the `stopwords` key of the [config file](glossary.md#config-file).

### ignore case
A setting that makes counting case-insensitive, so "Tally" and "tally" count as the same token.

### minimum length
The shortest token, measured in characters, that is still counted.

Shorter tokens are dropped before counting.

### config file
```glossary
aliases: tallyrc, .tallyrc
short: The TOML file that sets default counting options.
```
The optional TOML file named `.tallyrc` that supplies [ignore case](glossary.md#ignore-case),
[stopword](glossary.md#stopword) lists, and [minimum length](glossary.md#minimum-length).

### top list
The ranking of tokens by descending [occurrence count](glossary.md#occurrence-count), produced by `tally top`.

### export format
The serialisation chosen for `tally export`, either `json` or `csv`.

### tallyboard
```glossary
reserved-for-target: true
```
The sister project that visualises tally output as live charts.

### board feed
```glossary
reserved-for: tallyboard
short: The streaming payload consumed by tallyboard.
```
The streaming payload format that [tallyboard](glossary.md#tallyboard) reads; the term is reserved for that project and tally itself never emits it.

## Confusable Pairs

| Term | Confusable with | Distinction |
|---|---|---|
| [report](glossary.md#report) | [export format](glossary.md#export-format) | A report is the native JSON store; an export is a rendering for other tools. |
| [stopword](glossary.md#stopword) | [token](glossary.md#token) | A stopword is a token that is deliberately skipped. |

## Renames and deprecated terms

| Avoid | Use | Why |
|---|---|---|
| word count | occurrence count | "Word count" suggests the total number of words in a file. |

## Reserved Targets

| Target | What it is | Local | Remote |
|---|---|---|---|
| [tallyboard](glossary.md#tallyboard) | sister project | ~/repos/tallyboard | github.com/example/tallyboard |
