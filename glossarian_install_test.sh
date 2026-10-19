#!/usr/bin/env bash
# glossarian_install_test.sh - Tests for glossarian_install.sh, built against contract v0.
#
# Coverage:
#   - Happy path: install into a temp prefix writes both marked shims with the exact
#     three-line body (wc -l = 3), mode exactly 0755, and the checkout's absolute root
#     (behavior 4, shim output); progress lines go to stdout and nothing to stderr.
#   - Load-bearing: self-location through a symlink resolves to the real directory (behavior 2).
#   - Load-bearing: re-run updates marked shims in place and reports 'updated' (behavior 4).
#   - Trust boundary: an unmarked pre-existing file is refused untouched (refusal on stderr),
#     exit 1, while the other shim is still installed; a directory at a shim path is unmanaged
#     too (behaviors 4, 5). The same refusal applies under --dry-run (behavior 6).
#   - Load-bearing: --uninstall removes only marked shims, leaves the unmarked file with a
#     stderr Note, and works without the project files present (behaviors 3, 9).
#   - Capability boundary: --dry-run writes nothing, not even the prefix directory (behavior 6).
#   - Load-bearing: --check PASSes every byte-identical shim with a fake uv exiting 0, passes
#     UV_PYTHON_DOWNLOADS=never and the exact `run --project <root> --no-dev glossarian-<name>
#     --help` argv to it; FAILs with exit 1 when the fake uv exits 3; reports not-installed,
#     unmanaged, and stale-or-foreign shims without running them; refuses when uv is absent
#     from PATH (behavior 10).
#   - PATH hint printed with the exact export line when the prefix is off PATH, absent when
#     on PATH; default prefix prints the literal $HOME form (behavior 7).
#   - Closing first-run note names uv, the .venv path, and --check (behavior 8).
#   - Edge cases: --prefix with a space works; missing pyproject.toml / cli.py refuses before
#     writing (behavior 3); a checkout directory containing any of " $ ` \ or newline is
#     refused in install and check mode (behavior 2); usage errors exit 2 (unknown option,
#     valueless or empty --prefix, repeated/conflicting modes, HOME unset) and --help exits 0
#     (behavior 1).
#
# Negative controls: every assertion that a file was NOT touched, NOT run, or NOT written is
# paired with a positive sibling in the same test (the managed file WAS written / run), so
# removing the guard makes the test fail rather than vacuously pass.
#
# Run with:
#     bash glossarian_install_test.sh

set -u

SCRIPT_DIR=$(cd -P "$(dirname "$0")" && pwd)
INSTALL="$SCRIPT_DIR/glossarian_install.sh"
BASH_BIN=$(command -v bash)
MARKER="managed-by: glossarian-install"
NAMES="check gather"
TESTS=0
FAILURES=0
SANDBOXES=""
CURRENT_TEST=""

cleanup() {
    for dir in $SANDBOXES; do
        rm -rf "$dir"
    done
}
trap cleanup EXIT

sandbox() {
    local dir
    dir=$(mktemp -d "${TMPDIR:-/tmp}/glossarian_install_test.XXXXXX")
    # Canonicalise (TMPDIR may end in '/'); the installer embeds physical paths.
    dir=$(cd -P "$dir" && pwd)
    SANDBOXES="$SANDBOXES $dir"
    echo "$dir"
}

# A fake uv that logs its arguments and the guard variable, then exits with the given code.
make_fake_uv() {
    local dir="$1" code="$2"
    mkdir -p "$dir"
    cat > "$dir/uv" <<EOF
#!/bin/sh
echo "uv \$*" >> "$dir/calls.log"
echo "env UV_PYTHON_DOWNLOADS=\${UV_PYTHON_DOWNLOADS:-unset}" >> "$dir/calls.log"
exit $code
EOF
    chmod +x "$dir/uv"
}

# Copy the installer into DIR and give it the project files so install can succeed there.
make_installer_copy() {
    local dir="$1"
    mkdir -p "$dir/src/glossarian"
    cp "$INSTALL" "$dir/glossarian_install.sh"
    : > "$dir/pyproject.toml"
    : > "$dir/src/glossarian/cli.py"
}

fail() {
    FAILURES=$((FAILURES + 1))
    echo "FAIL: $CURRENT_TEST - $*" >&2
}

assert_eq() {
    [ "$1" = "$2" ] || fail "expected '$2', got '$1' ($3)"
}

assert_contains() {
    case "$1" in
        *"$2"*) ;;
        *) fail "expected output to contain '$2' ($3)" ;;
    esac
}

assert_not_contains() {
    case "$1" in
        *"$2"*) fail "expected output not to contain '$2' ($3)" ;;
    esac
}

assert_file_contains() {
    grep -qF "$2" "$1" 2>/dev/null || fail "expected $1 to contain '$2'"
}

expected_shim() {
    local dir="$1" name="$2"
    printf '#!/usr/bin/env bash\n# %s\nexec uv run --project "%s" --no-dev glossarian-%s "$@"' \
        "$MARKER" "$dir" "$name"
}

file_mode() {
    ls -ld "$1" | cut -c1-10
}

assert_all_shims() {
    local prefix="$1" dir="$2" name shim
    for name in $NAMES; do
        shim="$prefix/glossarian-$name"
        [ -f "$shim" ] || { fail "missing shim $shim"; continue; }
        assert_eq "$(file_mode "$shim")" "-rwxr-xr-x" "mode of glossarian-$name is exactly 0755"
        assert_eq "$(wc -l < "$shim" | tr -d ' ')" 3 "glossarian-$name has exactly three lines"
        assert_eq "$(cat "$shim")" "$(expected_shim "$dir" "$name")" "content of glossarian-$name"
    done
}

run_test() {
    CURRENT_TEST="$1"
    TESTS=$((TESTS + 1))
    "$1"
}

test_install_writes_both_marked_shims() {
    # Happy path + load-bearing shim output: exact body, marker, mode, absolute checkout root;
    # stdout/stderr split.
    local box rc out err; box=$(sandbox)
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >"$box/out" 2>"$box/err"; rc=$?
    out=$(cat "$box/out"); err=$(cat "$box/err")
    assert_eq "$rc" 0 "install exit code"
    assert_all_shims "$box/bin" "$SCRIPT_DIR"
    assert_eq "$(ls "$box/bin" | wc -l | tr -d ' ')" 2 "exactly two files in prefix"
    assert_contains "$out" "installed $box/bin/glossarian-check" "installed line on stdout"
    assert_contains "$out" "installed $box/bin/glossarian-gather" "installed line on stdout"
    assert_eq "$err" "" "nothing on stderr for a clean install"
    # The shim must never exec python3 directly (managed-policy refusal; contract anti-pattern).
    assert_not_contains "$(cat "$box/bin/glossarian-check")" "python3" "shim does not exec python3"
}

test_symlinked_installer_resolves_real_directory() {
    # Load-bearing: behavior 2 - shims embed the physical checkout directory.
    local box rc; box=$(sandbox)
    mkdir -p "$box/link"
    ln -s "$INSTALL" "$box/link/install.sh"
    "$BASH_BIN" "$box/link/install.sh" --prefix "$box/bin" >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 0 "symlinked install exit code"
    assert_all_shims "$box/bin" "$SCRIPT_DIR"
}

test_rerun_updates_marked_shims_in_place() {
    # Load-bearing: behavior 4 - re-run is the supported repair path after a move.
    local box out rc; box=$(sandbox)
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >/dev/null 2>&1
    echo "# stale extra line" >> "$box/bin/glossarian-gather"
    out=$("$BASH_BIN" "$INSTALL" --prefix "$box/bin" 2>&1); rc=$?
    assert_eq "$rc" 0 "re-run exit code"
    assert_contains "$out" "updated $box/bin/glossarian-gather" "updated line"
    assert_not_contains "$out" "installed $box/bin/glossarian-gather" "no installed line on re-run"
    assert_eq "$(cat "$box/bin/glossarian-gather")" "$(expected_shim "$SCRIPT_DIR" gather)" "stale content replaced"
    assert_all_shims "$box/bin" "$SCRIPT_DIR"
}

test_unmarked_file_refused_untouched_other_installed() {
    # Trust boundary: behaviors 4 and 5 - operator files are never overwritten; refusal on stderr.
    local box out err rc; box=$(sandbox)
    mkdir -p "$box/bin"
    printf '#!/bin/sh\necho mine\n' > "$box/bin/glossarian-check"
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >"$box/out" 2>"$box/err"; rc=$?
    out=$(cat "$box/out"); err=$(cat "$box/err")
    assert_eq "$rc" 1 "refusal exit code"
    assert_contains "$err" "Error: refusing to overwrite unmanaged file $box/bin/glossarian-check" "refusal on stderr names the path"
    assert_not_contains "$out" "refusing" "refusal not on stdout"
    assert_contains "$out" "installed $box/bin/glossarian-gather" "progress still on stdout"
    assert_eq "$(cat "$box/bin/glossarian-check")" "$(printf '#!/bin/sh\necho mine')" "unmarked file untouched"
    assert_eq "$(cat "$box/bin/glossarian-gather")" "$(expected_shim "$SCRIPT_DIR" gather)" "glossarian-gather still installed (positive control)"
    # A directory at a shim path is unmanaged too.
    local box2; box2=$(sandbox)
    mkdir -p "$box2/bin/glossarian-gather"
    "$BASH_BIN" "$INSTALL" --prefix "$box2/bin" >"$box2/out" 2>"$box2/err"; rc=$?
    assert_eq "$rc" 1 "directory refusal exit code"
    assert_contains "$(cat "$box2/err")" "Error: refusing to overwrite unmanaged file $box2/bin/glossarian-gather" "directory at shim path is unmanaged"
    [ -d "$box2/bin/glossarian-gather" ] || fail "directory at shim path must be left alone"
    assert_eq "$(cat "$box2/bin/glossarian-check")" "$(expected_shim "$SCRIPT_DIR" check)" "glossarian-check still installed (positive control)"
    # Dry run applies the same refusal and exit code without touching anything.
    local box3; box3=$(sandbox)
    mkdir -p "$box3/bin"
    printf '#!/bin/sh\necho mine\n' > "$box3/bin/glossarian-check"
    "$BASH_BIN" "$INSTALL" --prefix "$box3/bin" --dry-run >"$box3/out" 2>"$box3/err"; rc=$?
    assert_eq "$rc" 1 "dry-run refusal exit code"
    assert_contains "$(cat "$box3/err")" "refusing to overwrite unmanaged file $box3/bin/glossarian-check" "dry-run refusal line"
    assert_contains "$(cat "$box3/out")" "would write $box3/bin/glossarian-gather" "dry-run still lists the other"
    assert_eq "$(ls "$box3/bin" | wc -l | tr -d ' ')" 1 "dry-run wrote nothing"
    assert_eq "$(cat "$box3/bin/glossarian-check")" "$(printf '#!/bin/sh\necho mine')" "dry-run left the unmarked file alone"
}

test_uninstall_removes_only_marked_shims() {
    # Load-bearing: behavior 9; behavior 3 - uninstall needs no project files.
    local box out err rc; box=$(sandbox)
    mkdir -p "$box/bin"
    printf '#!/bin/sh\necho mine\n' > "$box/bin/glossarian-check"
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >/dev/null 2>&1
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --uninstall >"$box/out" 2>"$box/err"; rc=$?
    out=$(cat "$box/out"); err=$(cat "$box/err")
    assert_eq "$rc" 0 "uninstall exit code"
    [ ! -e "$box/bin/glossarian-gather" ] || fail "glossarian-gather should have been removed"
    assert_contains "$out" "removed $box/bin/glossarian-gather" "removed line on stdout"
    [ -e "$box/bin/glossarian-check" ] || fail "unmarked glossarian-check should remain"
    assert_eq "$(cat "$box/bin/glossarian-check")" "$(printf '#!/bin/sh\necho mine')" "unmarked file untouched by uninstall"
    assert_contains "$err" "Note: leaving unmanaged file $box/bin/glossarian-check" "uninstall notes the unmanaged file on stderr"
    assert_not_contains "$out" "Note:" "note not on stdout"
    [ -d "$box/bin" ] || fail "uninstall must not remove the prefix directory"
    # Uninstalling an empty prefix is a silent success.
    "$BASH_BIN" "$INSTALL" --prefix "$box/none" --uninstall >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 0 "uninstall of nothing exit code"
    # Uninstall works from a copy of the installer that has no project files beside it.
    local box2; box2=$(sandbox)
    "$BASH_BIN" "$INSTALL" --prefix "$box2/bin" >/dev/null 2>&1
    mkdir -p "$box2/alt"
    cp "$INSTALL" "$box2/alt/glossarian_install.sh"
    "$BASH_BIN" "$box2/alt/glossarian_install.sh" --prefix "$box2/bin" --uninstall >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 0 "uninstall without project files exit code"
    [ ! -e "$box2/bin/glossarian-check" ] || fail "uninstall without project files should still remove shims"
}

test_dry_run_writes_nothing() {
    # Capability boundary: behavior 6.
    local box out rc; box=$(sandbox)
    out=$("$BASH_BIN" "$INSTALL" --prefix "$box/bin" --dry-run 2>&1); rc=$?
    assert_eq "$rc" 0 "dry-run exit code"
    [ ! -e "$box/bin" ] || fail "dry-run must not create the prefix"
    assert_contains "$out" "would write $box/bin/glossarian-check" "would-write line"
    assert_contains "$out" "would write $box/bin/glossarian-gather" "would-write line"
    assert_not_contains "$out" "installed " "dry-run prints no installed lines"
    # Dry-run uninstall leaves installed shims alone.
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >/dev/null 2>&1
    out=$("$BASH_BIN" "$INSTALL" --prefix "$box/bin" --uninstall --dry-run 2>&1); rc=$?
    assert_eq "$rc" 0 "dry-run uninstall exit code"
    assert_contains "$out" "would remove $box/bin/glossarian-check" "would-remove line"
    assert_all_shims "$box/bin" "$SCRIPT_DIR"
}

test_check_passes_with_fake_uv_exit_0() {
    # Load-bearing: behavior 10 - every shim is run with --help through uv, with the guard env
    # and the exact project/no-dev argv the contract declares.
    local box out err rc name; box=$(sandbox)
    make_fake_uv "$box/fakebin" 0
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >/dev/null 2>&1
    PATH="$box/fakebin:$PATH" "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --check >"$box/out" 2>"$box/err"; rc=$?
    out=$(cat "$box/out"); err=$(cat "$box/err")
    assert_eq "$rc" 0 "check exit code"
    for name in $NAMES; do
        assert_contains "$out" "PASS glossarian-$name" "PASS line on stdout"
        assert_file_contains "$box/fakebin/calls.log" "uv run --project $SCRIPT_DIR --no-dev glossarian-$name --help"
    done
    assert_not_contains "$out" "FAIL" "no FAIL lines"
    assert_eq "$err" "" "nothing on stderr for a passing check"
    assert_eq "$(grep -c "^uv run --project " "$box/fakebin/calls.log")" 2 "two uv invocations"
    assert_eq "$(grep -c "^env UV_PYTHON_DOWNLOADS=never\$" "$box/fakebin/calls.log")" 2 "guard env set on every invocation"
}

test_check_reports_failures_with_fake_uv_exit_3() {
    # Load-bearing: behavior 10 - a failing shim (e.g. a moved checkout) is reported, exit 1.
    local box out rc; box=$(sandbox)
    make_fake_uv "$box/fakebin" 3
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >/dev/null 2>&1
    out=$(PATH="$box/fakebin:$PATH" "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --check 2>&1); rc=$?
    assert_eq "$rc" 1 "check exit code"
    assert_contains "$out" "FAIL glossarian-check (exit 3)" "FAIL line with exit code"
    assert_contains "$out" "FAIL glossarian-gather (exit 3)" "FAIL line with exit code"
    assert_not_contains "$out" "PASS" "no PASS lines"
}

test_check_never_runs_missing_unmanaged_or_stale_shims() {
    # Behavior 10 / anti-pattern: only byte-identical marked shims are executed.
    local box out rc; box=$(sandbox)
    make_fake_uv "$box/fakebin" 0
    # Case A: missing + unmanaged.
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >/dev/null 2>&1
    rm -f "$box/bin/glossarian-check"
    printf '#!/bin/sh\necho ran-foreign >> "%s/foreign.log"\n' "$box" > "$box/bin/glossarian-gather"
    chmod +x "$box/bin/glossarian-gather"
    out=$(PATH="$box/fakebin:$PATH" "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --check 2>&1); rc=$?
    assert_eq "$rc" 1 "check exit code with missing/unmanaged"
    assert_contains "$out" "FAIL glossarian-check (not installed)" "not-installed line"
    assert_contains "$out" "FAIL glossarian-gather (unmanaged file, not run)" "unmanaged line"
    [ ! -e "$box/foreign.log" ] || fail "unmanaged files must not be executed by --check"
    [ ! -e "$box/fakebin/calls.log" ] || fail "nothing healthy to run: uv must not be invoked"
    # Case B: stale (marker present, body differs) beside one healthy shim; positive control
    # that the healthy shim IS run.
    local box2; box2=$(sandbox)
    make_fake_uv "$box2/fakebin" 0
    "$BASH_BIN" "$INSTALL" --prefix "$box2/bin" >/dev/null 2>&1
    printf '#!/bin/sh\n# %s\necho ran-stale >> "%s/foreign.log"\n' "$MARKER" "$box2" > "$box2/bin/glossarian-gather"
    chmod +x "$box2/bin/glossarian-gather"
    out=$(PATH="$box2/fakebin:$PATH" "$BASH_BIN" "$INSTALL" --prefix "$box2/bin" --check 2>&1); rc=$?
    assert_eq "$rc" 1 "check exit code with stale"
    assert_contains "$out" "FAIL glossarian-gather (stale or foreign shim, not run)" "stale line"
    assert_contains "$out" "PASS glossarian-check" "healthy shim still passes"
    [ ! -e "$box2/foreign.log" ] || fail "stale files must not be executed by --check"
    assert_eq "$(grep -c "^uv run" "$box2/fakebin/calls.log")" 1 "only the one healthy shim was run"
}

test_check_requires_uv_on_path() {
    # Behavior 10 - says so and exits 1 when uv is missing; runs nothing.
    local box out rc; box=$(sandbox)
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" >/dev/null 2>&1
    mkdir -p "$box/toolbin"
    ln -s "$(command -v dirname)" "$box/toolbin/dirname"
    out=$(PATH="$box/toolbin" "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --check 2>&1); rc=$?
    assert_eq "$rc" 1 "check without uv exit code"
    assert_contains "$out" "uv not found on PATH" "missing-uv message"
    assert_not_contains "$out" "PASS" "nothing run without uv"
}

test_path_hint_present_when_prefix_off_path_absent_when_on() {
    # Behavior 7.
    local box out rc hint; box=$(sandbox)
    hint="export PATH=\"$box/bin:\$PATH\""
    out=$("$BASH_BIN" "$INSTALL" --prefix "$box/bin" 2>&1); rc=$?
    assert_eq "$rc" 0 "install exit code"
    assert_contains "$out" "$hint" "exact export line for custom prefix"
    out=$(PATH="$box/bin:$PATH" "$BASH_BIN" "$INSTALL" --prefix "$box/bin" 2>&1); rc=$?
    assert_eq "$rc" 0 "install exit code with prefix on PATH"
    assert_not_contains "$out" "export PATH=" "no hint when prefix on PATH"
    # Default prefix: shims land in $HOME/.local/bin and the hint uses the literal $HOME form.
    local home; home=$(sandbox)
    out=$(HOME="$home" "$BASH_BIN" "$INSTALL" 2>&1); rc=$?
    assert_eq "$rc" 0 "default-prefix exit code"
    assert_all_shims "$home/.local/bin" "$SCRIPT_DIR"
    assert_contains "$out" 'export PATH="$HOME/.local/bin:$PATH"' "literal HOME export line"
}

test_first_run_note_printed_after_install() {
    # Behavior 8.
    local box out; box=$(sandbox)
    out=$("$BASH_BIN" "$INSTALL" --prefix "$box/bin" 2>&1)
    assert_contains "$out" "need uv on PATH" "uv note"
    assert_contains "$out" "$SCRIPT_DIR/.venv" "venv path named"
    assert_contains "$out" "glossarian_install.sh --check" "check hint"
    out=$("$BASH_BIN" "$INSTALL" --prefix "$box/bin" --uninstall 2>&1)
    assert_not_contains "$out" "need uv on PATH" "no first-run note on uninstall"
}

test_prefix_with_space_works() {
    # Edge case: prefix paths are quoted everywhere.
    local box out rc; box=$(sandbox)
    out=$("$BASH_BIN" "$INSTALL" --prefix "$box/my bin dir" 2>&1); rc=$?
    assert_eq "$rc" 0 "spaced prefix exit code"
    assert_all_shims "$box/my bin dir" "$SCRIPT_DIR"
    assert_contains "$out" "export PATH=\"$box/my bin dir:\$PATH\"" "hint quotes the spaced prefix"
    "$BASH_BIN" "$INSTALL" --prefix "$box/my bin dir" --uninstall >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 0 "spaced prefix uninstall exit code"
    [ ! -e "$box/my bin dir/glossarian-check" ] || fail "spaced prefix shim not removed"
}

test_missing_project_files_refused_before_writing() {
    # Behavior 3 - precondition check runs before mkdir/write, for install and dry run.
    local box out rc; box=$(sandbox)
    mkdir -p "$box/alt"
    cp "$INSTALL" "$box/alt/glossarian_install.sh"
    out=$("$BASH_BIN" "$box/alt/glossarian_install.sh" --prefix "$box/bin" 2>&1); rc=$?
    assert_eq "$rc" 1 "missing pyproject exit code"
    assert_contains "$out" "missing $box/alt/pyproject.toml" "names the missing file"
    [ ! -e "$box/bin" ] || fail "nothing may be written when a project file is missing"
    out=$("$BASH_BIN" "$box/alt/glossarian_install.sh" --prefix "$box/bin" --dry-run 2>&1); rc=$?
    assert_eq "$rc" 1 "missing pyproject dry-run exit code"
    # pyproject present but the package entry module missing is refused too.
    : > "$box/alt/pyproject.toml"
    out=$("$BASH_BIN" "$box/alt/glossarian_install.sh" --prefix "$box/bin" 2>&1); rc=$?
    assert_eq "$rc" 1 "missing cli.py exit code"
    assert_contains "$out" "missing $box/alt/src/glossarian/cli.py" "names the missing module"
    [ ! -e "$box/bin" ] || fail "nothing may be written when cli.py is missing"
    # Positive control: with both files present the same copy installs.
    mkdir -p "$box/alt/src/glossarian" && : > "$box/alt/src/glossarian/cli.py"
    "$BASH_BIN" "$box/alt/glossarian_install.sh" --prefix "$box/bin" >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 0 "complete copy installs"
    assert_all_shims "$box/bin" "$box/alt"
}

test_repo_root_with_unsafe_characters_refused() {
    # Behavior 2 - each character that breaks the double-quoted shim path is refused, in
    # install and check mode alike.
    local box rc out dir label nl; box=$(sandbox)
    nl=$(printf '\n.'); nl=${nl%.}
    for label in dq dollar backtick backslash newline; do
        case "$label" in
            dq) dir="$box/has\"quote" ;;
            dollar) dir="$box/has\$dollar" ;;
            backtick) dir="$box/has\`tick" ;;
            backslash) dir="$box/has\\slash" ;;
            newline) dir="$box/has${nl}line" ;;
        esac
        make_installer_copy "$dir"
        out=$("$BASH_BIN" "$dir/glossarian_install.sh" --prefix "$box/bin-$label" 2>&1); rc=$?
        assert_eq "$rc" 1 "install refused for $label"
        assert_contains "$out" "cannot be embedded in a shim" "bad-character message for $label"
        [ ! -e "$box/bin-$label" ] || fail "nothing may be written for a bad checkout directory ($label)"
        out=$("$BASH_BIN" "$dir/glossarian_install.sh" --prefix "$box/bin-$label" --check 2>&1); rc=$?
        assert_eq "$rc" 1 "check refused for $label"
        assert_contains "$out" "cannot be embedded in a shim" "bad-character message in check for $label"
    done
    # Control: a copy in a safe directory installs fine.
    make_installer_copy "$box/safe dir"
    "$BASH_BIN" "$box/safe dir/glossarian_install.sh" --prefix "$box/bin-safe" >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 0 "safe copy installs"
    assert_all_shims "$box/bin-safe" "$box/safe dir"
}

test_usage_errors_exit_2_and_help_exits_0() {
    # Behavior 1.
    local box out rc; box=$(sandbox)
    "$BASH_BIN" "$INSTALL" --bogus >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 2 "unknown option"
    "$BASH_BIN" "$INSTALL" --prefix >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 2 "valueless --prefix"
    "$BASH_BIN" "$INSTALL" --prefix "" >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 2 "empty --prefix"
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --uninstall --check >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 2 "--uninstall with --check"
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --uninstall --uninstall >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 2 "repeated --uninstall"
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --check --check >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 2 "repeated --check"
    "$BASH_BIN" "$INSTALL" --prefix "$box/bin" --check --dry-run >/dev/null 2>&1; rc=$?
    assert_eq "$rc" 2 "--check with --dry-run"
    out=$(env -u HOME "$BASH_BIN" "$INSTALL" 2>&1); rc=$?
    assert_eq "$rc" 2 "HOME unset without --prefix"
    [ ! -e "$box/bin" ] || fail "usage errors must write nothing"
    "$BASH_BIN" "$INSTALL" --bogus >"$box/out" 2>"$box/err"
    assert_eq "$(cat "$box/out")" "" "usage error prints nothing on stdout"
    assert_contains "$(cat "$box/err")" "Error: unknown option: --bogus" "usage error on stderr"
    assert_contains "$(cat "$box/err")" "Usage:" "usage text follows the error on stderr"
    "$BASH_BIN" "$INSTALL" --help >"$box/out" 2>"$box/err"; rc=$?
    assert_eq "$rc" 0 "help exit code"
    assert_contains "$(cat "$box/out")" "Usage:" "help text on stdout"
    assert_contains "$(cat "$box/out")" "--prefix DIR" "help lists options"
    assert_eq "$(cat "$box/err")" "" "help prints nothing on stderr"
}

run_test test_install_writes_both_marked_shims
run_test test_symlinked_installer_resolves_real_directory
run_test test_rerun_updates_marked_shims_in_place
run_test test_unmarked_file_refused_untouched_other_installed
run_test test_uninstall_removes_only_marked_shims
run_test test_dry_run_writes_nothing
run_test test_check_passes_with_fake_uv_exit_0
run_test test_check_reports_failures_with_fake_uv_exit_3
run_test test_check_never_runs_missing_unmanaged_or_stale_shims
run_test test_check_requires_uv_on_path
run_test test_path_hint_present_when_prefix_off_path_absent_when_on
run_test test_first_run_note_printed_after_install
run_test test_prefix_with_space_works
run_test test_missing_project_files_refused_before_writing
run_test test_repo_root_with_unsafe_characters_refused
run_test test_usage_errors_exit_2_and_help_exits_0

echo "$TESTS tests, $FAILURES failure(s)"
[ "$FAILURES" -eq 0 ]
