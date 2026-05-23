#!/usr/bin/env bash
# install.sh — bootstrap memorytalk on a fresh machine.
#
# Creates a self-contained venv at ~/memory-talk/venv and installs the
# latest memorytalk release from PyPI into it. Idempotent: re-running
# upgrades in place.
#
# Layout after install:
#   ~/memory-talk/           ← install root (this script's INSTALL_DIR)
#   ~/memory-talk/venv/      ← Python venv, isolated from system Python
#   ~/memory-talk/venv/bin/memory-talk   ← entry point
#
# Note: the *data* root is a different directory (~/.memory-talk/, with
# the dot) created later by `memory-talk setup`. We don't touch it here.
#
# Usage:
#   ./install.sh
#   curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
#   MEMORY_TALK_INSTALL_DIR=/opt/memory-talk ./install.sh   # custom path
#
# Requires: bash 3.2+, Python 3.10+, network access to PyPI.

set -euo pipefail

INSTALL_DIR="${MEMORY_TALK_INSTALL_DIR:-$HOME/memory-talk}"
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
    warn "Running as root — memory-talk will install to /root/memory-talk."
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

# ────────── 3. pip install ──────────

step "Upgrading pip inside the venv..."
"$VENV_PY" -m pip install --quiet --disable-pip-version-check --upgrade pip
ok "pip is current"

step "Installing $PACKAGE from PyPI..."
hint "this pulls lancedb / pyarrow / fastapi etc. — first run can take 1–3 min"
"$VENV_PIP" install --disable-pip-version-check --upgrade "$PACKAGE"
ok "install finished"

# ────────── 4. verify ──────────

step "Verifying..."
if ! VERSION="$("$VENV_DIR/bin/memory-talk" --version 2>/dev/null)"; then
    fail "memory-talk installed but --version failed. Run '$VENV_DIR/bin/memory-talk --help' to investigate."
fi
ok "$PACKAGE $VERSION is ready"

# ────────── 5. post-install instructions ──────────

cat <<EOF

${C_BOLD}Installation complete.${C_RESET}

memory-talk entry point:
  ${C_BOLD}$VENV_DIR/bin/memory-talk${C_RESET}

To use it from anywhere, add the venv's bin to your PATH. Pick one:

  ${C_DIM}# Option A: shell rc one-liner (zsh / bash)${C_RESET}
  echo 'export PATH="$VENV_DIR/bin:\$PATH"' >> ~/.zshrc   # or ~/.bashrc

  ${C_DIM}# Option B: symlink into ~/.local/bin (if it's already in PATH)${C_RESET}
  ln -sf "$VENV_DIR/bin/memory-talk" "\$HOME/.local/bin/memory-talk"

Then in a new shell:

  memory-talk setup            ${C_DIM}# interactive first-time configure${C_RESET}
  memory-talk server start
  memory-talk --help

Future upgrades:

  memory-talk upgrade          ${C_DIM}# pulls latest from PyPI into this venv${C_RESET}

EOF
