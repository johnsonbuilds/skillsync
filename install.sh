#!/bin/sh
# SkillSync installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.sh | sh
#
# What it does:
#   1. checks Python >= 3.12
#   2. creates ~/.local/share/skillsync/venv (auto-installs python3-venv on
#      Debian/Ubuntu via apt when ensurepip is missing; set
#      SKILLSYNC_NO_AUTOINSTALL=1 to always handle it by hand)
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

# 2. Create the venv.
#    Debian/Ubuntu split ensurepip out into python3-venv; if venv creation
#    fails, install that package automatically (root directly, else via
#    sudo), then retry once before giving up with manual instructions.
create_venv() {
    rm -rf "$INSTALL_DIR/venv"
    python3 -m venv "$INSTALL_DIR/venv"
}

venv_manual_hint() {
    echo
    echo "Error: could not create the virtual environment (ensurepip missing)." >&2
    echo "Install the venv package for your Python and re-run this installer:" >&2
    echo "    sudo apt install python3-venv" >&2
    exit 1
}

try_apt_install() {
    if [ "$(id -u)" -eq 0 ]; then
        APT="env DEBIAN_FRONTEND=noninteractive apt-get"
    elif command -v sudo >/dev/null 2>&1; then
        APT="sudo env DEBIAN_FRONTEND=noninteractive apt-get"
    else
        echo "Error: python3-venv is missing and no sudo is available to install it." >&2
        return 1
    fi
    echo "Attempting: $APT install $*" >&2
    $APT install -y "$@" || {
        echo "apt-get install failed; running 'apt-get update' and retrying once..." >&2
        $APT update -qq || return 1
        $APT install -y "$@"
    }
}

if ! create_venv; then
    if [ "${SKILLSYNC_NO_AUTOINSTALL:-0}" = "1" ] || ! command -v apt-get >/dev/null 2>&1; then
        venv_manual_hint
    fi
    if try_apt_install python3-venv && create_venv; then
        :
    elif try_apt_install "$(python3 -c 'import sys; print("python%d.%d-venv" % (sys.version_info.major, sys.version_info.minor))')" && create_venv; then
        :
    else
        venv_manual_hint
    fi
fi

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
