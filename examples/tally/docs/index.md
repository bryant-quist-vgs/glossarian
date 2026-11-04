# tally

`tally` counts how often each word occurs in text files. It reads a [config file](glossary.md#config-file)
for defaults, writes a [report](glossary.md#report), and can [merge](glossary.md#merge) many reports.

## Quick start

```bash
tally count notes.txt essay.txt > report.json
tally top -n 5 notes.txt
tally merge a.json b.json > all.json
tally export --format csv < all.json
```

See [the CLI reference](cli.md), [configuration](config.md), and [concepts](concepts.md).
The vocabulary is defined in the [glossary](glossary.md).

A [token](glossary.md#token) is any word that survives the filters described in [config.md](config.md).
