"""Unit tests for Skill discovery and the Skill-level aggregation logic."""

import pytest

from skillsync import git
from skillsync.git import StatusEntry
from skillsync.skills import (
    aggregate_changes,
    discover_skills,
    group_by_skill,
    head_skill_roots,
    normalize_roots,
)


def entry(path: str, x: str = " ", y: str = "M") -> StatusEntry:
    return StatusEntry(x=x, y=y, path=path)


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def make_skill(root, *segments: str) -> None:
    """Create a Skill directory with a SKILL.md under ``root``."""
    d = root.joinpath(*segments)
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"# {segments[-1]}\n")


def test_discover_flat_layout(tmp_path):
    make_skill(tmp_path, "browser-research")
    make_skill(tmp_path, "github-pr")
    (tmp_path / "file.txt").write_text("x")
    assert discover_skills(tmp_path) == ["browser-research", "github-pr"]


def test_discover_category_nested_layout(tmp_path):
    make_skill(tmp_path, "productivity", "pdf")
    make_skill(tmp_path, "productivity", "timer")
    make_skill(tmp_path, "research", "browser")
    assert discover_skills(tmp_path) == [
        "productivity/pdf",
        "productivity/timer",
        "research/browser",
    ]


def test_discover_deep_nesting(tmp_path):
    make_skill(tmp_path, "optional-skills", "mlops", "training", "axolotl")
    make_skill(tmp_path, "optional-skills", "yuanbao")
    assert discover_skills(tmp_path) == [
        "optional-skills/mlops/training/axolotl",
        "optional-skills/yuanbao",
    ]


def test_discover_does_not_descend_into_a_skill(tmp_path):
    # A nested SKILL.md belongs to the enclosing Skill's payload, not to a
    # separate Skill (Agent Skills discovery rules).
    make_skill(tmp_path, "a")
    make_skill(tmp_path, "a", "nested")
    assert discover_skills(tmp_path) == ["a"]


def test_discover_ignores_dirs_without_marker(tmp_path):
    make_skill(tmp_path, "real")
    (tmp_path / "category").mkdir()
    (tmp_path / "category" / "DESCRIPTION.md").write_text("docs")
    (tmp_path / "index-cache").mkdir()
    (tmp_path / "index-cache" / "skills.json").write_text("{}")
    assert discover_skills(tmp_path) == ["real"]


def test_discover_skips_hidden_and_dependency_dirs(tmp_path):
    make_skill(tmp_path, "real")
    make_skill(tmp_path, ".git", "hook-skill")
    make_skill(tmp_path, "node_modules", "pkg-skill")
    make_skill(tmp_path, ".venv", "venv-skill")
    assert discover_skills(tmp_path) == ["real"]


def test_discover_empty_dir(tmp_path):
    assert discover_skills(tmp_path) == []


# ---------------------------------------------------------------------------
# HEAD-side discovery
# ---------------------------------------------------------------------------


def _init_repo_with_skills(tmp_path):
    make_skill(tmp_path, "productivity", "pdf")
    make_skill(tmp_path, "a")
    git.init(tmp_path)
    git.add_all(tmp_path)
    git.commit(tmp_path, "SkillSync initial snapshot")


def test_head_skill_roots_from_committed_tree(tmp_path):
    _init_repo_with_skills(tmp_path)
    assert head_skill_roots(tmp_path) == {"a", "productivity/pdf"}


def test_head_skill_roots_empty_without_commits(tmp_path):
    make_skill(tmp_path, "a")
    git.init(tmp_path)
    assert head_skill_roots(tmp_path) == set()


def test_normalize_roots_drops_nested_roots():
    assert normalize_roots({"a", "a/b", "c", "a/b/deep"}) == {"a", "c"}


# ---------------------------------------------------------------------------
# grouping
# ---------------------------------------------------------------------------


def test_group_by_skill_flat_roots():
    grouped = group_by_skill(
        [
            "browser-research/SKILL.md",
            "browser-research/scripts/search.py",
            "github-pr/SKILL.md",
        ],
        {"browser-research", "github-pr"},
    )
    assert grouped == {
        "browser-research": [
            "browser-research/SKILL.md",
            "browser-research/scripts/search.py",
        ],
        "github-pr": ["github-pr/SKILL.md"],
    }


def test_group_by_skill_nested_roots():
    grouped = group_by_skill(
        [
            "productivity/pdf/SKILL.md",
            "productivity/pdf/scripts/run.py",
            "productivity/timer/SKILL.md",
        ],
        {"productivity/pdf", "productivity/timer"},
    )
    assert grouped == {
        "productivity/pdf": [
            "productivity/pdf/SKILL.md",
            "productivity/pdf/scripts/run.py",
        ],
        "productivity/timer": ["productivity/timer/SKILL.md"],
    }


def test_group_by_skill_deepest_root_wins():
    # A skill dir inside another managed root: files go to the deepest one.
    grouped = group_by_skill(
        ["a/SKILL.md", "a/sub/SKILL.md", "a/other.md"],
        {"a", "a/sub"},
    )
    assert grouped["a"] == ["a/SKILL.md", "a/other.md"]
    assert grouped["a/sub"] == ["a/sub/SKILL.md"]


def test_group_by_skill_ignores_outside_files():
    grouped = group_by_skill(
        ["README.md", "notes.txt", "productivity/DESCRIPTION.md"],
        {"productivity/pdf"},
    )
    assert grouped == {}


def test_group_by_skill_no_false_prefix_match():
    # "a/b" must not match paths under "a/bc".
    grouped = group_by_skill(["a/bc/SKILL.md"], {"a/b"})
    assert grouped == {}


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


def test_aggregate_flat_added_modified_deleted():
    changes = aggregate_changes(
        [
            entry("new-skill/SKILL.md", "?", "?"),
            entry("kept/SKILL.md"),
            entry("old-deploy/SKILL.md", " ", "D"),
            entry("old-deploy/run.sh", " ", "D"),
        ],
        {"new-skill", "kept", "old-deploy"},
        {"kept", "old-deploy"},
    )
    by_name = {c.name: c.state for c in changes}
    assert by_name == {"new-skill": "A", "kept": "M", "old-deploy": "D"}
    assert {c.name: c.summary for c in changes} == {
        "kept": "1 file changed",
        "new-skill": "new skill",
        "old-deploy": None,
    }


def test_aggregate_nested_uses_relative_path_identity():
    changes = aggregate_changes(
        [entry("productivity/pdf/SKILL.md"), entry("productivity/pdf/new.py", "?", "?")],
        {"productivity/pdf"},
        {"productivity/pdf"},
    )
    assert [c.name for c in changes] == ["productivity/pdf"]
    assert changes[0].summary == "2 files changed"


def test_aggregate_deleted_skill_known_only_from_head():
    # The directory is gone from disk; the root still exists in HEAD.
    changes = aggregate_changes(
        [entry("research/browser/SKILL.md", " ", "D")],
        {"research/browser"},
        {"research/browser"},
    )
    assert [c.state for c in changes] == ["D"]
    assert changes[0].summary is None


def test_aggregate_new_skill_missing_from_head():
    changes = aggregate_changes(
        [entry("research/newcli/SKILL.md", "?", "?")],
        {"research/newcli"},
        set(),
    )
    assert [c.state for c in changes] == ["A"]


def test_aggregate_mixed_prefers_modified():
    changes = aggregate_changes(
        [entry("a/SKILL.md"), entry("a/old.md", " ", "D")], {"a"}, {"a"}
    )
    assert [c.state for c in changes] == ["M"]


def test_aggregate_sorted_by_name():
    changes = aggregate_changes(
        [entry("zz/SKILL.md"), entry("aa/SKILL.md")], {"zz", "aa"}, {"zz", "aa"}
    )
    assert [c.name for c in changes] == ["aa", "zz"]


def test_aggregate_ignores_files_outside_skills():
    changes = aggregate_changes(
        [entry("README.md", "?", "?"), entry("productivity/DESCRIPTION.md", "?", "?")],
        {"productivity/pdf"},
        {"productivity/pdf"},
    )
    assert changes == []
