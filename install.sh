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
#   5. when ~/.local/bin is missing from PATH, prints a copy-paste
#      command tailored to the detected shell (bash/zsh/fish/pwsh)
#
# Override the source repository with:
#   SKILLSYNC_REPO=/path/to/local/checkout install.sh
# Force the shell used for the PATH hint with:
#   SKILLSYNC_SHELL=bash|zsh|fish|pwsh install.sh

REPO_URL="${SKILLSYNC_REPO:-https://github.com/johnsonbuilds/skillsync.git}"
INSTALL_DIR="$HOME/.local/share/skillsync"
BIN_DIR="$HOME/.local/bin"

# ---------------------------------------------------------------------------
# Shell detection + PATH hint
#
# Detection order (first match wins):
#   1. $SKILLSYNC_SHELL             explicit override
#   2. process name of $$           covers `. ./install.sh` and `curl | bash`
#   3. process name of the parent   covers `curl ... | sh`, `sh install.sh`
#   4. $SHELL                       login default; may differ from the
#                                   current shell, so it is only a fallback
#   5. unknown                      generic multi-shell hint
# ---------------------------------------------------------------------------

skillsync_detect_shell() {
    _ps_pname="" _ps_ppid=""
    case "${SKILLSYNC_SHELL:-}" in
        bash|zsh|fish|pwsh) printf '%s\n' "$SKILLSYNC_SHELL"; return 0 ;;
    esac
    if command -v ps >/dev/null 2>&1; then
        # This process itself: a real shell when the script is sourced,
        # plain "sh"/"dash" when executed.
        _ps_pname=$(ps -o comm= -p "$$" 2>/dev/null || true)
        case "${_ps_pname##*/}" in
            bash|-bash) printf 'bash\n'; return 0 ;;
            zsh|-zsh)   printf 'zsh\n';  return 0 ;;
            fish)       printf 'fish\n'; return 0 ;;
            pwsh)       printf 'pwsh\n'; return 0 ;;
        esac
        # The parent process: the interactive shell for pipe/exec runs.
        _ps_ppid=$(ps -o ppid= -p "$$" 2>/dev/null | tr -d ' ' || true)
        if [ -n "$_ps_ppid" ]; then
            _ps_pname=$(ps -o comm= -p "$_ps_ppid" 2>/dev/null || true)
            case "${_ps_pname##*/}" in
                bash|-bash) printf 'bash\n'; return 0 ;;
                zsh|-zsh)   printf 'zsh\n';  return 0 ;;
                fish)       printf 'fish\n'; return 0 ;;
                pwsh)       printf 'pwsh\n'; return 0 ;;
            esac
        fi
    fi
    case "${SHELL:-}" in
        */bash)              echo bash; return 0 ;;
        */zsh)               echo zsh;  return 0 ;;
        */fish)              echo fish; return 0 ;;
        */pwsh|*/powershell) echo pwsh; return 0 ;;
    esac
    echo unknown
}

skillsync_print_path_hint() {
    # $1 = shell name as produced by skillsync_detect_shell
    _hint_shell="$1"
    echo
    echo "Note: $BIN_DIR is not on your PATH."
    case "$_hint_shell" in
        bash)
            # macOS starts login shells that read .bash_profile, not .bashrc.
            if [ "$(uname -s 2>/dev/null)" = "Darwin" ]; then
                _hint_rc="~/.bash_profile"
            else
                _hint_rc="~/.bashrc"
            fi
            echo
            echo "Detected shell: bash. Paste this to enable 'skillsync' now and in future terminals:"
            echo
            echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> $_hint_rc && source $_hint_rc"
            echo
            echo "(source applies it to this terminal; new terminals read $_hint_rc automatically)"
            ;;
        zsh)
            echo
            echo "Detected shell: zsh. Paste this to enable 'skillsync' now and in future terminals:"
            echo
            echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
            echo
            echo "(source applies it to this terminal; new terminals read ~/.zshrc automatically)"
            ;;
        fish)
            echo
            echo "Detected shell: fish. Paste this (fish >= 3.2):"
            echo
            echo "  fish_add_path $BIN_DIR"
            echo
            echo "(fish_add_path persists across sessions and applies to the current one — no source needed)"
            ;;
        pwsh)
            echo
            echo "Detected shell: pwsh. Paste this:"
            echo
            echo "  if (!(Test-Path \$PROFILE)) { New-Item -Type File -Path \$PROFILE -Force | Out-Null }"
            echo "  Add-Content -Path \$PROFILE -Value '\$env:Path = \"\$HOME/.local/bin:\" + \$env:Path'"
            echo "  . \$PROFILE"
            ;;
        *)
            echo
            echo "Could not detect your shell — add $BIN_DIR to your PATH manually:"
            echo
            echo "  bash:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
            echo "  zsh:   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
            echo "  fish:  fish_add_path $BIN_DIR"
            echo
            echo "(or re-run with: SKILLSYNC_SHELL=bash|zsh|fish|pwsh sh install.sh)"
            ;;
    esac
}

skillsync_main() {
    set -e

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
        *) skillsync_print_path_hint "$(skillsync_detect_shell)" ;;
    esac
}

# SKILLSYNC_INSTALL_TEST=1 sources the helper functions without running
# the installer (used by tests/test_install_sh.py).
if [ "${SKILLSYNC_INSTALL_TEST:-}" != "1" ]; then
    skillsync_main
fi
