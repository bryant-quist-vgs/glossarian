#!/usr/bin/env bash
# glossarian_install.sh - install PATH shims (glossarian-check, glossarian-gather) for this checkout.
# Built against contract v0 (glossarian_install_contract.md).

set -euo pipefail
unset CDPATH

MARKER="managed-by: glossarian-install"
NAMES="check gather"
TMP_FILE=""

cleanup_tmp() {
    [ -n "$TMP_FILE" ] && rm -f "$TMP_FILE"
    return 0
}
trap cleanup_tmp EXIT

usage() {
    cat <<'EOF'
Usage: glossarian_install.sh [--prefix DIR] [--dry-run]
       glossarian_install.sh [--prefix DIR] [--dry-run] --uninstall
       glossarian_install.sh [--prefix DIR] --check
       glossarian_install.sh --help

Installs one bash shim per glossarian command into DIR (default: $HOME/.local/bin):
  glossarian-check glossarian-gather
Each shim runs: uv run --project "<this checkout>" --no-dev glossarian-<name> "$@"
and carries a '# managed-by: glossarian-install' marker. Files without the marker are
never overwritten, removed, or executed.

Options:
  --prefix DIR   bin directory to write shims into (default: $HOME/.local/bin)
  --uninstall    remove marked shims from the prefix
  --check        run every installed shim with --help and report PASS/FAIL (needs uv)
  --dry-run      print what install/uninstall would do; write nothing
  -h, --help     show this help

Exit codes: 0 success, 1 refusal or failed check, 2 usage error.
EOF
}

die_usage() {
    echo "Error: $*" >&2
    usage >&2
    exit 2
}

die() {
    echo "Error: $*" >&2
    exit 1
}

# Resolve the installer's own directory through any symlink chain, physically.
resolve_script_dir() {
    local src="$1" dir
    while [ -L "$src" ]; do
        dir=$(cd -P -- "$(dirname -- "$src")" && pwd)
        src=$(readlink "$src")
        case "$src" in
            /*) ;;
            *) src="$dir/$src" ;;
        esac
    done
    cd -P -- "$(dirname -- "$src")" && pwd
}

# True only for a regular file (or symlink to one) containing the marker.
is_marked() {
    [ -f "$1" ] && grep -qF "$MARKER" "$1" 2>/dev/null
}

shim_body() {
    local repo_root="$1" name="$2"
    printf '#!/usr/bin/env bash\n# %s\nexec uv run --project "%s" --no-dev glossarian-%s "$@"\n' \
        "$MARKER" "$repo_root" "$name"
}

# Refuse a checkout directory whose path cannot be embedded in a double-quoted shim string.
check_repo_root() {
    local repo_root="$1" nl
    nl=$(printf '\n.')
    nl=${nl%.}
    case "$repo_root" in
        *\"*|*\$*|*\`*|*\\*|*"$nl"*)
            die "checkout directory contains a character (\" \$ \` \\ or newline) that cannot be embedded in a shim: $repo_root" ;;
    esac
}

check_project_files() {
    local repo_root="$1" rel
    for rel in pyproject.toml src/glossarian/cli.py; do
        [ -f "$repo_root/$rel" ] || die "missing $repo_root/$rel; run the installer from the root of a glossarian checkout"
    done
}

print_path_hint() {
    local prefix="$1" entry rest="$PATH:" on_path=0 shown
    while [ -n "$rest" ]; do
        entry="${rest%%:*}"
        rest="${rest#*:}"
        [ "$entry" = "$prefix" ] && on_path=1
    done
    if [ "$on_path" -eq 0 ]; then
        shown="$prefix"
        [ -n "${HOME:-}" ] && [ "$prefix" = "$HOME/.local/bin" ] && shown='$HOME/.local/bin'
        echo
        echo "$prefix is not on your PATH. Add this line to your shell rc file, then open a new shell:"
        echo "  export PATH=\"$shown:\$PATH\""
    fi
}

print_first_run_note() {
    local repo_root="$1"
    cat <<EOF

The shims need uv on PATH. The first run creates $repo_root/.venv
(fetching the hatchling build backend if uv's cache lacks it); later runs are offline.
Verify the install with: glossarian_install.sh --check
EOF
}

cmd_install() {
    local repo_root="$1" prefix="$2" dry_run="$3" name target failed=0 existed

    check_project_files "$repo_root"
    if [ "$dry_run" -eq 0 ]; then
        mkdir -p -- "$prefix" || die "cannot create $prefix"
    fi

    for name in $NAMES; do
        target="$prefix/glossarian-$name"
        existed=0
        if [ -e "$target" ] || [ -L "$target" ]; then
            existed=1
            if ! is_marked "$target"; then
                echo "Error: refusing to overwrite unmanaged file $target" >&2
                failed=1
                continue
            fi
        fi
        if [ "$dry_run" -eq 1 ]; then
            echo "would write $target"
            continue
        fi
        TMP_FILE=$(mktemp "$prefix/.glossarian-$name.XXXXXX") || die "cannot create temp file in $prefix"
        shim_body "$repo_root" "$name" > "$TMP_FILE"
        chmod 0755 "$TMP_FILE"
        mv -f -- "$TMP_FILE" "$target"
        TMP_FILE=""
        if [ "$existed" -eq 1 ]; then
            echo "updated $target"
        else
            echo "installed $target"
        fi
    done

    print_path_hint "$prefix"
    print_first_run_note "$repo_root"
    [ "$failed" -eq 0 ] || exit 1
}

cmd_uninstall() {
    local prefix="$1" dry_run="$2" name target
    for name in $NAMES; do
        target="$prefix/glossarian-$name"
        [ -e "$target" ] || [ -L "$target" ] || continue
        if ! is_marked "$target"; then
            echo "Note: leaving unmanaged file $target" >&2
            continue
        fi
        if [ "$dry_run" -eq 1 ]; then
            echo "would remove $target"
        else
            rm -f -- "$target"
            echo "removed $target"
        fi
    done
}

cmd_check() {
    local repo_root="$1" prefix="$2" name target failed=0 rc
    command -v uv >/dev/null 2>&1 || die "uv not found on PATH; the shims need uv (https://docs.astral.sh/uv/) - install it, then re-run --check"
    for name in $NAMES; do
        target="$prefix/glossarian-$name"
        if [ ! -e "$target" ] && [ ! -L "$target" ]; then
            echo "FAIL glossarian-$name (not installed)"
            failed=1
            continue
        fi
        if ! is_marked "$target"; then
            echo "FAIL glossarian-$name (unmanaged file, not run)"
            failed=1
            continue
        fi
        if ! cmp -s -- "$target" <(shim_body "$repo_root" "$name"); then
            echo "FAIL glossarian-$name (stale or foreign shim, not run)"
            failed=1
            continue
        fi
        rc=0
        UV_PYTHON_DOWNLOADS=never "$target" --help >/dev/null 2>&1 || rc=$?
        if [ "$rc" -eq 0 ]; then
            echo "PASS glossarian-$name"
        else
            echo "FAIL glossarian-$name (exit $rc)"
            failed=1
        fi
    done
    [ "$failed" -eq 0 ] || exit 1
}

main() {
    local prefix="" prefix_given=0 mode="install" dry_run=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --prefix)
                [ $# -ge 2 ] || die_usage "--prefix requires a value"
                [ -n "$2" ] || die_usage "--prefix requires a non-empty value"
                prefix="$2"; prefix_given=1; shift 2 ;;
            --uninstall)
                [ "$mode" = "install" ] || die_usage "--uninstall and --check may each be given once and not together"
                mode="uninstall"; shift ;;
            --check)
                [ "$mode" = "install" ] || die_usage "--uninstall and --check may each be given once and not together"
                mode="check"; shift ;;
            --dry-run) dry_run=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) die_usage "unknown option: $1" ;;
        esac
    done
    if [ "$mode" = "check" ] && [ "$dry_run" -eq 1 ]; then
        die_usage "--check cannot be combined with --dry-run"
    fi
    if [ "$prefix_given" -eq 0 ]; then
        [ -n "${HOME:-}" ] || die_usage "HOME is unset; pass --prefix DIR"
        prefix="$HOME/.local/bin"
    fi

    local repo_root
    repo_root=$(resolve_script_dir "${BASH_SOURCE[0]}")
    check_repo_root "$repo_root"

    case "$mode" in
        install) cmd_install "$repo_root" "$prefix" "$dry_run" ;;
        uninstall) cmd_uninstall "$prefix" "$dry_run" ;;
        check) cmd_check "$repo_root" "$prefix" ;;
    esac
}

main "$@"
