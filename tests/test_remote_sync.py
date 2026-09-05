"""End-to-end tests for remote synchronization (v0.3).

GitHub is simulated with a local bare repository reached over ``file://``,
which exercises the exact same git transport as a real remote without the
network. Covering: remote add (validation, initial backup, rollback on
unrelated histories), status remote lines, pre-sync snapshots, two-machine
round-trips, conflict abort + --use-remote, offline degradation, and clone.
"""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillsync.cli import app
from skillsync.git import log as git_log
from skillsync.git import remote_url

runner = CliRunner()


def invoke(*args: str, input: str | None = None):
    return runner.invoke(app, list(args), input=input)


def make_bare_remote(tmp_path: Path, name: str = "remote.git") -> str:
    """A local bare repository acting as the GitHub remote."""
    path = tmp_path / name
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(path)],
        check=True,
        capture_output=True,
    )
    return f"file://{path}"


def write_skill(skills_dir: Path, name: str, content: str) -> None:
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(content)


class Machine:
    """One machine: isolated Skills dir, config dir, and env."""

    def __init__(self, tmp_path: Path, name: str):
        self.name = name
        self.skills_dir = tmp_path / name / "skills"
        self.skills_dir.mkdir(parents=True)
        config = tmp_path / name / "config"
        config.mkdir(parents=True)
        self._env = {
            "SKILLSYNC_SKILLS_DIR": str(self.skills_dir),
            "XDG_CONFIG_HOME": str(config),
        }

    def use(self, monkeypatch) -> None:
        for key, value in self._env.items():
            monkeypatch.setenv(key, value)


@pytest.fixture
def machine_a(tmp_path):
    return Machine(tmp_path, "machine-a")


@pytest.fixture
def machine_b(tmp_path):
    return Machine(tmp_path, "machine-b")


def setup_skill_dir(machine: Machine) -> None:
    write_skill(machine.skills_dir, "browser-research", "# Browser Research\n")
    write_skill(machine.skills_dir, "github-pr", "# GitHub PR\n")
    result = invoke("init")
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# remote add
# ---------------------------------------------------------------------------


def test_remote_add_rejects_unreachable_url(machine_a, monkeypatch):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    result = invoke("remote", "add", "file:///nonexistent/repo.git")
    assert result.exit_code == 1, result.output
    assert "could not reach" in result.output
    assert remote_url(machine_a.skills_dir) is None


def test_remote_add_initial_push_and_status(machine_a, monkeypatch, tmp_path):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)

    result = invoke("remote", "add", url)
    assert result.exit_code == 0, result.output
    assert "Remote added" in result.output
    assert "Initial backup pushed." in result.output
    assert "PRIVATE" in result.output  # reminder

    # The bare remote now holds the initial snapshot.
    heads = subprocess.run(
        ["git", f"--git-dir={tmp_path / 'remote.git'}", "log", "--oneline", "main"],
        capture_output=True,
        text=True,
    )
    assert heads.returncode == 0, heads.stderr
    assert "SkillSync initial snapshot" in heads.stdout

    result = invoke("status")
    assert result.exit_code == 0, result.output
    assert f"Remote: {url}" in result.output
    assert "Remote state: up to date" in result.output

    result = invoke("sync")
    assert result.exit_code == 0, result.output
    assert "Everything up to date." in result.output


def test_remote_add_rejects_second_remote(machine_a, monkeypatch, tmp_path):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0
    result = invoke("remote", "add", url)
    assert result.exit_code == 1, result.output
    assert "already configured" in result.output


def test_remote_add_rolls_back_on_unrelated_history(
    machine_a, machine_b, monkeypatch, tmp_path
):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)

    # Machine B sets up its own repo and pushes it to another bare remote.
    # A distinct marker file (written BEFORE init, so it lands in B's root
    # snapshot) makes B's root commit differ from A's even within the same
    # second — identical trees would hash to the identical commit.
    machine_b.use(monkeypatch)
    (machine_b.skills_dir / "machine-b-marker.txt").write_text("different history\n")
    setup_skill_dir(machine_b)
    other = make_bare_remote(tmp_path, "other.git")
    assert invoke("remote", "add", other).exit_code == 0
    assert remote_url(machine_b.skills_dir) == other

    # Machine A tries to point at that same remote: unrelated histories.
    machine_a.use(monkeypatch)
    result = invoke("remote", "add", other)
    assert result.exit_code == 1, result.output
    assert "different history" in result.output
    # Rolled back: no remote left behind.
    assert remote_url(machine_a.skills_dir) is None


def test_remote_remove(machine_a, monkeypatch, tmp_path):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0

    result = invoke("remote", "remove")
    assert result.exit_code == 0, result.output
    assert "not touched" in result.output
    assert remote_url(machine_a.skills_dir) is None

    result = invoke("sync")
    assert result.exit_code == 1, result.output
    assert "no remote" in result.output


def test_remote_show_without_subcommand(machine_a, monkeypatch, tmp_path):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)

    result = invoke("remote")
    assert result.exit_code == 0, result.output
    assert "No remote configured." in result.output

    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0
    result = invoke("remote")
    assert result.exit_code == 0, result.output
    assert f"Remote: {url}" in result.output


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


def test_sync_pre_snapshots_and_pushes(machine_a, monkeypatch, tmp_path):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0

    write_skill(machine_a.skills_dir, "browser-research", "# Changed on A\n")
    result = invoke("sync")
    assert result.exit_code == 0, result.output
    assert "Pre-sync snapshot created:" in result.output
    assert "Pushed 1 snapshot" in result.output

    result = invoke("status")
    assert "Remote state: up to date" in result.output

    # The pre-sync snapshot landed on the remote too.
    heads = subprocess.run(
        ["git", f"--git-dir={tmp_path / 'remote.git'}", "log", "--format=%s", "main"],
        capture_output=True,
        text=True,
    )
    assert any("Pre-sync snapshot" in line for line in heads.stdout.splitlines())


def test_sync_two_machine_roundtrip(
    machine_a, machine_b, monkeypatch, tmp_path
):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0

    # Machine B clones and pushes a change to one skill.
    machine_b.use(monkeypatch)
    target = tmp_path / "machine-b" / "skills"
    result = invoke("clone", url, str(target))
    assert result.exit_code == 0, result.output
    assert "Found 2 skills." in result.output
    (target / "github-pr" / "SKILL.md").write_text("# Changed on B\n")
    result = invoke("sync")
    assert result.exit_code == 0, result.output
    assert "Pushed 1 snapshot" in result.output

    # Machine A changed a *different* skill: rebase replays cleanly.
    machine_a.use(monkeypatch)
    write_skill(machine_a.skills_dir, "browser-research", "# Changed on A\n")
    result = invoke("sync")
    assert result.exit_code == 0, result.output
    assert "Pulled 1" in result.output
    assert "pushed 1" in result.output

    content = (machine_a.skills_dir / "github-pr" / "SKILL.md").read_text()
    assert content == "# Changed on B\n"

    result = invoke("status")
    assert "Remote state: up to date" in result.output


def test_sync_conflict_abort_then_use_remote(
    machine_a, machine_b, monkeypatch, tmp_path
):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0

    machine_b.use(monkeypatch)
    target = tmp_path / "machine-b" / "skills"
    assert invoke("clone", url, str(target)).exit_code == 0
    (target / "github-pr" / "SKILL.md").write_text("# Version B\n")
    assert invoke("sync").exit_code == 0

    # Machine A changed the SAME skill: conflict.
    machine_a.use(monkeypatch)
    (machine_a.skills_dir / "github-pr" / "SKILL.md").write_text("# Version A\n")
    result = invoke("sync")
    assert result.exit_code == 1, result.output
    assert "conflicting skill: github-pr" in result.output
    assert "Sync aborted" in result.output
    assert "skillsync sync --use-remote" in result.output

    # Nothing changed locally: A's version is intact and in sync's history.
    content = (machine_a.skills_dir / "github-pr" / "SKILL.md").read_text()
    assert content == "# Version A\n"
    local_log = git_log(machine_a.skills_dir)
    assert "Version A" not in local_log[-1].subject  # HEAD untouched by sync

    result = invoke("status")
    assert result.exit_code == 0, result.output
    assert "diverged" in result.output

    # Adopting the remote replaces A's content with B's.
    result = invoke("sync", "--use-remote")
    assert result.exit_code == 0, result.output
    assert "Adopted the remote version." in result.output
    assert "recoverable via `git reflog`" in result.output
    content = (machine_a.skills_dir / "github-pr" / "SKILL.md").read_text()
    assert content == "# Version B\n"

    result = invoke("status")
    assert "Remote state: up to date" in result.output


def test_sync_offline_leaves_local_state_alone(
    machine_a, monkeypatch, tmp_path
):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0

    # The remote disappears (like GitHub being unreachable).
    subprocess.run(["rm", "-rf", str(tmp_path / "remote.git")], check=True)

    write_skill(machine_a.skills_dir, "browser-research", "# Offline work\n")
    result = invoke("sync")
    assert result.exit_code == 1, result.output
    assert "could not reach the remote" in result.output
    assert "Local snapshots are safe." in result.output

    # The pre-sync snapshot was still taken locally before the failed fetch.
    result = invoke("status")
    assert result.exit_code == 0, result.output
    assert "No changes." in result.output
    assert "unknown (offline)" in result.output


def test_clone_rejects_non_empty_target(
    machine_a, machine_b, monkeypatch, tmp_path
):
    machine_a.use(monkeypatch)
    setup_skill_dir(machine_a)
    url = make_bare_remote(tmp_path)
    assert invoke("remote", "add", url).exit_code == 0

    machine_b.use(monkeypatch)
    occupied = tmp_path / "machine-b" / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("precious\n")
    result = invoke("clone", url, str(occupied))
    assert result.exit_code == 1, result.output
    assert "not empty" in result.output
    assert (occupied / "keep.txt").read_text() == "precious\n"
