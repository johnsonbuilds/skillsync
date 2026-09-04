"""End-to-end tests for the SkillSync CLI.

These run the real CLI (via Typer's test runner) against a temporary Skills
directory and exercise the full MVP workflow from the functional design,
section 19.
"""

import shutil

import pytest
from typer.testing import CliRunner

from skillsync.cli import app
from skillsync.git import log as git_log

runner = CliRunner()


def invoke(*args: str, input: str | None = None):
    return runner.invoke(app, list(args), input=input)


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    """A fake Hermes-style Skills directory with two skills."""
    d = tmp_path / "skills"
    d.mkdir()
    (d / "browser-research").mkdir()
    (d / "browser-research" / "SKILL.md").write_text(
        "# Browser Research\n\nSearch well.\n"
    )
    (d / "browser-research" / "scripts").mkdir()
    (d / "browser-research" / "scripts" / "search.py").write_text("print('search')\n")
    (d / "github-pr").mkdir()
    (d / "github-pr" / "SKILL.md").write_text("# GitHub PR\n\nDo PRs.\n")

    monkeypatch.setenv("SKILLSYNC_SKILLS_DIR", str(d))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return d


def test_status_fails_before_init(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLSYNC_SKILLS_DIR", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    result = invoke("status")
    assert result.exit_code == 1
    assert "not initialized" in result.output


def test_full_mvp_workflow(skills_dir):
    # --- init ------------------------------------------------------------
    result = invoke("init")
    assert result.exit_code == 0, result.output
    assert "Found 2 skills." in result.output
    assert "Initial snapshot created." in result.output
    assert (skills_dir / ".git").exists()

    # --- re-init reuses the repository, never overwrites ------------------
    result = invoke("init")
    assert result.exit_code == 0, result.output
    assert "reusing it" in result.output
    assert "Existing history preserved." in result.output

    # --- status: clean ----------------------------------------------------
    result = invoke("status")
    assert result.exit_code == 0, result.output
    assert "No changes." in result.output

    # --- the Agent modifies a Skill ----------------------------------------
    (skills_dir / "browser-research" / "SKILL.md").write_text(
        "# Browser Research\n\nSearch badly.\n"
    )
    (skills_dir / "browser-research" / "references").mkdir()
    (skills_dir / "browser-research" / "references" / "notes.md").write_text("n\n")

    # --- status: Skill-level change ----------------------------------------
    result = invoke("status")
    assert result.exit_code == 0, result.output
    assert " M  browser-research" in result.output
    assert "2 files changed" in result.output
    assert "1 skill changed" in result.output

    # --- diff: shows the actual change -------------------------------------
    result = invoke("diff", "browser-research")
    assert result.exit_code == 0, result.output
    assert "-Search well." in result.output
    assert "+Search badly." in result.output
    assert "new file: browser-research/references/notes.md" in result.output

    # --- diff: unchanged skill ----------------------------------------------
    result = invoke("diff", "github-pr")
    assert result.exit_code == 0, result.output
    assert "No changes." in result.output

    # --- diff: unknown skill -------------------------------------------------
    result = invoke("diff", "nope")
    assert result.exit_code == 1

    # --- snapshot -------------------------------------------------------------
    result = invoke("snapshot", "-m", "Agent modified browser research")
    assert result.exit_code == 0, result.output
    assert "1 skill changed." in result.output
    assert "Snapshot created:" in result.output

    result = invoke("status")
    assert "No changes." in result.output

    # --- snapshot with no changes ----------------------------------------------
    result = invoke("snapshot")
    assert "No changes to snapshot." in result.output

    # --- the Agent makes the Skill worse (uncommitted) ---------------------------
    (skills_dir / "browser-research" / "SKILL.md").write_text(
        "# Browser Research\n\nbroken beyond repair\n"
    )
    (skills_dir / "browser-research" / "scripts" / "search.py").unlink()
    (skills_dir / "browser-research" / "junk.txt").write_text("junk\n")

    result = invoke("status")
    assert " M  browser-research" in result.output

    # --- log ------------------------------------------------------------------
    result = invoke("log")
    assert "commit " in result.output
    assert "Agent modified browser research" in result.output
    result = invoke("log", "browser-research")
    assert "Agent modified browser research" in result.output

    # --- restore: confirmation --------------------------------------------------
    result = invoke("restore", "browser-research", input="n\n")
    assert result.exit_code == 0, result.output
    assert "Aborted." in result.output
    assert "broken beyond repair" in (
        skills_dir / "browser-research" / "SKILL.md"
    ).read_text()

    # --- restore: back to the previous known state -------------------------------
    result = invoke("restore", "browser-research", "--yes")
    assert result.exit_code == 0, result.output
    assert "Restored browser-research" in result.output

    # the bad change is gone, the snapshot state is back
    assert (
        "# Browser Research\n\nSearch badly.\n"
        == (skills_dir / "browser-research" / "SKILL.md").read_text()
    )
    assert (skills_dir / "browser-research" / "scripts" / "search.py").exists()
    assert not (skills_dir / "browser-research" / "junk.txt").exists()

    # --- status: clean again -------------------------------------------------------
    result = invoke("status")
    assert "No changes." in result.output


def test_restore_specific_commit_creates_new_commit(skills_dir):
    invoke("init")

    # S1: a good state
    (skills_dir / "browser-research" / "SKILL.md").write_text("good v1\n")
    invoke("snapshot", "-m", "good v1")
    s1 = git_log(skills_dir, limit=1)[0].hash

    # S2: a committed bad state
    (skills_dir / "browser-research" / "SKILL.md").write_text("bad v2\n")
    invoke("snapshot", "-m", "bad v2")

    # restore the skill to S1
    result = invoke("restore", "browser-research", s1, "--yes")
    assert result.exit_code == 0, result.output
    assert "Restore snapshot created:" in result.output

    assert (skills_dir / "browser-research" / "SKILL.md").read_text() == "good v1\n"
    result = invoke("status")
    assert "No changes." in result.output

    # history is preserved: both snapshots still exist, plus the restore
    subjects = [entry.subject for entry in git_log(skills_dir)]
    assert subjects == [
        "SkillSync restore: browser-research to " + s1[:7],
        "bad v2",
        "good v1",
        "SkillSync initial snapshot",
    ]


def test_new_and_deleted_skills(skills_dir):
    invoke("init")

    # a brand new skill shows up as "A"
    (skills_dir / "deploy-k8s").mkdir()
    (skills_dir / "deploy-k8s" / "SKILL.md").write_text("# Deploy\n")
    result = invoke("status")
    assert " A  deploy-k8s" in result.output
    assert "new skill" in result.output

    # a deleted skill shows up as "D"
    shutil.rmtree(skills_dir / "github-pr")
    result = invoke("status")
    assert " D  github-pr" in result.output

    # snapshot both changes
    result = invoke("snapshot", "-m", "add deploy-k8s, drop github-pr")
    assert result.exit_code == 0, result.output
    assert "2 skills changed." in result.output

    result = invoke("status")
    assert "No changes." in result.output

    # diff of all skills when nothing changed
    result = invoke("diff")
    assert "No changes." in result.output


def test_snapshot_without_message_uses_default(skills_dir):
    invoke("init")
    (skills_dir / "github-pr" / "SKILL.md").write_text("changed\n")
    result = invoke("snapshot")
    assert result.exit_code == 0, result.output
    assert "Snapshot created:" in result.output
    subjects = [entry.subject for entry in git_log(skills_dir, limit=1)]
    assert subjects[0].startswith("SkillSync snapshot: ")


# ---------------------------------------------------------------------------
# nested (category / skill) layouts, e.g. Hermes-style Skills directories
# ---------------------------------------------------------------------------


@pytest.fixture
def nested_skills_dir(tmp_path, monkeypatch):
    """A Hermes-style three-layer Skills directory: category / skill / files."""
    d = tmp_path / "skills"
    pdf = d / "productivity" / "pdf"
    pdf.mkdir(parents=True)
    (pdf / "SKILL.md").write_text("# PDF\n\nMerge pages.\n")
    (pdf / "scripts").mkdir()
    (pdf / "scripts" / "run.py").write_text("print('pdf')\n")
    browser = d / "research" / "browser"
    browser.mkdir(parents=True)
    (browser / "SKILL.md").write_text("# Browser\n\nSearch well.\n")
    # category docs and caches: never Skills
    (d / "DESCRIPTION.md").write_text("category docs\n")
    (d / "index-cache").mkdir()
    (d / "index-cache" / "skills.json").write_text("{}\n")
    monkeypatch.setenv("SKILLSYNC_SKILLS_DIR", str(d))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return d


def test_nested_layout_workflow(nested_skills_dir):
    d = nested_skills_dir

    # --- init counts real Skills, not categories ----------------------------
    result = invoke("init")
    assert result.exit_code == 0, result.output
    assert "Found 2 skills." in result.output
    assert "Initial snapshot created." in result.output

    result = invoke("status")
    assert "No changes." in result.output

    # --- the Agent modifies one Skill inside a category ----------------------
    (d / "productivity" / "pdf" / "SKILL.md").write_text("# PDF\n\nbroken merge\n")
    (d / "productivity" / "pdf" / "scripts" / "extra.py").write_text("x = 1\n")

    # --- status: Skill-level, not category-level ------------------------------
    result = invoke("status")
    assert result.exit_code == 0, result.output
    assert " M  productivity/pdf" in result.output
    # the category itself must never be reported as the changed unit
    assert " M  productivity\n" not in result.output
    assert " M  research\n" not in result.output
    assert "1 skill changed" in result.output

    # --- diff / log / restore accept the relative-path Skill ID ---------------
    result = invoke("diff", "productivity/pdf")
    assert result.exit_code == 0, result.output
    assert "-Merge pages." in result.output
    assert "+broken merge" in result.output
    assert "new file: productivity/pdf/scripts/extra.py" in result.output

    result = invoke("diff", "productivity")
    assert result.exit_code == 1  # a category is not a Skill

    result = invoke("log", "productivity/pdf")
    assert "SkillSync initial snapshot" in result.output

    # --- snapshot and restore the nested Skill --------------------------------
    result = invoke("snapshot", "-m", "agent broke pdf")
    assert result.exit_code == 0, result.output
    assert "1 skill changed." in result.output

    (d / "productivity" / "pdf" / "SKILL.md").write_text("# PDF\n\nworse\n")
    (d / "productivity" / "pdf" / "junk.txt").write_text("junk\n")
    result = invoke("restore", "productivity/pdf", "--yes")
    assert result.exit_code == 0, result.output
    assert "Restored productivity/pdf" in result.output
    assert (d / "productivity" / "pdf" / "SKILL.md").read_text() == "# PDF\n\nbroken merge\n"
    assert (d / "productivity" / "pdf" / "scripts" / "extra.py").exists()
    assert not (d / "productivity" / "pdf" / "junk.txt").exists()

    result = invoke("status")
    assert "No changes." in result.output

    # --- new and deleted Skills inside categories ------------------------------
    newcli = d / "research" / "newcli"
    newcli.mkdir()
    (newcli / "SKILL.md").write_text("# New CLI\n")
    shutil.rmtree(d / "research" / "browser")
    # a file outside any Skill: noted, never swallowed
    (d / "NOTES.md").write_text("loose file\n")

    result = invoke("status")
    assert " A  research/newcli" in result.output
    assert " D  research/browser" in result.output
    assert "2 skills changed" in result.output
    assert "1 file(s) changed outside any Skill" in result.output

    result = invoke("snapshot", "-m", "swap research skills")
    assert result.exit_code == 0, result.output
    result = invoke("status")
    assert "No changes." in result.output


def test_nested_layout_diff_new_file(nested_skills_dir):
    d = nested_skills_dir
    invoke("init")
    (d / "productivity" / "timer").mkdir(parents=True)
    (d / "productivity" / "timer" / "SKILL.md").write_text("# Timer\n")
    result = invoke("diff", "productivity/timer")
    assert result.exit_code == 0, result.output
    assert "new file: productivity/timer/SKILL.md" in result.output
