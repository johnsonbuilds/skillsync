"""Tests for install.sh shell detection and the tailored PATH hint.

install.sh stays POSIX sh; these tests drive it through ``sh -c`` /
``bash -c`` subprocesses and assert on the generated text.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

INSTALL = pathlib.Path(__file__).resolve().parents[1] / "install.sh"

BASH_EXPORT = 'export PATH="$HOME/.local/bin:$PATH"'


def run_sh(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/home/test",
        # source install.sh without running the installer
        "SKILLSYNC_INSTALL_TEST": "1",
    }
    if env:
        base.update(env)
    return subprocess.run(
        ["sh", "-c", script], env=base, capture_output=True, text=True, timeout=60
    )


def source_install() -> str:
    return f'. "{INSTALL}"'


def make_test_env() -> dict[str, str]:
    """Env for direct subprocesses: never let install.sh run its main flow."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/home/test",
        "SKILLSYNC_INSTALL_TEST": "1",
    }


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------


def test_install_sh_syntax():
    result = subprocess.run(
        ["sh", "-n", str(INSTALL)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_sourced_with_test_flag_does_not_install():
    result = run_sh(f"{source_install()}; echo REACHED")
    assert result.returncode == 0, result.stderr
    assert "Installing SkillSync" not in result.stdout
    assert "REACHED" in result.stdout


# ---------------------------------------------------------------------------
# skillsync_detect_shell
# ---------------------------------------------------------------------------


def test_detect_shell_explicit_override_wins():
    result = run_sh(
        f"{source_install()}; skillsync_detect_shell",
        env={"SKILLSYNC_SHELL": "fish", "SHELL": "/bin/bash"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "fish"


def test_detect_shell_rejects_bad_override():
    result = run_sh(
        f"{source_install()}; skillsync_detect_shell",
        env={"SKILLSYNC_SHELL": "tcsh", "SHELL": "/bin/zsh"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "zsh"


def test_detect_shell_when_sourced_from_bash():
    # `. install.sh` from bash: $$ IS bash (detection step 2).
    result = subprocess.run(
        ["bash", "-c", f'{source_install()}; skillsync_detect_shell'],
        env=make_test_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "bash"


def test_detect_shell_via_parent_process():
    # Mirrors `curl ... | sh`: pipeline members are forked children, so the
    # inner sh's parent is a real bash process. (The trailing `; :` keeps
    # bash from exec-optimizing the pipeline away.)
    inner = f"{source_install()}; skillsync_detect_shell"
    result = subprocess.run(
        ["bash", "-c", f'sh -c "{inner}" | cat; :'],
        env=make_test_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "bash"


def test_detect_shell_falls_back_to_shell_env():
    # Parent of this sh is pytest (not a shell) -> $SHELL decides.
    result = run_sh(
        f"{source_install()}; skillsync_detect_shell",
        env={"SHELL": "/usr/bin/zsh"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "zsh"


def test_detect_shell_unknown_without_signals():
    result = run_sh(f"{source_install()}; skillsync_detect_shell", env={"SHELL": ""})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unknown"


# ---------------------------------------------------------------------------
# skillsync_print_path_hint
# ---------------------------------------------------------------------------


def test_hint_bash_linux():
    result = run_sh(f"{source_install()}; skillsync_print_path_hint bash")
    out = result.stdout
    assert result.returncode == 0, result.stderr
    assert "not on your PATH" in out
    assert f"echo '{BASH_EXPORT}' >> ~/.bashrc && source ~/.bashrc" in out
    assert "new terminals read ~/.bashrc automatically" in out


def test_hint_bash_macos_uses_bash_profile():
    # Simulate Darwin by stubbing uname in PATH (sh cannot monkeypatch).
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        stub_bin = pathlib.Path(tmp) / "bin"
        stub_bin.mkdir()
        (stub_bin / "uname").write_text("#!/bin/sh\necho Darwin\n")
        (stub_bin / "uname").chmod(0o755)
        env = {"PATH": f"{stub_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}"}
        result = run_sh(f"{source_install()}; skillsync_print_path_hint bash", env=env)
    out = result.stdout
    assert result.returncode == 0, result.stderr
    assert ">> ~/.bash_profile && source ~/.bash_profile" in out
    assert ".bashrc" not in out


def test_hint_zsh():
    result = run_sh(f"{source_install()}; skillsync_print_path_hint zsh")
    out = result.stdout
    assert result.returncode == 0, result.stderr
    assert f"echo '{BASH_EXPORT}' >> ~/.zshrc && source ~/.zshrc" in out


def test_hint_fish_no_source():
    result = run_sh(f"{source_install()}; skillsync_print_path_hint fish")
    out = result.stdout
    assert result.returncode == 0, result.stderr
    assert "fish_add_path /home/test/.local/bin" in out
    assert "no source needed" in out
    assert "source" not in out.replace("no source needed", "")


def test_hint_pwsh():
    result = run_sh(f"{source_install()}; skillsync_print_path_hint pwsh")
    out = result.stdout
    assert result.returncode == 0, result.stderr
    assert "Add-Content -Path $PROFILE" in out
    assert '$env:Path = "$HOME/.local/bin:" + $env:Path' in out
    assert ". $PROFILE" in out


def test_hint_unknown_lists_all_shells():
    result = run_sh(f"{source_install()}; skillsync_print_path_hint unknown")
    out = result.stdout
    assert result.returncode == 0, result.stderr
    assert "Could not detect your shell" in out
    assert ">> ~/.bashrc && source ~/.bashrc" in out
    assert ">> ~/.zshrc && source ~/.zshrc" in out
    assert "fish_add_path" in out
    assert "SKILLSYNC_SHELL" in out
