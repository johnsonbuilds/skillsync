"""Tests for the Agent adapters: Skills-directory discovery and selection."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillsync import agent
from skillsync.agent import (
    AgentSpec,
    detect_agent,
    find_agent,
    find_agents,
    get_specs,
    label_agent,
    search_skill_dirs,
)
from skillsync.cli import app

runner = CliRunner()


def make_skills(base: Path) -> Path:
    """Create ``base/skills/demo`` with a SKILL.md; return the skills dir."""
    skills = base / "skills"
    (skills / "demo").mkdir(parents=True)
    (skills / "demo" / "SKILL.md").write_text("# Demo\n")
    return skills


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Keep discovery isolated from the real machine."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in (
        "HERMES_HOME",
        "OPENCLAW_STATE_DIR",
        "SKILLSYNC_SKILLS_DIR",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(agent, "HERMES_FALLBACK_DIRS", ())
    monkeypatch.setattr(agent, "CODEX_SYSTEM_DIRS", ())


# ---------------------------------------------------------------------------
# candidate chains
# ---------------------------------------------------------------------------


def test_hermes_candidate_order(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.setattr(agent, "HERMES_FALLBACK_DIRS", (Path("/opt/.hermes/skills"),))
    spec = next(s for s in get_specs() if s.key == "hermes")
    assert spec.candidate_dirs() == [
        tmp_path / "hermes-home" / "skills",
        Path.home() / ".hermes" / "skills",
        Path("/opt/.hermes/skills"),
    ]


def test_hermes_candidates_without_env_var(monkeypatch):
    monkeypatch.setattr(agent, "HERMES_FALLBACK_DIRS", ())
    spec = next(s for s in get_specs() if s.key == "hermes")
    assert spec.candidate_dirs() == [Path.home() / ".hermes" / "skills"]


def test_openclaw_state_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(tmp_path / "state"))
    spec = next(s for s in get_specs() if s.key == "openclaw")
    assert spec.candidate_dirs() == [
        tmp_path / "state" / "skills",
        Path.home() / ".openclaw" / "skills",
    ]


def test_openclaw_candidates_default():
    spec = next(s for s in get_specs() if s.key == "openclaw")
    assert spec.candidate_dirs() == [Path.home() / ".openclaw" / "skills"]


def test_codex_includes_system_dir():
    spec = AgentSpec(
        key="codex",
        name="Codex",
        home_subdir=".codex",
        extra_dirs=(Path("/etc/codex/skills"),),
    )
    assert spec.candidate_dirs() == [
        Path.home() / ".codex" / "skills",
        Path("/etc/codex/skills"),
    ]


def test_claude_candidates():
    spec = next(s for s in get_specs() if s.key == "claude")
    assert spec.candidate_dirs() == [Path.home() / ".claude" / "skills"]


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------


def test_find_agents_only_existing_dirs():
    make_skills(Path.home() / ".hermes")
    make_skills(Path.home() / ".claude")
    agents = find_agents()
    assert [a.key for a in agents] == ["hermes", "claude"]


def test_find_agents_skips_harnesses_without_skills_dir():
    (Path.home() / ".claude").mkdir()  # exists, but no skills/ inside
    assert find_agents() == []


def test_find_agents_dedupes_identical_dirs(monkeypatch):
    base = Path.home() / "shared-base"
    shared = make_skills(base)
    monkeypatch.setenv("ALPHA_HOME", str(base))
    specs = (
        AgentSpec("alpha", "Alpha", env_var="ALPHA_HOME"),
        AgentSpec("beta", "Beta", home_subdir="shared-base"),
    )
    monkeypatch.setattr(agent, "get_specs", lambda: specs)
    agents = find_agents()
    # beta resolves to the same directory as alpha and must not be listed.
    assert [a.key for a in agents] == ["alpha"]
    assert str(agents[0].skills_dir) == str(shared)


def test_detect_agent_single_harness():
    make_skills(Path.home() / ".hermes")
    detected = detect_agent()
    assert detected is not None
    assert detected.key == "hermes"
    assert detected.name == "Hermes"


def test_detect_agent_ambiguous_returns_none():
    make_skills(Path.home() / ".hermes")
    make_skills(Path.home() / ".claude")
    assert detect_agent() is None
    assert [a.key for a in find_agents()] == ["hermes", "claude"]


def test_find_agent_specific_key():
    make_skills(Path.home() / ".claude")
    found = find_agent("claude")
    assert found is not None
    assert found.key == "claude"
    assert find_agent("hermes") is None


def test_label_agent_recognizes_harness(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "h"))
    skills = tmp_path / "h" / "skills"
    skills.mkdir(parents=True)
    assert label_agent(skills).key == "hermes"
    other = tmp_path / "elsewhere" / "skills"
    other.mkdir(parents=True)
    assert label_agent(other).key == "custom"


# ---------------------------------------------------------------------------
# bounded hint search
# ---------------------------------------------------------------------------


def test_search_finds_skills_dir_under_home():
    skills = make_skills(Path.home() / "work" / "hermes-agent")
    assert search_skill_dirs() == [skills]


def test_search_finds_optional_skills_dir():
    base = Path.home() / "work" / "hermes-agent" / "optional-skills"
    (base / "yuanbao").mkdir(parents=True)
    assert search_skill_dirs() == [base]


def test_search_ignores_dirs_with_only_hidden_children():
    d = Path.home() / "proj" / "skills"
    (d / ".hidden").mkdir(parents=True)
    assert search_skill_dirs() == []


def test_search_respects_depth_limit():
    at_limit = Path.home() / "a" / "b" / "c" / "skills"  # depth 4 == limit
    (at_limit / "demo").mkdir(parents=True)
    beyond = Path.home() / "a" / "b" / "c" / "d" / "skills"  # depth 5
    (beyond / "demo").mkdir(parents=True)
    assert search_skill_dirs() == [at_limit]


def test_search_skips_dependency_dirs():
    (Path.home() / "proj" / ".venv" / "skills" / "demo").mkdir(parents=True)
    (Path.home() / "proj" / "node_modules" / "pkg" / "skills" / "demo").mkdir(
        parents=True
    )
    assert search_skill_dirs() == []


# ---------------------------------------------------------------------------
# init: harness selection
# ---------------------------------------------------------------------------


def test_init_single_harness_auto_selected():
    make_skills(Path.home() / ".hermes")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "Hermes Skills:" in result.output
    assert "Found 1 skill." in result.output


def test_init_lists_candidates_when_ambiguous():
    make_skills(Path.home() / ".hermes")
    make_skills(Path.home() / ".claude")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert "several Agent Skills directories" in result.output
    assert "hermes" in result.output
    assert "claude" in result.output
    assert "--agent" in result.output


def test_init_agent_flag_picks_harness():
    make_skills(Path.home() / ".hermes")
    make_skills(Path.home() / ".claude")
    result = runner.invoke(app, ["init", "--agent", "claude"])
    assert result.exit_code == 0, result.output
    assert "Claude Code Skills:" in result.output


def test_init_agent_flag_unknown_agent():
    result = runner.invoke(app, ["init", "--agent", "nope"])
    assert result.exit_code == 1
    assert "unknown agent" in result.output
    assert "hermes, openclaw, claude, codex" in result.output


def test_init_agent_flag_without_skills_dir():
    result = runner.invoke(app, ["init", "--agent", "codex"])
    assert result.exit_code == 1
    assert "no Skills directory found for agent: codex" in result.output


def test_init_env_var_resolves_ambiguity(monkeypatch):
    make_skills(Path.home() / ".hermes")
    claude = make_skills(Path.home() / ".claude")
    monkeypatch.setenv("SKILLSYNC_SKILLS_DIR", str(claude))
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert "Claude Code Skills:" in result.output


def test_init_lists_search_hints_when_nothing_detected():
    skills = make_skills(Path.home() / "work" / "hermes-agent")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert str(skills) in result.output
    assert "--path" in result.output
