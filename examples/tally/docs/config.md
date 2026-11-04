# Configuration

`tally` looks for a [config file](glossary.md#config-file) named `.tallyrc` in the current directory,
then in each parent directory. The file is TOML. Command-line flags override it.

```toml
ignore_case = true
stopwords = ["the", "a", "and"]
min_length = 3
```

## Keys

- `ignore_case` (bool, default `false`): enables [ignore case](glossary.md#ignore-case) counting.
- `stopwords` (list of strings, default empty): the [stopword](glossary.md#stopword) list.
- `min_length` (integer, default `1`): the [minimum length](glossary.md#minimum-length) of a
  [token](glossary.md#token).

Unknown keys are rejected with exit code `2`. See [the CLI reference](cli.md) for the matching flags.
