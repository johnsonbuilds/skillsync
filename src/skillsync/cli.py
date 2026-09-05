"""SkillSync command line interface.

Local version control:

    skillsync init
    skillsync status
    skillsync diff [skill]
    skillsync snapshot [-m "message"]
    skillsync log [skill]
    skillsync restore <skill> [commit]

Remote synchronization (GitHub or any git remote):

    skillsync remote [add <url> | remove]
    skillsync clone <url> <path>
    skillsync sync [--use-remote]

SkillSync never force-pushes, and network failures never change local
state: when `sync` cannot reach the remote, local snapshots are untouched.
"""

from __future__ import annotations

import datetime as _dt
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import typer

from . import __version__, git
from .agent import (
    AGENT_KEYS,
    AGENT_KEYS_HELP,
    Agent,
    find_agent,
    find_agents,
    label_agent,
    load_skills_dir,
    save_skills_dir,
    search_skill_dirs,
)
from .skills import (
    SkillChange,
    aggregate_changes,
    changed_skills,
    discover_skills,
    group_by_skill,
    head_skill_roots,
)

app = typer.Typer(
    help="Git-based version control for Agent Skills.",
    no_args_is_help=True,
    add_completion=False,
)
remote_app = typer.Typer(invoke_without_command=True)
app.add_typer(remote_app, name="remote", help="Manage the GitHub remote.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"skillsync {__version__}")
        raise typer.Exit()


@app.callback()
def _main_callback(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Git-based version control for Agent Skills."""


def main() -> None:
    """Console-script entry point."""
    app()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _die(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


@contextmanager
def git_errors() -> Iterator[None]:
    """Turn unexpected git failures into clean CLI error messages."""
    try:
        yield
    except git.GitError as exc:
        _die(f"Error: {exc}")


def _display_path(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def _require_git() -> None:
    if not git.is_git_available():
        _die("Error: git is required but was not found on PATH.")


def _skills_dir() -> Path:
    """Resolve and validate the Skills directory for non-init commands."""
    skills_dir = load_skills_dir()
    if skills_dir is None:
        _die(
            "Error: could not find an Agent Skills directory.\n"
            "Run `skillsync init` first, or set SKILLSYNC_SKILLS_DIR."
        )
    if not skills_dir.is_dir():
        _die(f"Error: Skills directory not found: {skills_dir}")
    if not git.is_repo(skills_dir):
        _die(
            f"Error: SkillSync is not initialized in {skills_dir}.\n"
            "Run `skillsync init` first."
        )
    return skills_dir


def _skill_exists(skills_dir: Path, name: str) -> bool:
    """A Skill exists when it is on disk or in the last snapshot (HEAD).

    ``name`` is the Skill identity: its path relative to the Skills
    directory (e.g. ``browser-research`` or ``productivity/pdf``).
    """
    if name in set(discover_skills(skills_dir)):
        return True
    return name in head_skill_roots(skills_dir)


def _skill_changes(skills_dir: Path) -> tuple[list[SkillChange], int]:
    """Aggregate file-level status into Skill-level changes."""
    entries = git.status_porcelain(skills_dir)
    disk_roots = discover_skills(skills_dir)
    head_roots = head_skill_roots(skills_dir)
    all_roots = set(disk_roots) | head_roots
    changes = aggregate_changes(entries, all_roots, head_roots)
    managed = {
        path
        for paths in group_by_skill(
            [entry.path for entry in entries], all_roots
        ).values()
        for path in paths
    }
    unmanaged = sum(1 for entry in entries if entry.path not in managed)
    return changes, unmanaged


def _print_status(changes: list[SkillChange], unmanaged: int) -> None:
    if not changes:
        typer.echo("No changes.")
        return
    blocks: list[str] = []
    for change in changes:
        lines = [f" {change.state}  {change.name}"]
        summary = change.summary
        if summary:
            lines.append(f"    {summary}")
        blocks.append("\n".join(lines))
    typer.echo("Skills\n")
    typer.echo("\n\n".join(blocks))
    if unmanaged:
        typer.echo(f"\n(note: {unmanaged} file(s) changed outside any Skill)")
    count = len(changes)
    typer.echo(f"\n{count} skill{'s' if count != 1 else ''} changed")


def _print_skill_diff(skills_dir: Path, skill: str) -> None:
    prefix = skill.rstrip("/") + "/"
    entries = [
        entry
        for entry in git.status_porcelain(skills_dir, skill)
        if entry.path.startswith(prefix)
    ]
    untracked = [entry for entry in entries if entry.untracked]
    tracked_diff = ""
    if git.has_commits(skills_dir):
        tracked_diff = git.diff_head(skills_dir, skill).rstrip("\n")

    if not tracked_diff and not untracked:
        typer.echo(f"{skill}\n")
        typer.echo("No changes.")
        return

    typer.echo(f"{skill}\n")
    if tracked_diff:
        typer.echo(tracked_diff)
    for entry in untracked:
        if tracked_diff:
            typer.echo()
        typer.echo(f"new file: {entry.path}")
        diff = git.diff_new_file(skills_dir, entry.path)
        typer.echo(diff.rstrip("\n"))


# ---------------------------------------------------------------------------
# remote helpers
# ---------------------------------------------------------------------------


def _require_remote(skills_dir: Path) -> str:
    """The configured remote URL, or a clean error explaining how to set up."""
    url = git.remote_url(skills_dir)
    if url is None:
        _die(
            "Error: no remote is configured.\n"
            "Set one up first:\n"
            "  skillsync remote add <url>\n"
            "  (e.g. git@github.com:you/skills.git)"
        )
    return url


def _remote_state(skills_dir: Path) -> str:
    """One-line remote state. Never raises: offline degrades gracefully."""
    try:
        git.fetch(skills_dir)
    except git.GitError:
        return "unknown (offline)"
    branch = git.current_branch(skills_dir)
    remote_ref = f"{git.REMOTE_NAME}/{branch}"
    if git.remote_branch(skills_dir, branch) is None:
        return "nothing on the remote yet (run: skillsync sync)"
    if not git.has_merge_base(skills_dir, branch, remote_ref):
        return "unrelated histories (manual setup required)"
    counts = git.ahead_behind(skills_dir, branch)
    if counts is None:
        return "unknown"
    ahead, behind = counts
    if ahead == 0 and behind == 0:
        return "up to date"
    if ahead and behind:
        return f"diverged ({ahead} local, {behind} remote) — run: skillsync sync"
    if ahead:
        return f"ahead {ahead} — run: skillsync sync"
    return f"behind {behind} — run: skillsync sync"


def _append_remote_status(skills_dir: Path) -> None:
    """Extra `status` lines shown only when a remote is configured."""
    url = git.remote_url(skills_dir)
    if url is None:
        return
    typer.echo()
    typer.echo(f"Remote: {url}")
    typer.echo(f"Remote state: {_remote_state(skills_dir)}")


def _print_private_reminder() -> None:
    typer.secho(
        "\nReminder: use a PRIVATE repository, and make sure no Skill\n"
        "contains plaintext API keys — Skills directories often do.",
        fg=typer.colors.YELLOW,
    )


def _handle_push_result(ok: bool, err: str) -> None:
    """Explain a rejected push in plain words; never suggest force-pushing."""
    if ok:
        return
    if "[rejected]" in err or "non-fast-forward" in err:
        _die(
            "Error: the remote moved while syncing (another machine pushed).\n"
            "Nothing was changed — run `skillsync sync` again."
        )
    _die(f"Error: push failed:\n{err}")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


@app.command()
def init(
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Skills directory to manage (default: auto-detect).",
    ),
    agent_key: Optional[str] = typer.Option(
        None,
        "--agent",
        help=(
            "Use this harness's Skills directory "
            f"({AGENT_KEYS_HELP}); for use when several are detected."
        ),
    ),
) -> None:
    """Detect the Agent Skills directory and initialize SkillSync."""
    _require_git()
    if agent_key is not None and agent_key not in AGENT_KEYS:
        _die(
            f"Error: unknown agent: {agent_key}\n"
            f"Known agents: {AGENT_KEYS_HELP}"
        )
    with git_errors():
        agent: Agent
        if path is not None:
            skills_dir = path.expanduser().resolve()
            agent = Agent(key="custom", name="Custom", skills_dir=skills_dir)
        elif agent_key is not None:
            agent = find_agent(agent_key)
            if agent is None:
                _die(
                    f"Error: no Skills directory found for agent: {agent_key}\n"
                    "Tried its environment variable, home directory and the\n"
                    "well-known fallback locations — or pass one explicitly:\n"
                    "  skillsync init --path /path/to/skills"
                )
            skills_dir = agent.skills_dir
        else:
            # Resolution order: --path > --agent > env var > config file >
            # auto-detect. Ambiguity is never resolved by guessing: several
            # harnesses found means the user picks one.
            resolved = load_skills_dir()
            if resolved is None:
                agents = find_agents()
                if not agents:
                    hints = search_skill_dirs()
                    if hints:
                        listing = "\n".join(f"  {hint}" for hint in hints)
                        _die(
                            "Error: could not find an Agent Skills directory.\n"
                            "\n"
                            "These directories look like Skills directories:\n"
                            f"{listing}\n"
                            "\n"
                            "Pass one explicitly:\n"
                            "  skillsync init --path /path/to/skills"
                        )
                    _die(
                        "Error: could not find an Agent Skills directory.\n"
                        "Tried the known harness locations (hermes, openclaw,\n"
                        f"claude, codex) — or pass one explicitly:\n"
                        "  skillsync init --path /path/to/skills"
                    )
                if len(agents) > 1:
                    listing = "\n".join(
                        f"  {a.key:<8} {a.name}: {_display_path(a.skills_dir)}"
                        for a in agents
                    )
                    _die(
                        "Error: several Agent Skills directories were found.\n"
                        "\n"
                        f"{listing}\n"
                        "\n"
                        "Pick one explicitly:\n"
                        "  skillsync init --agent <key>\n"
                        "  skillsync init --path /path/to/skills"
                    )
                agent = agents[0]
                skills_dir = agent.skills_dir
            else:
                skills_dir = resolved
                agent = label_agent(resolved)

        if not skills_dir.is_dir():
            _die(f"Error: Skills directory does not exist: {skills_dir}")

        typer.echo(f"{agent.name} Skills:")
        typer.echo(_display_path(skills_dir))
        skills = discover_skills(skills_dir)
        typer.echo()
        if skills:
            count = len(skills)
            typer.echo(f"Found {count} skill{'s' if count != 1 else ''}.")
        else:
            typer.echo("No skills found yet.")

        save_skills_dir(agent.key, skills_dir)

        typer.echo()
        if git.is_repo(skills_dir):
            typer.echo("A Git repository already exists here — reusing it.")
            if git.has_commits(skills_dir):
                typer.echo("Existing history preserved.")
            else:
                git.add_all(skills_dir)
                git.commit(skills_dir, "SkillSync initial snapshot")
                typer.echo("Initial snapshot created.")
            return

        typer.echo("Initializing SkillSync...")
        git.init(skills_dir)
        git.add_all(skills_dir)
        git.commit(skills_dir, "SkillSync initial snapshot")
        typer.echo("Initial snapshot created.")


@app.command()
def status() -> None:
    """Show which Skills changed since the last snapshot."""
    with git_errors():
        skills_dir = _skills_dir()
        changes, root_files = _skill_changes(skills_dir)
        _print_status(changes, root_files)
        _append_remote_status(skills_dir)


@app.command()
def diff(
    skill: Optional[str] = typer.Argument(
        None, help="Skill path relative to the Skills directory, e.g. productivity/pdf (default: all changed Skills)."
    ),
) -> None:
    """Show what changed inside a Skill."""
    with git_errors():
        skills_dir = _skills_dir()
        if skill is not None:
            if not _skill_exists(skills_dir, skill):
                _die(f"Error: unknown skill: {skill}")
            _print_skill_diff(skills_dir, skill)
            return

        changes, _ = _skill_changes(skills_dir)
        if not changes:
            typer.echo("No changes.")
            return
        for index, change in enumerate(changes):
            if index:
                typer.echo()
            _print_skill_diff(skills_dir, change.name)


@app.command()
def snapshot(
    message: Optional[str] = typer.Option(
        None, "-m", "--message", help="Snapshot message."
    ),
) -> None:
    """Save the current state of all Skills as a Git snapshot."""
    with git_errors():
        skills_dir = _skills_dir()
        entries = git.status_porcelain(skills_dir)
        if not entries:
            typer.echo("No changes to snapshot.")
            raise typer.Exit()

        changes, _ = _skill_changes(skills_dir)
        if changes:
            count = len(changes)
            typer.echo(f"{count} skill{'s' if count != 1 else ''} changed.\n")

        if message is None:
            message = f"SkillSync snapshot: {_dt.datetime.now():%Y-%m-%d %H:%M}"
        git.add_all(skills_dir)
        created = git.commit(skills_dir, message)
        if created is None:
            _die("Error: snapshot failed — nothing could be committed.")
        typer.echo(f"Snapshot created: {created}")


@app.command("log")
def log(
    skill: Optional[str] = typer.Argument(
        None, help="Skill path relative to the Skills directory, e.g. productivity/pdf (default: all Skills)."
    ),
) -> None:
    """Show snapshot history."""
    with git_errors():
        skills_dir = _skills_dir()
        if skill is not None and not _skill_exists(skills_dir, skill):
            _die(f"Error: unknown skill: {skill}")
        entries = git.log(skills_dir, pathspec=skill if skill else None)
        if not entries:
            typer.echo("No snapshots yet.")
            return
        for index, entry in enumerate(entries):
            if index:
                typer.echo()
            typer.echo(f"commit {entry.short_hash}")
            typer.echo(entry.date)
            typer.echo(entry.subject)


@app.command()
def restore(
    skill: str = typer.Argument(
        ..., help="Skill path relative to the Skills directory, e.g. productivity/pdf."
    ),
    commit_ref: Optional[str] = typer.Argument(
        None, help="Snapshot (git commit) to restore from."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Restore a Skill to a previous version."""
    with git_errors():
        skills_dir = _skills_dir()
        if not _skill_exists(skills_dir, skill):
            _die(f"Error: unknown skill: {skill}")

        dirty = bool(git.status_porcelain(skills_dir, skill))
        if commit_ref is not None:
            target = git.rev_parse(skills_dir, commit_ref)
            if target is None:
                _die(f"Error: unknown commit: {commit_ref}")
        elif dirty:
            # Uncommitted changes: go back to the last snapshot (HEAD).
            target = git.rev_parse(skills_dir, "HEAD")
        else:
            # Working tree is clean: go back to the state before the most
            # recent commit that touched this skill.
            history = git.log(skills_dir, pathspec=skill, limit=2)
            if len(history) < 2:
                _die(f"Error: no previous version to restore for skill: {skill}")
            target = history[1].hash

        short = target[:7]
        if not yes:
            typer.echo("Current changes will be replaced.\n")
            typer.echo("Previous version:")
            typer.echo(f"  commit {short}")
            if not typer.confirm(f"\nRestore {skill}?", default=False):
                typer.echo("Aborted.")
                raise typer.Exit()

        restored = git.restore_skill(skills_dir, skill, target)
        typer.echo(f"Restored {skill} to commit {short}.")
        if restored:
            typer.echo(f"Restore snapshot created: {restored} (history preserved).")


# ---------------------------------------------------------------------------
# remote commands
# ---------------------------------------------------------------------------


@remote_app.callback(invoke_without_command=True)
def remote_show(ctx: typer.Context) -> None:
    """Show the configured remote (or manage it with add/remove)."""
    if ctx.invoked_subcommand is not None:
        return
    with git_errors():
        skills_dir = _skills_dir()
        url = git.remote_url(skills_dir)
        if url is None:
            typer.echo("No remote configured.")
            typer.echo("Set one up:  skillsync remote add <url>")
            return
        typer.echo(f"Remote: {url}")
        typer.echo(f"Remote state: {_remote_state(skills_dir)}")


@remote_app.command("add")
def remote_add(
    url: str = typer.Argument(
        ..., help="Git remote URL, e.g. git@github.com:you/skills.git."
    ),
) -> None:
    """Connect this Skills repository to a (private!) remote repository.

    The URL is validated before anything is written. On a fresh remote the
    local snapshots are pushed right away as the initial backup.
    """
    _require_git()
    with git_errors():
        skills_dir = _skills_dir()
        if git.remote_url(skills_dir) is not None:
            _die(
                "Error: a remote is already configured.\n"
                "Replace it first:  skillsync remote remove"
            )
        if not git.url_is_reachable(url):
            _die(
                f"Error: could not reach: {url}\n"
                "Check the URL and your credentials "
                "(gh auth login, SSH key, or token).\n"
                "Nothing was changed."
            )
        git.remote_add(skills_dir, url)
        typer.echo(f"Remote added: {url}")

        if not git.has_commits(skills_dir):
            # No repo, or a repo with no snapshot: sync would have nothing to
            # reconcile and another machine could silently "win" the remote.
            git.remote_remove(skills_dir)
            _die(
                "Error: this Skills directory has no snapshots yet.\n"
                "Run `skillsync init` (and `skillsync snapshot`) first.\n"
                "Nothing was changed."
            )

        git.fetch(skills_dir)
        branch = git.current_branch(skills_dir)
        remote_ref = f"{git.REMOTE_NAME}/{branch}"
        if git.remote_branch(skills_dir, branch) is None:
            # Fresh remote: the initial backup is always a fast-forward.
            ok, err = git.push(skills_dir, branch)
            if not ok:
                _die(
                    f"Error: initial backup failed:\n{err}\n"
                    "The remote was kept — run `skillsync sync` once it works."
                )
            typer.echo("Initial backup pushed.")
        else:
            if not git.has_merge_base(skills_dir, branch, remote_ref):
                # Roll back: never keep a remote that `sync` cannot reconcile.
                git.remote_remove(skills_dir)
                _die(
                    "Error: this remote already holds a different history "
                    "(another machine set it up).\n"
                    f"To adopt that history here instead:\n"
                    f"  skillsync clone {url} <path>\n"
                    "Nothing was changed."
                )
            typer.echo(f"Remote state: {_remote_state(skills_dir)}")
            typer.echo("Run `skillsync sync` to reconcile local and remote.")
        _print_private_reminder()


@remote_app.command("remove")
def remote_remove() -> None:
    """Forget the configured remote (local config only)."""
    with git_errors():
        skills_dir = _skills_dir()
        if git.remote_url(skills_dir) is None:
            _die("Error: no remote is configured.")
        git.remote_remove(skills_dir)
        typer.echo(
            "Remote removed (local config only — "
            "the GitHub repository was not touched)."
        )


@app.command()
def clone(
    url: str = typer.Argument(..., help="Git remote URL to clone from."),
    path: Path = typer.Argument(..., help="Target Skills directory (must not exist or be empty)."),
) -> None:
    """Set up this machine from an existing Skills repository."""
    _require_git()
    target = path.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        _die(f"Error: target directory is not empty: {target}")
    with git_errors():
        git.clone(url, target)
        agent = label_agent(target)
        save_skills_dir(agent.key, target)
        typer.echo(f"Cloned into {_display_path(target)}")
        skills = discover_skills(target)
        if skills:
            count = len(skills)
            typer.echo(f"Found {count} skill{'s' if count != 1 else ''}.")
        else:
            typer.echo("No skills found yet.")
    _print_private_reminder()


def _handle_conflict(skills_dir: Path, branch: str, use_remote: bool) -> None:
    """Report a rebase conflict at Skill level, then resolve or abort.

    Never changes history silently: either the user asked to adopt the
    remote (--use-remote, with the abandoned snapshots pointed out), or the
    rebase is aborted and the exact pre-sync state is restored.
    """
    paths = git.conflicted_paths(skills_dir)
    roots = set(discover_skills(skills_dir)) | head_skill_roots(skills_dir)
    grouped = group_by_skill(paths, roots)
    mapped = {path for paths_ in grouped.values() for path in paths_}
    ungrouped = [path for path in paths if path not in mapped]

    if use_remote:
        # During a rebase HEAD is detached on the replay base; the branch
        # ref still points at the pre-rebase local tip.
        abandoned = git.rev_parse(skills_dir, branch)
        git.rebase_abort(skills_dir)
        git.reset_hard(skills_dir, f"{git.REMOTE_NAME}/{branch}")
        typer.echo("Adopted the remote version.")
        if abandoned:
            typer.echo(
                "Local snapshots the remote did not have were abandoned —\n"
                f"recoverable via `git reflog`, starting at {abandoned[:7]}."
            )
        return

    git.rebase_abort(skills_dir)
    typer.echo(
        "Conflict: the same Skill changed on both sides — automatic merge failed."
    )
    typer.echo()
    names = sorted(grouped)
    if names:
        label = "skill" if len(names) == 1 else "skills"
        typer.echo(f"  conflicting {label}: {', '.join(names)}")
    for path in ungrouped:
        typer.echo(f"  conflicting file (outside any Skill): {path}")
    typer.echo()
    typer.echo("Sync aborted — nothing changed locally. Your snapshots are safe.")
    typer.echo()
    typer.echo("Choose one:")
    typer.echo("  · Adopt the GitHub version:")
    typer.echo("      skillsync sync --use-remote")
    typer.echo("      (abandons ALL local snapshots the remote does not have;")
    typer.echo("       they stay recoverable via `git reflog`)")
    typer.echo("  · Keep the local version:")
    typer.echo("      SkillSync never force-pushes. If you are sure, do it manually:")
    typer.echo(f"        git push --force-with-lease {git.REMOTE_NAME} {branch}")
    raise typer.Exit(1)


def _fmt_touched(names: list[str], limit: int = 3) -> str:
    """Output suffix naming the Skills touched by a sync, e.g. `` (a, b, +1 more)``.

    Empty when no Skill was touched (changes outside every Skill root), so
    the existing single-line sync output stays intact.
    """
    if not names:
        return ""
    shown = names[:limit]
    extra = len(names) - len(shown)
    label = ", ".join(shown) + (f", +{extra} more" if extra > 0 else "")
    return f" ({label})"


@app.command()
def sync(
    use_remote: bool = typer.Option(
        False,
        "--use-remote",
        help="On conflict: adopt the remote version and abandon local-only snapshots.",
    ),
) -> None:
    """Save local changes, then pull and push snapshots with the remote."""
    _require_git()
    with git_errors():
        skills_dir = _skills_dir()
        url = _require_remote(skills_dir)
        if not git.has_commits(skills_dir):
            _die("Error: no local snapshots yet — run `skillsync snapshot` first.")

        typer.echo(f"Syncing with {url} ...")

        # 1. Never mix remote changes with unsaved local state: pre-snapshot.
        if git.status_porcelain(skills_dir):
            message = f"Pre-sync snapshot: {_dt.datetime.now():%Y-%m-%d %H:%M}"
            git.add_all(skills_dir)
            created = git.commit(skills_dir, message)
            if created:
                typer.echo(f"Pre-sync snapshot created: {created}")

        # 2. Fetch. Failure here changes nothing locally.
        try:
            git.fetch(skills_dir)
        except git.GitError as exc:
            _die(
                "Error: could not reach the remote (offline, or a credentials\n"
                f"problem). Local snapshots are safe.\n{exc}"
            )

        branch = git.current_branch(skills_dir)
        remote_ref = f"{git.REMOTE_NAME}/{branch}"

        # 3. Remote has nothing yet: the initial backup is all that is needed.
        if git.remote_branch(skills_dir, branch) is None:
            ok, err = git.push(skills_dir, branch)
            _handle_push_result(ok, err)
            typer.echo("Initial backup pushed.")
            return

        if not git.has_merge_base(skills_dir, branch, remote_ref):
            _die(
                "Error: the remote holds a different history than this machine.\n"
                "Point `skillsync remote add` at an empty repository, or adopt\n"
                f"the remote history instead:  skillsync clone {url} <path>"
            )

        ahead, behind = git.ahead_behind(skills_dir, branch) or (0, 0)

        if behind == 0 and ahead == 0:
            typer.echo("Everything up to date.")
            return
        if behind > 0 and ahead == 0:
            old_head = git.rev_parse(skills_dir, "HEAD")
            pulled = (
                changed_skills(skills_dir, old_head, remote_ref) if old_head else []
            )
            git.merge_ff_only(skills_dir, remote_ref)
            typer.echo(
                f"Pulled {behind} new snapshot{'s' if behind != 1 else ''}"
                f"{_fmt_touched(pulled)}."
            )
            return
        if behind == 0:
            pushed = changed_skills(skills_dir, remote_ref, "HEAD")
            ok, err = git.push(skills_dir, branch)
            _handle_push_result(ok, err)
            typer.echo(
                f"Pushed {ahead} snapshot{'s' if ahead != 1 else ''}"
                f"{_fmt_touched(pushed)}."
            )
            return

        # 4. Diverged: replay local snapshots on top of the remote.
        #    Both sides are resolved against the shared ancestor before the
        #    rebase rewrites local commit hashes.
        base = git.merge_base(skills_dir, branch, remote_ref)
        pulled = changed_skills(skills_dir, base, remote_ref) if base else []
        pushed = changed_skills(skills_dir, base, "HEAD") if base else []
        result = git.rebase(skills_dir, remote_ref)
        if result.ok:
            ok, err = git.push(skills_dir, branch)
            _handle_push_result(ok, err)
            typer.echo(
                f"Pulled {behind}{_fmt_touched(pulled)}, "
                f"pushed {ahead}{_fmt_touched(pushed)}."
            )
            return

        _handle_conflict(skills_dir, branch, use_remote)


if __name__ == "__main__":
    main()
