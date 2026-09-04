"""Agent adapters.

Each supported Agent only contributes one thing: how to locate its Skills
directory. Adding a new Agent (e.g. OpenClaw) should only require extending
this module.
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


# Well-known Hermes locations, tried in priority order after the explicit
# ones ($HERMES_HOME/skills, ~/.hermes/skills).
HERMES_FALLBACK_DIRS: tuple[Path, ...] = (
    Path("/opt/.hermes/skills"),
    Path("/opt/data/.hermes/skills"),
    Path("/usr/local/.hermes/skills"),
)

# Roots (with depth limits) for the bounded hint search that only runs when
# every well-known location failed.
SEARCH_ROOTS: tuple[tuple[Path, int], ...] = (
    (Path("/opt"), 3),
    (Path("/usr/local"), 3),
)
SEARCH_HOME_DEPTH = 4
SEARCH_MAX_RESULTS = 5

# Directories never descended into during the hint search.
SEARCH_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".cache", ".cargo", ".rustup",
    ".npm", ".nvm", "site-packages", "dist-packages", "Library",
}


def hermes_candidate_dirs() -> list[Path]:
    """Hermes Skills-directory candidates in priority order."""
    candidates: list[Path] = []
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        candidates.append(Path(hermes_home).expanduser() / "skills")
    candidates.append(Path.home() / ".hermes" / "skills")
    candidates.extend(HERMES_FALLBACK_DIRS)
    return candidates


def hermes_skills_dir() -> Path | None:
    """First Hermes candidate that exists on disk, or None."""
    for candidate in hermes_candidate_dirs():
        if candidate.is_dir():
            return candidate
    return None


def detect_agent() -> Agent | None:
    """Detect the first supported Agent with a Skills directory on disk."""
    skills_dir = hermes_skills_dir()
    if skills_dir is not None:
        return Agent(key="hermes", name="Hermes", skills_dir=skills_dir)
    return None


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
                if name != "skills":
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
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "skillsync" / "config.json"


def save_skills_dir(agent_key: str, skills_dir: Path) -> None:
    """Persist the managed Skills directory in a tiny local config file."""
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
    """Resolve the Skills directory: env var > config file > auto-detect."""
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
