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


def hermes_skills_dir() -> Path:
    return Path.home() / ".hermes" / "skills"


def detect_agent() -> Agent | None:
    """Detect the first supported Agent with a Skills directory on disk."""
    if hermes_skills_dir().is_dir():
        return Agent(key="hermes", name="Hermes", skills_dir=hermes_skills_dir())
    return None


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
