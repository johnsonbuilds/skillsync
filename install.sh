#!/bin/sh
# SkillSync installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.sh | sh
#
# What it does:
#   1. checks Python >= 3.12
#   2. creates ~/.local/share/skillsync/venv
#   3. pip installs skillsync (from GitHub by default)
#   4. exposes ~/.local/bin/skillsync
#
# Override the source repository with:
#   SKILLSYNC_REPO=/path/to/local/checkout install.sh

set -e

REPO_URL="${SKILLSYNC_REPO:-https://github.com/johnsonbuilds/skillsync.git}"
INSTALL_DIR="$HOME/.local/share/skillsync"
BIN_DIR="$HOME/.local/bin"

echo "Installing SkillSync..."

# 1. Check Python >= 3.12
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found. Install Python 3.12+ first." >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "Error: SkillSync requires Python >= 3.12 (found $(python3 --version 2>&1))." >&2
    exit 1
fi

# 2. Create the venv
python3 -m venv "$INSTALL_DIR/venv"

# 3. Install skillsync into it
#    REPO_URL may be a git URL or a local checkout path.
case "$REPO_URL" in
    *.git | http://* | https://* | git+*) SRC="git+$REPO_URL" ;;
    *) SRC="$REPO_URL" ;;
esac
"$INSTALL_DIR/venv/bin/pip" install --upgrade "$SRC"

# 4. Expose the entry point
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/venv/bin/skillsync" "$BIN_DIR/skillsync"

echo
echo "SkillSync installed."
echo "Run:  skillsync init"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Note: $BIN_DIR is not in your PATH. Add it to use 'skillsync' directly." ;;
esac
