"""Tests for the Agent adapter: Skills-directory discovery."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillsync import agent
from skillsync.agent import (
    detect_agent,
    hermes_candidate_dirs,
    hermes_skills_dir,
    search_skill_dirs,
)
from skillsync.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Keep discovery isolated from the real machine."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("SKILLSYNC_SKILLS_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(agent, "HERMES_FALLBACK_DIRS", ())
    monkeypatch.setattr(agent, "SEARCH_ROOTS", ())
    return home


def make_skills(parent: Path) -> Path:
    """Create parent/skills/browser-research and return parent/skills."""
    skills = parent / "skills"
    (skills / "browser-research").mkdir(parents=True)
    return skills


def test_candidate_chain_order(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", "/hermes-home")
    monkeypatch.setattr(
        agent,
        "HERMES_FALLBACK_DIRS",
        (Path("/opt/.hermes/skills"), Path("/opt/data/.hermes/skills")),
    )
    assert hermes_candidate_dirs() == [
        Path("/hermes-home/skills"),
        Path.home() / ".hermes" / "skills",
        Path("/opt/.hermes/skills"),
        Path("/opt/data/.hermes/skills"),
    ]


def test_hermes_home_wins_over_home_dir(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes-home"
    make_skills(hermes_home)
    make_skills(Path.home() / ".hermes")  # exists too, but lower priority
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    assert hermes_skills_dir() == hermes_home / "skills"


def test_falls_back_to_home_hermes_when_hermes_home_missing(tmp_path, monkeypatch):
    expected = make_skills(Path.home() / ".hermes")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "missing"))
    assert hermes_skills_dir() == expected


def test_falls_through_fallback_dirs_in_order(tmp_path, monkeypatch):
    second = tmp_path / "optdata" / ".hermes" / "skills"
    second.mkdir(parents=True)
    missing_first = tmp_path / "opt" / ".hermes" / "skills"
    third = tmp_path / "usrlocal" / ".hermes" / "skills"
    third.mkdir(parents=True)
    monkeypatch.setattr(
        agent, "HERMES_FALLBACK_DIRS", (missing_first, second, third)
    )
    assert hermes_skills_dir() == second


def test_detect_agent_none_when_nothing_exists():
    assert hermes_skills_dir() is None
    assert detect_agent() is None


def test_detect_agent_reports_hermes():
    skills = make_skills(Path.home() / ".hermes")
    found = detect_agent()
    assert found is not None
    assert found.key == "hermes"
    assert found.skills_dir == skills


def test_search_finds_skills_dir_under_home():
    skills = make_skills(Path.home() / "work" / "hermes-agent")
    assert search_skill_dirs() == [skills]


def test_search_ignores_implausible_skills_dirs():
    empty = Path.home() / "somewhere" / "skills"
    empty.mkdir(parents=True)  # no subdirectories
    hidden_only = Path.home() / "elsewhere" / "skills" / ".hidden"
    hidden_only.mkdir(parents=True)  # only hidden children
    assert search_skill_dirs() == []


def test_search_respects_depth_limit():
    at_limit = Path.home() / "a" / "b" / "c" / "skills"  # depth 4 == limit
    make_skills(at_limit)
    beyond = Path.home() / "a" / "b" / "c" / "d" / "skills"  # depth 5
    make_skills(beyond)
    assert search_skill_dirs() == [at_limit]


def test_search_skips_dependency_dirs():
    make_skills(Path.home() / "proj" / ".venv" / "skills")
    make_skills(Path.home() / "proj" / "node_modules" / "pkg" / "skills")
    assert search_skill_dirs() == []


def test_init_lists_search_hints_when_nothing_detected():
    skills = make_skills(Path.home() / "work" / "hermes-agent")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert str(skills) in result.output
    assert "--path" in result.output
