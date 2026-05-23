#!/usr/bin/env bash
# install.sh — bootstrap memorytalk on a fresh machine.
#
# Creates a self-contained venv at ~/.memory.talk/venv and installs the
# latest memorytalk release from PyPI into it. Idempotent: re-running
# upgrades in place.
#
# Layout after install (shared with runtime data root):
#   ~/.memory.talk/                        ← install root + data root
#   ~/.memory.talk/venv/                   ← Python venv (this script)
#   ~/.memory.talk/venv/bin/memory.talk    ← entry point
#   ~/.memory.talk/settings.json           ← created by `memory.talk setup`
#   ~/.memory.talk/memory.db, sessions/, cards/, ...  ← runtime data
#
# Usage:
#   ./install.sh
#   curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
#   MEMORY_TALK_INSTALL_DIR=/opt/memory.talk ./install.sh   # custom path
#
# Requires: bash 3.2+, Python 3.10+, network access to PyPI.

set -euo pipefail

INSTALL_DIR="${MEMORY_TALK_INSTALL_DIR:-$HOME/.memory.talk}"
VENV_DIR="$INSTALL_DIR/venv"
PACKAGE="memorytalk"
MIN_PY_MAJOR=3
MIN_PY_MINOR=10

# ────────── tiny output helpers ──────────

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_BOLD="$(printf '\033[1m')"
    C_DIM="$(printf '\033[2m')"
    C_GREEN="$(printf '\033[32m')"
    C_YELLOW="$(printf '\033[33m')"
    C_RED="$(printf '\033[31m')"
    C_RESET="$(printf '\033[0m')"
else
    C_BOLD="" C_DIM="" C_GREEN="" C_YELLOW="" C_RED="" C_RESET=""
fi

step()  { printf '%s▸%s %s\n'    "$C_BOLD"   "$C_RESET" "$*"; }
ok()    { printf '  %s✓%s %s\n'  "$C_GREEN"  "$C_RESET" "$*"; }
warn()  { printf '  %s!%s %s\n'  "$C_YELLOW" "$C_RESET" "$*" >&2; }
fail()  { printf '  %s✗%s %s\n'  "$C_RED"    "$C_RESET" "$*" >&2; exit 1; }
hint()  { printf '  %s%s%s\n'    "$C_DIM"    "$*"     "$C_RESET"; }

# ────────── 0. sanity warnings ──────────

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    warn "Running as root — memory.talk will install to /root/memory.talk."
    warn "Usually you want to run this as your normal user instead."
fi

# ────────── 1. detect a Python that meets the floor ──────────

step "Looking for Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}..."
PYTHON=""
# Try most-specific first so we prefer the newest interpreter installed.
for cand in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
        major="${ver%.*}"
        minor="${ver#*.}"
        if [ "$major" -gt "$MIN_PY_MAJOR" ] || \
           { [ "$major" -eq "$MIN_PY_MAJOR" ] && [ "$minor" -ge "$MIN_PY_MINOR" ]; }; then
            PYTHON="$(command -v "$cand")"
            ok "found $PYTHON (Python $ver)"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    fail "No Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR} found on PATH. Install one and re-run."
fi

# Some distros split the venv module into a separate apt/yum package.
# Check up front so we fail with an actionable message rather than a
# cryptic ModuleNotFoundError later.
if ! "$PYTHON" -c "import venv" >/dev/null 2>&1; then
    fail "$PYTHON does not have the 'venv' module. On Debian/Ubuntu: apt install python3-venv"
fi

# ────────── 2. install dir + venv ──────────

step "Setting up install dir at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

if [ -x "$VENV_DIR/bin/python" ] || [ -x "$VENV_DIR/bin/python3" ]; then
    ok "venv already exists, reusing"
else
    if [ -e "$VENV_DIR" ]; then
        # Path exists but isn't a usable venv → user must clean it up
        # explicitly. Don't silently nuke it; might be their data.
        fail "$VENV_DIR exists but isn't a usable venv. Remove it manually and re-run."
    fi
    hint "creating venv (this may take a few seconds)..."
    "$PYTHON" -m venv "$VENV_DIR"
    ok "created venv at $VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ────────── 3. pick fastest PyPI mirror ──────────
#
# Many users (esp. mainland China) get vastly faster downloads from a
# domestic mirror than from pypi.org. We race the two and use whichever
# answers fastest. ``MEMORY_TALK_INDEX_URL=...`` overrides the test —
# use it to force a specific mirror (or set it to '' / pypi.org URL to
# pin to official).

PYPI_OFFICIAL="https://pypi.org/simple/"
PYPI_ALIYUN="https://mirrors.aliyun.com/pypi/simple/"
# Probe each mirror with a real metadata request — the memorytalk page
# is small and exists on both. ``time_total`` includes DNS + connect +
# TLS + body, so it's a good proxy for "how fast will pip resolve from
# here". 5s timeout caps the worst case.
_probe_mirror() {
    local url="$1"
    local probe="${url%/}/memorytalk/"
    local result code time
    if ! command -v curl >/dev/null 2>&1; then
        echo "FAIL"; return
    fi
    if result=$(curl -o /dev/null -s -w '%{http_code} %{time_total}' \
                     --max-time 5 "$probe" 2>/dev/null); then
        code="${result%% *}"
        time="${result##* }"
        if [ "$code" = "200" ]; then
            echo "$time"
            return
        fi
    fi
    echo "FAIL"
}

PIP_INDEX_ARGS=()
if [ -n "${MEMORY_TALK_INDEX_URL:-}" ]; then
    step "Using PyPI mirror from \$MEMORY_TALK_INDEX_URL..."
    PIP_INDEX_ARGS=(--index-url "$MEMORY_TALK_INDEX_URL")
    ok "pinned to $MEMORY_TALK_INDEX_URL"
else
    step "Picking the fastest PyPI mirror..."
    hint "probing pypi.org + mirrors.aliyun.com (5s timeout each)..."
    T_OFFICIAL="$(_probe_mirror "$PYPI_OFFICIAL")"
    T_ALIYUN="$(_probe_mirror "$PYPI_ALIYUN")"

    if [ "$T_OFFICIAL" = "FAIL" ] && [ "$T_ALIYUN" = "FAIL" ]; then
        warn "Both mirrors unreachable, falling back to pip's default index."
    elif [ "$T_OFFICIAL" = "FAIL" ]; then
        ok "pypi.org unreachable, using aliyun (${T_ALIYUN}s)"
        PIP_INDEX_ARGS=(--index-url "$PYPI_ALIYUN")
    elif [ "$T_ALIYUN" = "FAIL" ]; then
        ok "aliyun unreachable, using pypi.org (${T_OFFICIAL}s)"
        PIP_INDEX_ARGS=(--index-url "$PYPI_OFFICIAL")
    else
        # Both reachable — pick faster. bash doesn't compare floats; use awk.
        if awk "BEGIN{exit !(${T_OFFICIAL} < ${T_ALIYUN})}"; then
            ok "pypi.org wins (${T_OFFICIAL}s vs aliyun ${T_ALIYUN}s)"
            PIP_INDEX_ARGS=(--index-url "$PYPI_OFFICIAL")
        else
            ok "aliyun wins (${T_ALIYUN}s vs pypi.org ${T_OFFICIAL}s)"
            PIP_INDEX_ARGS=(--index-url "$PYPI_ALIYUN")
        fi
    fi
fi

# ────────── 4. pip install ──────────

step "Upgrading pip inside the venv..."
"$VENV_PY" -m pip install --quiet --disable-pip-version-check \
    "${PIP_INDEX_ARGS[@]}" --upgrade pip
ok "pip is current"

step "Installing $PACKAGE from PyPI..."
hint "this pulls lancedb / pyarrow / fastapi etc. — first run can take 1–3 min"
"$VENV_PIP" install --disable-pip-version-check \
    "${PIP_INDEX_ARGS[@]}" --upgrade "$PACKAGE"
ok "install finished"

# ────────── 5. verify ──────────

step "Verifying..."
if ! VERSION="$("$VENV_DIR/bin/memory.talk" --version 2>/dev/null)"; then
    fail "memory.talk installed but --version failed. Run '$VENV_DIR/bin/memory.talk --help' to investigate."
fi
ok "$PACKAGE $VERSION is ready"

# ────────── 6. expose `memory.talk` globally ──────────
#
# Drop a symlink into ``~/.local/bin/`` (XDG convention; on Ubuntu / Mac
# / Fedora this dir is already on the default PATH via ~/.profile). If
# it's not in PATH yet, warn the user with the exact line to add.
#
# Overrides:
#   MEMORY_TALK_BIN_DIR=/some/where    symlink target dir
#   MEMORY_TALK_NO_BIN_LINK=1          skip linking entirely

BIN_LINK_DIR="${MEMORY_TALK_BIN_DIR:-$HOME/.local/bin}"
BIN_LINK="$BIN_LINK_DIR/memory.talk"
ENTRY="$VENV_DIR/bin/memory.talk"

if [ -n "${MEMORY_TALK_NO_BIN_LINK:-}" ]; then
    step "Skipping global bin link (MEMORY_TALK_NO_BIN_LINK set)"
else
    step "Exposing memory.talk in $BIN_LINK_DIR..."
    mkdir -p "$BIN_LINK_DIR"
    if [ -L "$BIN_LINK" ]; then
        # Existing symlink — replace transparently (likely our own from
        # a prior install run).
        ln -sf "$ENTRY" "$BIN_LINK"
        ok "updated symlink $BIN_LINK"
    elif [ -e "$BIN_LINK" ]; then
        # Regular file at this path — don't clobber user data.
        warn "$BIN_LINK already exists as a regular file. Skipping link."
        hint "Remove it and re-run install.sh, or set MEMORY_TALK_BIN_DIR to another dir."
    else
        ln -s "$ENTRY" "$BIN_LINK"
        ok "created symlink $BIN_LINK"
    fi

    # Path check — many shells don't include ~/.local/bin unless the
    # user's rc explicitly adds it. Tell them what to do.
    case ":$PATH:" in
        *":$BIN_LINK_DIR:"*)
            ok "$BIN_LINK_DIR is already on \$PATH — run: memory.talk --version"
            ;;
        *)
            warn "$BIN_LINK_DIR is not on \$PATH yet. Add this line to your shell rc:"
            hint "  export PATH=\"$BIN_LINK_DIR:\$PATH\""
            ;;
    esac
fi

# ────────── 7. post-install instructions ──────────

cat <<EOF

${C_BOLD}Installation complete.${C_RESET}

Entry point:    ${C_BOLD}$ENTRY${C_RESET}
Global link:    $BIN_LINK
Data root:      $INSTALL_DIR

Next steps (after opening a new shell so PATH updates take effect):

  memory.talk setup            ${C_DIM}# interactive first-time configure${C_RESET}
  memory.talk server start
  memory.talk --help

Future upgrades:

  memory.talk upgrade          ${C_DIM}# pulls latest from PyPI into this venv${C_RESET}

EOF
