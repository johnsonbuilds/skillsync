"""Thin wrappers around the git command line.

SkillSync implements no version control logic of its own: every operation is
delegated to git via subprocess. This module is the only place that talks to
git directly.

Remote operations (fetch, push, clone) run with terminal prompts disabled
and a subprocess timeout, so an unreachable remote fails cleanly instead of
hanging. SkillSync never force-pushes: there is deliberately no wrapper for
``git push --force``.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

REMOTE_NAME = "origin"

# Network operation budgets (seconds). Generous for pushes/clones, tight for
# the fetch used by `status` — a version-control command must never hang.
LS_REMOTE_TIMEOUT = 15
FETCH_TIMEOUT = 10
PUSH_TIMEOUT = 120
CLONE_TIMEOUT = 300


class GitError(RuntimeError):
    """Raised when a git command fails."""


def _net_env() -> dict[str, str]:
    """Environment for network commands: never prompt for credentials."""
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


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


def merge_base(repo: Path, a: str, b: str) -> str | None:
    """Common ancestor commit of two refs, or None when they diverge."""
    out = git("merge-base", a, b, cwd=repo, check=False)
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


# ---------------------------------------------------------------------------
# remote operations
#
# SkillSync's remote layer is intentionally thin: it configures git's own
# remote (always named ``origin``) and wraps the four network verbs with
# timeouts and non-interactive credentials. Conflict resolution policy lives
# in the CLI layer, not here.
# ---------------------------------------------------------------------------


def _net(args: list[str], cwd: Path | None, timeout: int) -> str:
    """Run a network git command with prompts disabled and a timeout."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_net_env(),
        )
    except subprocess.TimeoutExpired:
        raise GitError(
            f"git {' '.join(args[:2])} timed out after {timeout}s "
            "(remote unreachable?)"
        )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise GitError(message or f"git {' '.join(args[:2])} failed")
    return proc.stdout


def remote_url(repo: Path) -> str | None:
    """The configured remote URL, or None when no remote is set up."""
    proc = subprocess.run(
        ["git", "remote", "get-url", REMOTE_NAME],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def remote_add(repo: Path, url: str) -> None:
    git("remote", "add", REMOTE_NAME, url, cwd=repo)


def remote_remove(repo: Path) -> None:
    git("remote", "remove", REMOTE_NAME, cwd=repo)


def url_is_reachable(url: str) -> bool:
    """True when git can talk to ``url`` at all (auth and network included)."""
    try:
        _net(["ls-remote", "--heads", url], cwd=None, timeout=LS_REMOTE_TIMEOUT)
    except GitError:
        return False
    return True


def fetch(repo: Path) -> None:
    """Update remote-tracking refs; raises GitError when unreachable."""
    _net(["fetch", "--quiet", REMOTE_NAME], cwd=repo, timeout=FETCH_TIMEOUT)


def current_branch(repo: Path) -> str:
    out = git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)
    return out.strip()


def remote_branch(repo: Path, branch: str) -> str | None:
    """Full hash of ``origin/<branch>``, or None when the remote has none."""
    return rev_parse(repo, f"{REMOTE_NAME}/{branch}")


def has_merge_base(repo: Path, a: str, b: str) -> bool:
    """False when two refs share no history (unrelated histories)."""
    return try_git("merge-base", a, b, cwd=repo)


def ahead_behind(repo: Path, branch: str) -> tuple[int, int] | None:
    """(ahead, behind) of ``origin/<branch>``, or None when not comparable."""
    out = git(
        "rev-list", "--left-right", "--count",
        f"{branch}...{REMOTE_NAME}/{branch}",
        cwd=repo, check=False,
    )
    parts = out.split()
    if len(parts) != 2:
        return None
    return int(parts[0]), int(parts[1])


def merge_ff_only(repo: Path, ref: str) -> None:
    git("merge", "--ff-only", ref, cwd=repo)


@dataclass(frozen=True)
class RebaseResult:
    ok: bool
    detail: str  # stderr on failure


def rebase(repo: Path, ref: str) -> RebaseResult:
    """Replay local commits onto ``ref``. Never aborts on its own."""
    proc = subprocess.run(
        ["git", "rebase", ref],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return RebaseResult(ok=True, detail="")
    return RebaseResult(ok=False, detail=(proc.stderr or proc.stdout).strip())


def conflicted_paths(repo: Path) -> list[str]:
    """Paths with unresolved conflicts (valid only mid-conflict)."""
    out = git(
        "diff", "--name-only", "--diff-filter=U", cwd=repo, check=False
    )
    return [line for line in out.splitlines() if line]


def rebase_abort(repo: Path) -> None:
    """Best-effort rebase abort: restore the exact pre-rebase state."""
    try:
        git("rebase", "--abort", cwd=repo)
    except GitError:
        pass


def push(repo: Path, branch: str) -> tuple[bool, str]:
    """Push ``branch`` to origin and set upstream.

    Returns (True, "") on success. Never force-pushes; a rejected
    non-fast-forward returns (False, stderr) so the caller can explain it.
    """
    try:
        _net(
            ["push", "-u", REMOTE_NAME, branch],
            cwd=repo,
            timeout=PUSH_TIMEOUT,
        )
    except GitError as exc:
        return False, str(exc)
    return True, ""


def reset_hard(repo: Path, ref: str) -> None:
    git("reset", "--hard", ref, cwd=repo)


def clone(url: str, path: Path) -> None:
    _net(["clone", "--quiet", url, str(path)], cwd=None, timeout=CLONE_TIMEOUT)
