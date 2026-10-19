Contract version: v0

# glossarian_install.sh — PATH-shim installer for `glossarian-check` and `glossarian-gather`: Contract

`glossarian_install.sh` is the operator-run installer that makes the two glossarian console
scripts runnable from any directory in any repository with nothing but `PATH`. It writes one
small bash shim per command into a bin directory (`~/.local/bin` by default), each of which
`exec`s `uv run --project "<ABS_REPO_ROOT>" --no-dev glossarian-<name> "$@"`, where
`ABS_REPO_ROOT` is this checkout's root, resolved from the installer's own location at
install time. Every shim carries a `# managed-by: glossarian-install` marker; the installer
never overwrites, updates, removes, or executes a file that lacks the marker. It can also
uninstall its shims, show what it would write, and self-check the installed shims by running
each with `--help`. It performs no network access itself, never uses `sudo`, and writes only
under the prefix.

## Delivery mechanism (decision record)

The handoff that commissioned this installer (sedric `scripts/glossarian_standalone/HANDOFF.md`,
2026-10-18) offered two mechanisms. This contract adopts the **live-source shim**:

- **Live-source shim (adopted).** The shim runs the console script out of this checkout's own
  uv project environment (`<ABS_REPO_ROOT>/.venv`, created by `uv` on first run). It always
  tracks the current source: `git pull` is the upgrade path, with no reinstall step, and the
  mechanism mirrors the sedric_lite `task-*` shims exactly. Cost: the shims break if the
  checkout moves; `--check` reports that as a failed self-test, and re-running the installer
  from the new location repairs it.
- **Isolated install (rejected for now).** `uv tool install <ABS_REPO_ROOT>` would give
  self-contained binaries but goes silently stale whenever the source changes unless the
  operator remembers to reinstall. Revisit if a consumer needs the tools without a checkout.

`--no-dev` keeps the runtime shim from syncing the `dev` dependency group (pytest, ruff, mypy)
into the project environment, so a shim run needs nothing beyond the stdlib-only package and
its `hatchling` build backend. `uv run` performs a *sufficient* (inexact) sync, so a shim run
does not remove dev tools that `uv run pytest` installed earlier, and vice versa (verified
against uv 0.11.17).

**Deviation from the handoff, recorded here as it required:** the handoff said not to modify
the glossarian package. Neither CLI accepted `--help` (`glossarian-check` treated it as a
default-path run and `glossarian-gather` rejected it as unknown), which both the `--check`
self-test and the handoff's own acceptance criterion assume. With the package now living in
this repository rather than as a sedric workspace member, `-h`/`--help` was added to both
CLIs (`glossary_format_check` contract v4 → v5, `gather_reference_terms` contract v1 → v2,
each with tests). No lint rule, output, or capability of either tool changed.

## Inputs

- **`--prefix DIR`** — string path, optional. CLI argument. **Trust:** operator-provided
  (trusted). The bin directory that receives the shims. Default: `$HOME/.local/bin`. May
  contain spaces. Taken literally (not canonicalised); created with `mkdir -p` on install
  when absent. An empty value is a usage error (exit 2).
- **`--uninstall`** — flag, optional. CLI argument. **Trust:** operator-provided. Remove
  marked shims from the prefix instead of installing. May be given once.
- **`--check`** — flag, optional. CLI argument. **Trust:** operator-provided. Run every shim
  in the prefix with `--help` and report pass/fail. May be given once; mutually exclusive
  with `--uninstall` and `--dry-run` (usage error, exit 2).
- **`--dry-run`** — flag, optional. CLI argument. **Trust:** operator-provided. Print what
  install or uninstall would do without writing, creating, or removing anything.
- **`-h` / `--help`** — flag, optional. Print usage to stdout and exit 0.
- **`$HOME`** — environment variable, required unless `--prefix` is given. Used only to
  compute the default prefix and to print the PATH hint.
- **`$PATH`** — environment variable, read to decide whether the prefix is already on PATH
  (install mode) and to locate `uv` (check mode). Also used implicitly by the shell for
  command lookup.
- **`$CDPATH`** — environment variable, unset at startup so every `cd` the script performs
  is literal. Never read.
- **`${BASH_SOURCE[0]}`** — the installer's own invocation path, resolved through symlinks to
  an absolute directory, `ABS_REPO_ROOT`. **Trust:** operator-controlled (the operator placed
  the checkout). Refused (exit 1) in every mode when the resolved directory contains any of
  `"`, `$`, `` ` ``, `\`, or a newline, because the path is embedded inside a double-quoted
  string in each shim.
- **Existing files at `<prefix>/glossarian-<name>`** — read only to test for the management
  marker and, in check mode, to compare against the expected shim body. **Trust:**
  operator-owned content, treated as untrusted; unmarked content is never modified, executed,
  or removed. Only a regular file (or a symlink to one) can count as marked; a directory,
  FIFO, socket, or device at the path is treated as unmanaged.
- **The project files beside the installer** — `pyproject.toml` and `src/glossarian/cli.py`
  in `ABS_REPO_ROOT`. Their existence is checked before any shim is written in install mode
  (proof that the installer is running from a glossarian checkout). The installer never
  reads, modifies, or executes them; `--check` executes the package indirectly, through the
  shims, with `--help`.

## Outputs

- **Shim files** at `<prefix>/glossarian-<name>` for `check` and `gather`, mode exactly
  `0755`, exactly three lines:

  ```
  #!/usr/bin/env bash
  # managed-by: glossarian-install
  exec uv run --project "<ABS_REPO_ROOT>" --no-dev glossarian-<name> "$@"
  ```

  `Load-bearing: consumer repositories (first: microservice_relation_mapping's Makefile
  docs-lint target and .pre-commit-config.yaml glossarian hook) invoke the tools by these
  bare names from their own directories and branch on the tools' 0/1/2 exit codes, which
  the shim passes through unchanged via exec.`
- **stdout** — one line per shim (`installed <path>`, `updated <path>`, `would write <path>`,
  `removed <path>`, `would remove <path>`, `PASS glossarian-<name>`,
  `FAIL glossarian-<name> (<reason>)`), the PATH hint when applicable, the closing
  first-run note after an install, and usage text for `--help`. Nothing else goes to stdout.
- **stderr** — `Error: ...` lines for refusals and usage errors (plus usage text after a
  usage error); `Note: ...` lines for unmarked files skipped during uninstall. Nothing else
  goes to stderr.
- **exit code** — `0` success (including idempotent re-runs and uninstall of nothing); `1`
  refusal or failed check (unmarked file in the way, missing project files, bad checkout
  directory, `uv` missing in check mode, any shim failing `--check`); `2` usage error
  (unknown option, option missing its value or empty, repeated or conflicting modes, `$HOME`
  unset without `--prefix`).
  `Load-bearing: the operator and any wrapping automation branch on 0/1/2 exactly as the
  sedric_lite DESIGN.md §3 convention defines them.`

## Behaviors

1. **Argument parsing.** Accepts the flags listed under Inputs in any order. Unknown
   options, a `--prefix` without a value or with an empty value, `--uninstall` or `--check`
   given more than once or together, and `--check` combined with `--dry-run` are usage
   errors (exit 2) that print the error and usage to stderr.
2. **Self-location.** Unsets `CDPATH`, then resolves `${BASH_SOURCE[0]}` through any chain
   of symlinks and takes the absolute, physical (`cd -P --`) directory as `ABS_REPO_ROOT`.
   In every mode, refuses (exit 1) if that directory contains `"`, `$`, `` ` ``, `\`, or a
   newline.
   `Load-bearing: shims hard-code this path; a wrong resolution makes every command fail at
   run time.`
3. **Precondition check (install and dry run only).** Before creating the prefix or writing
   anything, verifies `ABS_REPO_ROOT/pyproject.toml` and
   `ABS_REPO_ROOT/src/glossarian/cli.py` exist; a missing one is a refusal (exit 1) and no
   shim is written. Uninstall and check do not require them.
4. **Install (default mode).** Creates the prefix with `mkdir -p` when absent. For each
   name: if something exists at the shim path and is not a marked regular file, prints
   `Error: refusing to overwrite unmanaged file <path>` to stderr, records the refusal, and
   continues with the remaining names; otherwise writes the three-line shim atomically (temp
   file created by `mktemp` in the prefix, `chmod 0755`, then `mv -f` over the target)
   printing `installed <path>` for a new file or `updated <path>` for a marked file replaced
   in place. An `EXIT` trap removes the temp file if the script dies between `mktemp` and
   `mv`. Exits 1 if any refusal was recorded, else 0.
   `Load-bearing: re-running the installer is the supported repair path after the checkout
   moves ("update marked ones in place").`
5. **Unmanaged-file protection.** A path that is not a regular file containing the exact
   marker string `managed-by: glossarian-install` is never written to, removed, or executed
   by this script in any mode.
   `Load-bearing: the operator's own ~/.local/bin contents (including the sedric_lite task-*
   and llm-size-guard shims, which carry different markers) are safe from this installer.`
6. **Dry run.** With `--dry-run`, install prints `would write <path>` (or the refusal line
   for unmanaged files, with exit 1) and uninstall prints `would remove <path>`; the prefix
   directory is not created and no file is created, modified, or removed. Exit code follows
   the same rules as the real run.
7. **PATH hint.** After an install (real or dry run), splits `$PATH` on `:` and, if no entry
   equals the prefix string exactly, prints a hint containing the literal line
   `export PATH="$HOME/.local/bin:$PATH"` when the prefix is the default, or
   `export PATH="<prefix>:$PATH"` otherwise. Prints no `export PATH=` line when the prefix
   is on PATH.
8. **Closing first-run note.** After an install (real or dry run), prints that the shims
   need `uv` on PATH, that the first run creates `<ABS_REPO_ROOT>/.venv` (which may fetch
   the `hatchling` build backend if it is not already in uv's cache), and that
   `glossarian_install.sh --check` verifies the install.
9. **Uninstall.** With `--uninstall`, for each name: a marked file at the shim path is
   removed (`removed <path>`); anything else present is left in place with
   `Note: leaving unmanaged file <path>` on stderr; a missing file is silently skipped. Exits
   0. Does not remove the prefix directory or the project `.venv`.
10. **Check.** With `--check`, first requires `uv` on `PATH` (otherwise
    `Error: uv not found on PATH ...` and exit 1 without running anything). Then for each
    name: a missing shim is `FAIL glossarian-<name> (not installed)`; an unmarked path is
    `FAIL glossarian-<name> (unmanaged file, not run)`; a marked file whose bytes differ from
    the shim body this installer would write for that name (compared with `cmp` against a
    process substitution; nothing is written) is
    `FAIL glossarian-<name> (stale or foreign shim, not run)`; a byte-identical shim is
    executed as `"<path>" --help` with `UV_PYTHON_DOWNLOADS=never` set in its environment
    and with stdout and stderr discarded, `PASS glossarian-<name>` on exit 0 and
    `FAIL glossarian-<name> (exit N)` otherwise. Exits 0 only if every name passed, else 1.
    `Load-bearing: this is the operator's verification step after install, and the
    detector for a moved checkout.`

Any behavior the script performs that is not listed here is **undeclared** and constitutes
drift. The script must not perform undeclared behaviors. An adversarial reviewer treats
undeclared behaviors as suspect.

## Declared capability surface

- **Filesystem reads:** existence tests on `ABS_REPO_ROOT/pyproject.toml` and
  `ABS_REPO_ROOT/src/glossarian/cli.py`; regular-file tests, marker `grep`, and (check mode)
  `cmp` on `<prefix>/glossarian-<name>`; `readlink` on `${BASH_SOURCE[0]}` and its symlink
  chain. No other reads.
- **Filesystem writes:** by this script, only under `<prefix>`: `mkdir -p <prefix>`, a temp
  file created by `mktemp` inside `<prefix>` then `mv -f`'d to `<prefix>/glossarian-<name>`,
  `chmod 0755` on that file, `rm -f` of the temp file on abnormal exit, and
  `rm -f <prefix>/glossarian-<name>` for marked files in uninstall mode. Nothing is written
  by this script in `--dry-run` or `--check` mode. **Residual delegated writes in `--check`:**
  the shims run `uv run --project`, which creates or syncs `<ABS_REPO_ROOT>/.venv`, may write
  to its own cache and state directories (`~/.cache/uv` or `$UV_CACHE_DIR`,
  `~/.local/share/uv`), and the Python it launches writes bytecode under
  `<ABS_REPO_ROOT>/.venv`. `UV_PYTHON_DOWNLOADS=never` is the only guard this script applies.
- **Network access:** none performed directly. In `--check` the delegated `uv` is told not to
  download Python interpreters (`UV_PYTHON_DOWNLOADS=never`); the project is stdlib-only, so
  the only thing `uv` could fetch is the `hatchling` build backend on a machine whose uv
  cache lacks it. At normal (non-check) run time the shims are governed by the operator's own
  `uv` configuration, not by this script.
- **Subprocess invocation:** `mkdir`, `mktemp`, `mv -f`, `chmod`, `rm -f`, `grep`, `cmp`,
  `readlink`, `dirname`, `cat` (heredoc text), `command -v uv`, and — in check mode only —
  each byte-identical marked shim as `<prefix>/glossarian-<name> --help` (which in turn runs
  `uv run --project <ABS_REPO_ROOT> --no-dev glossarian-<name> --help`). No other commands.
- **Environment variables read:** `HOME`, `PATH`. **Environment variables set:** `CDPATH` is
  unset at startup; `UV_PYTHON_DOWNLOADS=never` is set only in the environment of each shim
  invoked by `--check` (never exported to the operator's shell).
- **Secrets handled:** No secrets handled.
- **Privilege escalation:** No privilege escalation; never invokes `sudo`.

## Assumptions for operation

- Runtime: `bash >= 3.2` (macOS system bash is sufficient); no associative arrays or
  `mapfile`; process substitution (`<(...)`) is available.
- Dependencies: POSIX `mkdir`, `mktemp`, `mv`, `chmod`, `rm`, `grep`, `cmp`, `readlink`,
  `dirname`, `cat` on `PATH`. `uv` is required only by `--check` and at shim run time.
- The installer is run from (or via a symlink to) the root of a glossarian checkout
  (`pyproject.toml` and `src/glossarian/` beside it), and the checkout is not moved
  afterwards (shims embed the absolute path; re-run the installer if it is).
- Filesystem: POSIX semantics; the prefix is on a filesystem where `mv` within the
  directory is atomic.
- Encoding: shim content is ASCII; paths are passed through unmodified.
- The shims rely on `uv` being on `PATH` and a Python >= 3.14 being available to `uv`
  (`requires-python` in `pyproject.toml`) when the operator or a consumer repository runs a
  command. Bare `python3` is never invoked: this machine's managed policy refuses it, and
  `uv` is the supported runner.

## Anti-patterns this script must not do

- Do **not** overwrite, remove, or execute a file at a shim path that lacks the management
  marker, and do **not** execute a marked file whose content differs from the expected shim
  body. The operator's bin directory is not this script's to edit.
- Do **not** write anywhere outside `--prefix`, and do **not** modify the package, the
  operator's shell rc files, or `PATH` itself; the PATH change is printed as a hint for the
  operator to apply.
- Do **not** write shims that exec `python3` directly (managed-policy refusal); `uv` is the
  runner.
- Do **not** use `sudo`, install system-wide, or touch the network; do **not** let the
  delegated `uv` download interpreters during `--check`.
- Do **not** run the shims in any mode other than `--check`.
- Do **not** prompt or read stdin.

## Manual verification

The authoring session's sandbox denied every execution of the two shell files, including
`bash -n` (the same denial sedric's `install_sedric_lite.sh` hit; see that README). The
suite was therefore **not run in-session**, and this contract stays at v0 until the operator's
run is green. Ratification is then a two-line edit: `Contract version: v0` → `v1` here, and
`Built against contract v0` → `v1` in the script header.

1. The hermetic suite (fake `uv`, temp prefixes, no network, writes nothing outside
   `$TMPDIR`):

   ```bash
   bash ~/bryant_repos/glossarian/glossarian_install_test.sh
   ```

   Expected: `16 tests, 0 failure(s)`, exit 0.

2. The real, non-hermetic acceptance run the handoff specifies, from an unrelated directory
   with only `PATH`:

   ```bash
   bash ~/bryant_repos/glossarian/glossarian_install.sh
   bash ~/bryant_repos/glossarian/glossarian_install.sh --check
   cd "$TMPDIR" && glossarian-check --help
   glossarian-check ~/bryant_repos/microservice_relation_mapping/docs/glossary.md
   ```

   Expected: `--check` prints `PASS glossarian-check` and `PASS glossarian-gather`; the last
   command exits 0 and reports `12 definition entries`. (The shim's exact command line was
   exercised in-session by hand from `$TMPDIR`:
   `uv run --project ~/bryant_repos/glossarian --no-dev glossarian-check <that file>` printed
   `OK: ... — 12 definition entries`, exit 0, and both `--help` forms exit 0.)

## Revision rules

- Removing a behavior, an input, an output, or an assumption requires a high threshold and a
  deliberate version bump. Removals are recheck signals for everything that depends on the
  script.
- Added assumptions never relax previous assumptions.
- Added capabilities to the declared capability surface require operator review; a
  maintenance session that adds a capability silently is producing drift.
- The script's file header references the contract version it was built against.

## Revision history

- v0 — drafted ahead of the script from sedric's `install_sedric_lite.sh` contract v2
  conventions and the 2026-10-18 handoff.
