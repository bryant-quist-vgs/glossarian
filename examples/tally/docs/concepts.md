# Concepts

## From text to counts

`tally` splits input into [tokens](glossary.md#token), discards those shorter than the
[minimum length](glossary.md#minimum-length) or listed as a [stopword](glossary.md#stopword), and tallies
each remaining token as an [occurrence count](glossary.md#occurrence-count).

## Reports and merging

The result of a run is a [report](glossary.md#report). Because a report is plain JSON, runs on separate
machines can later be combined with a [merge](glossary.md#merge). The [top list](glossary.md#top-list) is
computed on demand and is not stored.

## Interop

For other tools use an [export format](glossary.md#export-format). The sister project
[tallyboard](glossary.md#tallyboard) consumes the [board feed](glossary.md#board-feed).
Settings come from the [config file](glossary.md#config-file) described in [config.md](config.md).
