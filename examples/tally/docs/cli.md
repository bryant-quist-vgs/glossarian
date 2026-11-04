# CLI reference

Every subcommand reads the [config file](glossary.md#config-file) from the current directory unless
`--config PATH` is given. Global flags: `--config PATH`, `--version`, `--help`.

## tally count FILE...

Counts [tokens](glossary.md#token) in each FILE and prints a [report](glossary.md#report) as JSON to
standard output.

- `--ignore-case` / `--no-ignore-case`: override [ignore case](glossary.md#ignore-case).
- `--min-length N`: override [minimum length](glossary.md#minimum-length).
- `--stopwords FILE`: read extra [stopwords](glossary.md#stopword), one per line.
- `-o, --output PATH`: write the report to PATH instead of standard output.

## tally top -n N FILE...

Prints the [top list](glossary.md#top-list): the N tokens with the highest
[occurrence count](glossary.md#occurrence-count). The default N is 10.

## tally merge REPORT...

Performs a [merge](glossary.md#merge) of the given [reports](glossary.md#report) and prints the result.
Reports produced with different settings are refused unless `--force` is given.

## tally export --format {json,csv}

Reads a report from standard input and writes it in the chosen [export format](glossary.md#export-format).
`--format` is required. Use `-o PATH` to write to a file.

Exit codes: `0` success, `1` runtime error, `2` bad usage.
