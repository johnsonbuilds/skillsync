"""Agent adapters.

Each supported Agent harness contributes only one thing: the candidates for
its Skills directory, in priority order. The core of SkillSync never needs
to know which harness is in use — the resolved directory is all that
matters.

Adding a harness means adding one ``AgentSpec`` entry to ``get_specs``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Agent:
    key: str
    name: str
    skills_dir: Path


@dataclass(frozen=True)
class AgentSpec:
    """Skills-directory candidates for one harness, in priority order."""

    key: str
    name: str
    env_var: str | None = None          # harness-home override, e.g. HERMES_HOME
    home_subdir: str | None = None      # directory under $HOME, e.g. ".hermes"
    extra_dirs: tuple[Path, ...] = ()   # absolute fallbacks, lowest priority

    def candidate_dirs(self) -> list[Path]:
        candidates: list[Path] = []
        if self.env_var:
            value = os.environ.get(self.env_var)
            if value:
                candidates.append(Path(value).expanduser() / "skills")
        if self.home_subdir:
            candidates.append(Path.home() / self.home_subdir / "skills")
        candidates.extend(self.extra_dirs)
        return candidates


# Well-known Hermes locations, tried after $HERMES_HOME/skills and
# ~/.hermes/skills.
HERMES_FALLBACK_DIRS: tuple[Path, ...] = (
    Path("/opt/.hermes/skills"),
    Path("/opt/data/.hermes/skills"),
    Path("/usr/local/.hermes/skills"),
)

# System-wide Codex Skills (read-only for most users; detection only).
CODEX_SYSTEM_DIRS: tuple[Path, ...] = (
    Path("/etc/codex/skills"),
)

AGENT_KEYS = ("hermes", "openclaw", "claude", "codex")
AGENT_KEYS_HELP = ", ".join(AGENT_KEYS)

# Directory names recognized by the bounded hint search.
SEARCH_DIR_NAMES = ("skills", "optional-skills")


def get_specs() -> tuple[AgentSpec, ...]:
    """Harness specs, built fresh so tests can monkeypatch module globals."""
    return (
        AgentSpec(
            key="hermes",
            name="Hermes",
            env_var="HERMES_HOME",
            home_subdir=".hermes",
            extra_dirs=HERMES_FALLBACK_DIRS,
        ),
        AgentSpec(
            key="openclaw",
            name="OpenClaw",
            env_var="OPENCLAW_STATE_DIR",
            home_subdir=".openclaw",
        ),
        AgentSpec(key="claude", name="Claude Code", home_subdir=".claude"),
        AgentSpec(
            key="codex",
            name="Codex",
            home_subdir=".codex",
            extra_dirs=CODEX_SYSTEM_DIRS,
        ),
    )


def find_agents() -> list[Agent]:
    """Every harness with an existing Skills directory, in spec order.

    Each harness contributes at most one directory (its first existing
    candidate); identical paths are deduplicated. Detection never guesses:
    when several harnesses are found, ``init`` lists them and asks the user
    to pick one.
    """
    agents: list[Agent] = []
    seen: set[str] = set()
    for spec in get_specs():
        for candidate in spec.candidate_dirs():
            if str(candidate) in seen:
                break
            if candidate.is_dir():
                seen.add(str(candidate))
                agents.append(
                    Agent(key=spec.key, name=spec.name, skills_dir=candidate)
                )
                break
    return agents


def find_agent(agent_key: str) -> Agent | None:
    """The first existing Skills directory for one specific harness."""
    for spec in get_specs():
        if spec.key != agent_key:
            continue
        for candidate in spec.candidate_dirs():
            if candidate.is_dir():
                return Agent(key=spec.key, name=spec.name, skills_dir=candidate)
    return None


def label_agent(skills_dir: Path) -> Agent:
    """An Agent for ``skills_dir``: its harness when recognized, else Custom."""
    for spec in get_specs():
        if skills_dir in spec.candidate_dirs():
            return Agent(key=spec.key, name=spec.name, skills_dir=skills_dir)
    return Agent(key="custom", name="Custom", skills_dir=skills_dir)


def detect_agent() -> Agent | None:
    """The single harness found on this machine.

    Returns None when none exists or when several do — ambiguity is always
    resolved explicitly by the user (``init`` lists the candidates).
    """
    agents = find_agents()
    if len(agents) == 1:
        return agents[0]
    return None


# Roots (with depth limits) for the bounded hint search that only runs when
# every well-known location failed.
SEARCH_ROOTS: tuple[tuple[Path, int], ...] = (
    (Path("/opt"), 3),
    (Path("/usr/local"), 3),
)
SEARCH_HOME_DEPTH = 4
SEARCH_MAX_RESULTS = 5

# Directory names recognized by the hint search.
SEARCH_DIR_NAMES = ("skills", "optional-skills")

# Directories never descended into during the hint search.
SEARCH_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".cache", ".cargo", ".rustup",
    ".npm", ".nvm", "site-packages", "dist-packages", "Library",
}


def _looks_like_skills_dir(path: Path) -> bool:
    """A plausible Skills directory holds at least one non-hidden subdirectory."""
    try:
        return any(
            p.is_dir() and not p.name.startswith(".") for p in path.iterdir()
        )
    except OSError:
        return False


def search_skill_dirs(max_results: int = SEARCH_MAX_RESULTS) -> list[Path]:
    """Bounded, read-only search for plausible Skills directories.

    This is only a hint for the user: SkillSync never picks a searched
    directory automatically. The search is depth-limited and skips hidden
    and dependency directories, so it stays fast.
    """
    roots: list[tuple[Path, int]] = [(Path.home(), SEARCH_HOME_DEPTH)]
    roots.extend(SEARCH_ROOTS)
    hits: dict[str, Path] = {}
    for root, max_depth in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, _filenames in os.walk(root, onerror=None):
            try:
                depth = len(Path(dirpath).relative_to(root).parts)
            except ValueError:
                continue
            if depth >= max_depth:
                dirnames[:] = []
                continue
            for name in dirnames:
                if name not in SEARCH_DIR_NAMES:
                    continue
                candidate = Path(dirpath) / name
                if _looks_like_skills_dir(candidate):
                    hits[str(candidate)] = candidate
                    if len(hits) >= max_results:
                        return sorted(hits.values(), key=str)
            dirnames[:] = [
                d for d in dirnames
                if d not in SEARCH_SKIP_DIRS and not d.startswith(".")
            ]
    return sorted(hits.values(), key=str)


def config_file() -> Path:
    """Persisted resolution (agent key + Skills dir) from the last init."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "skillsync" / "config.json"


def save_skills_dir(agent_key: str, skills_dir: Path) -> None:
    """Remember the resolution so later commands skip detection."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            data = {}
    data["agent"] = agent_key
    data["skills_dir"] = str(skills_dir)
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_skills_dir() -> Path | None:
    """Resolve the Skills directory: env var > config file > auto-detect.

    Auto-detect yields a result only when exactly one harness is found;
    ambiguity stays None so the caller can surface the candidates.
    """
    env = os.environ.get("SKILLSYNC_SKILLS_DIR")
    if env:
        return Path(env).expanduser()
    path = config_file()
    if path.exists():
        try:
            saved = json.loads(path.read_text()).get("skills_dir")
            if saved:
                return Path(saved).expanduser()
        except (OSError, json.JSONDecodeError):
            pass
    agent = detect_agent()
    return agent.skills_dir if agent else None
