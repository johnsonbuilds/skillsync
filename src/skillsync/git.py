"""Thin wrappers around the git command line.

SkillSync implements no version control logic of its own: every operation is
delegated to git via subprocess. This module is the only place that talks to
git directly.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git command fails."""


def git(*args: str, cwd: Path, check: bool = True) -> str:
    """Run ``git <args>`` inside ``cwd`` and return stdout."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise GitError(message or f"git {' '.join(args)} failed")
    return proc.stdout


def try_git(*args: str, cwd: Path) -> bool:
    """Run ``git <args>`` and return True when it exits with 0."""
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True).returncode == 0


def is_git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True)
    except FileNotFoundError:
        return False
    return True


def is_repo(path: Path) -> bool:
    """True when ``path`` itself contains a Git repository."""
    return (Path(path) / ".git").exists()


def has_commits(repo: Path) -> bool:
    """True when the repository has at least one commit."""
    return try_git("rev-parse", "--verify", "-q", "HEAD", cwd=repo)


def init(repo: Path) -> None:
    git("init", "-b", "main", cwd=repo)


def rev_parse(repo: Path, ref: str) -> str | None:
    """Resolve ``ref`` to a full commit hash, or None when unknown."""
    out = git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}", cwd=repo, check=False)
    return out.strip() or None


@dataclass(frozen=True)
class StatusEntry:
    """One line of ``git status --porcelain``."""

    x: str  # index (staged) status
    y: str  # worktree status
    path: str

    @property
    def untracked(self) -> bool:
        return self.x == "?" and self.y == "?"

    @property
    def deleted(self) -> bool:
        return "D" in (self.x, self.y)


def status_porcelain(repo: Path, *pathspecs: str) -> list[StatusEntry]:
    """File-level status, including untracked files, renames disabled."""
    out = git(
        "status", "--porcelain=v1", "-z", "-uall", "--no-renames", *pathspecs, cwd=repo
    )
    entries: list[StatusEntry] = []
    for record in out.split("\0"):
        if len(record) < 4:
            continue
        entries.append(StatusEntry(x=record[0], y=record[1], path=record[3:]))
    return entries


def diff_head(repo: Path, pathspec: str) -> str:
    """Unified diff between the last snapshot (HEAD) and the working tree."""
    return git("diff", "HEAD", "--no-color", "--", pathspec, cwd=repo, check=False)


def diff_new_file(repo: Path, path: str) -> str:
    """Unified diff showing an untracked file as entirely new."""
    return git(
        "diff", "--no-color", "--no-index", "--", "/dev/null", path, cwd=repo, check=False
    )


def ls_files(repo: Path, pathspec: str) -> list[str]:
    out = git("ls-files", "--", pathspec, cwd=repo)
    return [line for line in out.splitlines() if line]


def ls_tree(repo: Path, ref: str, pathspec: str | None = None) -> list[str]:
    """Paths in ``ref`` (optionally under ``pathspec``); empty without commits."""
    if not has_commits(repo):
        return []
    args = ["ls-tree", "-r", "--name-only", ref]
    if pathspec is not None:
        args += ["--", pathspec]
    out = git(*args, cwd=repo, check=False)
    return [line for line in out.splitlines() if line]


def add_all(repo: Path) -> None:
    git("add", "-A", cwd=repo)


def ensure_identity(repo: Path) -> None:
    """Guarantee commits are possible via a repo-local fallback identity."""
    if not try_git("config", "user.email", cwd=repo):
        git("config", "user.name", "SkillSync", cwd=repo)
        git("config", "user.email", "skillsync@localhost", cwd=repo)


def commit(repo: Path, message: str, *pathspecs: str) -> str | None:
    """Commit staged (or pathspec-scoped) changes.

    Returns the short hash of the new commit, or None when there was nothing
    to commit. Raises GitError on unexpected failures.
    """
    ensure_identity(repo)
    args = ["commit", "-m", message]
    if pathspecs:
        args += ["--", *pathspecs]
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip()
        if "nothing to commit" in err.lower():
            return None
        raise GitError(err or "git commit failed")
    return git("rev-parse", "--short", "HEAD", cwd=repo).strip()


@dataclass(frozen=True)
class LogEntry:
    hash: str
    date: str
    subject: str

    @property
    def short_hash(self) -> str:
        return self.hash[:7]


def log(repo: Path, pathspec: str | None = None, limit: int | None = None) -> list[LogEntry]:
    """Commit history, newest first, optionally scoped to a pathspec."""
    if not has_commits(repo):
        return []
    args = [
        "log",
        "--no-color",
        "--date=format:%Y-%m-%d",
        "--pretty=format:%H%x1f%ad%x1f%s",
    ]
    if limit:
        args += ["-n", str(limit)]
    if pathspec:
        args += ["--", pathspec]
    out = git(*args, cwd=repo, check=False)
    entries: list[LogEntry] = []
    for line in out.splitlines():
        if "\x1f" not in line:
            continue
        commit_hash, date, subject = line.split("\x1f", 2)
        entries.append(LogEntry(hash=commit_hash, date=date, subject=subject))
    return entries


def restore_skill(repo: Path, skill: str, target: str) -> str | None:
    """Restore ``skill/`` to exactly match ``target``.

    History is never rewritten or deleted; when the restore changes the
    current state it is recorded as a new commit. Returns the hash of that
    restore commit, or None when the skill already matched ``target``.
    """
    # 1. Drop untracked files under the skill; the restore replaces them.
    git("clean", "-fdq", "--", skill, cwd=repo, check=False)
    # 2. Remove the skill from the index and the working tree.
    if ls_files(repo, skill):
        git("rm", "-r", "-f", "-q", "--", skill, cwd=repo)
    # 3. Check the skill out from the target revision.
    if ls_tree(repo, target, skill):
        git("checkout", target, "--", skill, cwd=repo)
    # 4. Record the restore as a new commit so history is preserved.
    return commit(repo, f"SkillSync restore: {skill} to {target[:7]}", skill)
