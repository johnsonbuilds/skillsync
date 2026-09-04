"""Unit tests for the Skill-level aggregation logic."""

from skillsync.git import StatusEntry
from skillsync.skills import aggregate_changes, group_by_skill, list_skills


def entry(path: str, x: str = " ", y: str = "M") -> StatusEntry:
    return StatusEntry(x=x, y=y, path=path)


def test_group_by_skill():
    grouped = group_by_skill(
        [
            "browser-research/SKILL.md",
            "browser-research/scripts/search.py",
            "github-pr/SKILL.md",
        ]
    )
    assert grouped == {
        "browser-research": [
            "browser-research/SKILL.md",
            "browser-research/scripts/search.py",
        ],
        "github-pr": ["github-pr/SKILL.md"],
    }


def test_group_ignores_root_files():
    assert group_by_skill(["README.md", "a/SKILL.md"]) == {"a": ["a/SKILL.md"]}


def test_aggregate_modified():
    changes = aggregate_changes(
        [entry("browser-research/SKILL.md"), entry("browser-research/x.md")],
        {"browser-research": True},
    )
    assert [c.state for c in changes] == ["M"]
    assert changes[0].name == "browser-research"
    assert changes[0].summary == "2 files changed"


def test_aggregate_new_skill():
    changes = aggregate_changes(
        [entry("deploy-k8s/SKILL.md", "?", "?")], {"deploy-k8s": False}
    )
    assert [c.state for c in changes] == ["A"]
    assert changes[0].summary == "new skill"


def test_aggregate_deleted():
    changes = aggregate_changes(
        [entry("old-deploy/x.md", " ", "D"), entry("old-deploy/y.md", "D", " ")],
        {"old-deploy": True},
    )
    assert [c.state for c in changes] == ["D"]
    assert changes[0].summary is None


def test_aggregate_mixed_prefers_modified():
    changes = aggregate_changes(
        [entry("a/SKILL.md"), entry("a/old.md", " ", "D")], {"a": True}
    )
    assert [c.state for c in changes] == ["M"]


def test_aggregate_sorted_by_name():
    changes = aggregate_changes(
        [entry("zz/SKILL.md"), entry("aa/SKILL.md")], {"zz": True, "aa": True}
    )
    assert [c.name for c in changes] == ["aa", "zz"]


def test_list_skills_ignores_dotdirs(tmp_path):
    (tmp_path / "browser-research").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    assert list_skills(tmp_path) == ["browser-research"]
