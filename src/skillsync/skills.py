"""Skill model: discover Skills and group git file changes by Skill.

This is the core differentiator of SkillSync: users think in terms of
Skills ("browser-research changed"), not individual files.

A Skill is any directory that directly contains a ``SKILL.md`` file, at any
depth below the Skills directory. This matches Agent Skills discovery rules
and covers flat layouts (``browser-research/``), category-nested layouts
(``productivity/pdf/``), deeper nesting
(``optional-skills/mlops/training/axolotl/``), and single-directory Skills
(``yuanbao/SKILL.md``) alike. Directories without ``SKILL.md`` (category
descriptions, caches, dependency trees) are never Skills.

A Skill is identified by its path relative to the Skills directory
(e.g. ``productivity/pdf``). This stays unique and unambiguous no matter
how the harness organizes its Skills directory, and doubles as the git
pathspec for diff/log/restore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import git
from .git import StatusEntry

SKILL_MARKER = "SKILL.md"

# Directories never descended into during discovery.
DISCOVERY_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
}


def discover_skills(skills_dir: Path) -> list[str]:
    """Relative POSIX paths of directories that directly contain SKILL.md.

    Discovery walks the Skills directory tree. A directory containing
    ``SKILL.md`` is a Skill and is not descended into: nested ``SKILL.md``
    files are part of that Skill's payload, not separate Skills. Hidden and
    dependency directories are skipped. A ``SKILL.md`` at the very root of
    the Skills directory is ignored (the root itself is not a Skill).
    """
    roots: list[str] = []

    def walk(directory: Path) -> None:
        if directory != skills_dir and (directory / SKILL_MARKER).is_file():
            roots.append(directory.relative_to(skills_dir).as_posix())
            return  # a discovered Skill is never descended into
        try:
            children = list(directory.iterdir())
        except OSError:
            return
        for child in children:
            if (
                child.is_dir()
                and not child.name.startswith(".")
                and child.name not in DISCOVERY_SKIP_DIRS
            ):
                walk(child)

    walk(skills_dir)
    return sorted(roots)


def normalize_roots(roots: Iterable[str]) -> set[str]:
    """Drop Skill roots nested inside another root (outermost wins)."""
    kept: list[str] = []
    for root in sorted(roots, key=lambda r: (r.count("/"), r)):
        if not any(root == k or root.startswith(k + "/") for k in kept):
            kept.append(root)
    return set(kept)


def _roots_deepest_first(roots: Iterable[str]) -> list[tuple[int, str]]:
    """Roots keyed by depth, sorted deepest first (longest prefix wins)."""
    return sorted(((r.count("/"), r) for r in set(roots)), key=lambda t: (-t[0], t[1]))


def _enclosing_root(path: str, deepest_first: list[tuple[int, str]]) -> str | None:
    """The deepest Skill root whose directory contains ``path``, if any."""
    for _, root in deepest_first:
        if path.startswith(root + "/"):
            return root
    return None


def group_by_skill(
    paths: list[str], skill_roots: Iterable[str]
) -> dict[str, list[str]]:
    """Map changed file paths to their enclosing Skill.

    ``skill_roots`` holds Skill identity paths relative to the Skills
    directory (see ``discover_skills``). A file belongs to the deepest Skill
    root that contains it; files outside every Skill root are not grouped
    (SkillSync reports them as changed files outside any Skill).
    """
    deepest_first = _roots_deepest_first(skill_roots)
    grouped: dict[str, list[str]] = {}
    for path in paths:
        root = _enclosing_root(path, deepest_first)
        if root is not None:
            grouped.setdefault(root, []).append(path)
    return grouped


def skill_roots_at(skills_dir: Path, ref: str) -> set[str]:
    """Skill roots present in commit ``ref`` (directories with SKILL.md)."""
    roots = {
        path.rsplit("/", 1)[0]
        for path in git.ls_tree(skills_dir, ref)
        if "/" in path and path.rsplit("/", 1)[1] == SKILL_MARKER
    }
    return normalize_roots(roots)


def head_skill_roots(skills_dir: Path) -> set[str]:
    """Skill roots present in the last snapshot (HEAD).

    Discovered the same way as on disk (directories containing SKILL.md), so
    that Skills deleted from the working tree still group correctly. Empty
    when the repository has no commits yet.
    """
    return skill_roots_at(skills_dir, "HEAD")


def changed_skills(skills_dir: Path, base: str, head: str) -> list[str]:
    """Sorted Skill identities touched by the commits between base and head.

    Skill roots are collected from both endpoint trees, so Skills added or
    deleted inside the range still group correctly; changed paths outside
    every Skill root (e.g. a root-level README) are ignored.
    """
    out = git.git("diff", "--name-only", f"{base}..{head}", cwd=skills_dir, check=False)
    paths = [line for line in out.splitlines() if line]
    if not paths:
        return []
    roots = skill_roots_at(skills_dir, base) | skill_roots_at(skills_dir, head)
    return sorted(group_by_skill(paths, roots))


@dataclass
class SkillChange:
    """A Skill-level change aggregated from file-level git status."""

    name: str  # Skill identity: path relative to the Skills directory
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


def aggregate_changes(
    entries: list[StatusEntry],
    skill_roots: Iterable[str],
    head_roots: Iterable[str] = (),
) -> list[SkillChange]:
    """Collapse file-level git status into Skill-level changes.

    ``skill_roots`` is the set of known Skill identities (on disk plus in
    HEAD); ``head_roots`` is the subset present in the last snapshot.
    Skills missing from HEAD are new ("A"); Skills whose files are all
    deleted are gone ("D"); everything else is a modification ("M").
    """
    deepest_first = _roots_deepest_first(skill_roots)
    head = set(head_roots)

    grouped: dict[str, list[StatusEntry]] = {}
    for entry in entries:
        root = _enclosing_root(entry.path, deepest_first)
        if root is not None:
            grouped.setdefault(root, []).append(entry)

    changes: list[SkillChange] = []
    for name in sorted(grouped):
        files = grouped[name]
        if name not in head:
            state = "A"
        elif all(entry.deleted for entry in files):
            state = "D"
        else:
            state = "M"
        changes.append(
            SkillChange(name=name, state=state, files=[entry.path for entry in files])
        )
    return changes
