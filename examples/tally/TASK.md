You are building documentation for a toy command-line tool called `tally`.

`tally` counts occurrences of words in text files. It has subcommands `tally count FILE...`,
`tally top -n N FILE...`, `tally merge REPORT...`, and `tally export --format {json,csv}`.
It reads an optional config file `.tallyrc` (TOML) with keys `ignore_case`, `stopwords`,
`min_length`. It writes "reports" (JSON files) and can "merge" reports. Invent any further
plausible details you need.

Work only inside: <WORKDIR>
Create these files under <WORKDIR>/docs/:
  - index.md     — overview and quick start
  - cli.md       — reference for every subcommand and flag
  - config.md    — the .tallyrc configuration reference
  - concepts.md  — explanation of the tool's core concepts
  - glossary.md  — a glossarian-compliant glossary with at least 10 terms

Requirements:
  - Each doc other than the glossary links at least three terms to the glossary.
  - At least two glossary entries use a field block; at least one uses `see`; at least one
    uses `aliases`.
  - At least one reserved target exists (a sister project, tool, or convention that some
    term is reserved for), and at least one term is reserved for it.
  - The Confusable Pairs and Renames tables each have at least one row.
  - The glossary must comply with the specification at <SPEC>. Read it in full before
    writing anything. It is the ONLY authority on glossary format: do not read the glossarian
    source code, its contracts, tests, README, or any file outside <WORKDIR> and <SPEC>.

Verification protocol (follow exactly):
  1. Do NOT run glossarian-check or glossarian-gather until all five files are written.
  2. Then, from <WORKDIR>, run exactly these two commands once each:
       glossarian-check docs/glossary.md
       glossarian-gather docs/ --glossary docs/glossary.md
     Save their complete output and exit codes verbatim to <WORKDIR>/first-run.log BEFORE
     changing any file.
  3. If either exit code was non-zero, fix the docs, re-run, and repeat until both exit 0.

Final report (plain text): list every file change you made after step 2 and why; the
sections of the spec you found unclear, ambiguous, or missing; anything you had to guess;
and anything the tools reported that the spec did not prepare you for. If the first run was
clean, say so explicitly.
