"""Skill model: discover Skills and group git file changes by Skill.

This is the core differentiator of SkillSync: users think in terms of
Skills ("browser-research changed"), not individual files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .git import StatusEntry


def list_skills(skills_dir: Path) -> list[str]:
    """Sorted names of immediate subdirectories that look like Skills."""
    return sorted(
        p.name
        for p in skills_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


@dataclass
class SkillChange:
    """A Skill-level change aggregated from file-level git status."""

    name: str
    state: str  # "A" added / "M" modified / "D" deleted
    files: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str | None:
        if self.state == "A":
            return "new skill"
        if self.state == "M":
            count = len(self.files)
            return f"{count} file{'s' if count != 1 else ''} changed"
        return None  # deleted: no summary line


def group_by_skill(paths: list[str]) -> dict[str, list[str]]:
    """Map changed file paths to their top-level directory (the Skill)."""
    grouped: dict[str, list[str]] = {}
    for path in paths:
        parts = path.split("/")
        if len(parts) < 2:
            continue  # repository-root files are not Skills
        grouped.setdefault(parts[0], []).append(path)
    return grouped


def aggregate_changes(
    entries: list[StatusEntry],
    in_head: dict[str, bool] | None = None,
) -> list[SkillChange]:
    """Collapse file-level git status into Skill-level changes.

    ``in_head`` maps a Skill name to whether it exists in the last snapshot
    (HEAD). Skills missing from HEAD are reported as new ("A"); skills whose
    files are all deleted are reported as deleted ("D"); everything else is
    a modification ("M").
    """
    in_head = in_head or {}
    grouped: dict[str, list[StatusEntry]] = {}
    for entry in entries:
        parts = entry.path.split("/")
        if len(parts) < 2:
            continue
        grouped.setdefault(parts[0], []).append(entry)

    changes: list[SkillChange] = []
    for name in sorted(grouped):
        files = grouped[name]
        if not in_head.get(name, False):
            state = "A"
        elif all(entry.deleted for entry in files):
            state = "D"
        else:
            state = "M"
        changes.append(
            SkillChange(name=name, state=state, files=[entry.path for entry in files])
        )
    return changes
