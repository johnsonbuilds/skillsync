"""Unit tests for the thin git wrapper (v0.3.1).

commit()'s no-op contract must hold on every locale: emptiness is probed
via ``git diff`` exit codes, never via localized output strings.
"""

from pathlib import Path

from skillsync import git


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git.init(repo)
    (repo / "a.txt").write_text("one\n")
    git.add_all(repo)
    git.commit(repo, "first")
    return repo


def test_commit_first_snapshot_on_unborn_branch(tmp_path):
    repo = tmp_path / "fresh"
    repo.mkdir()
    git.init(repo)
    (repo / "a.txt").write_text("one\n")
    git.add_all(repo)
    assert git.commit(repo, "first") is not None
    assert len(git.log(repo)) == 1


def test_commit_returns_none_when_nothing_staged(tmp_path):
    repo = make_repo(tmp_path)
    assert git.commit(repo, "empty") is None
    assert len(git.log(repo)) == 1


def test_commit_returns_none_for_unchanged_pathspec(tmp_path):
    repo = make_repo(tmp_path)
    assert git.commit(repo, "empty", "a.txt") is None
    assert len(git.log(repo)) == 1


def test_commit_staged_changes(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("two\n")
    git.add_all(repo)
    short = git.commit(repo, "second")
    assert short is not None
    assert len(git.log(repo)) == 2


def test_commit_pathspec_scopes_the_commit(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("two\n")
    (repo / "b.txt").write_text("new\n")
    short = git.commit(repo, "only a", "a.txt")
    assert short is not None
    assert (repo / "a.txt").read_text() == "two\n"
    assert (repo / "b.txt").read_text() == "new\n"
    assert not git.ls_files(repo, "b.txt")  # b.txt stayed untracked
