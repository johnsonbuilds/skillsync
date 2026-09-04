"""SkillSync command line interface.

Six commands, exactly the MVP surface:

    skillsync init
    skillsync status
    skillsync diff [skill]
    skillsync snapshot [-m "message"]
    skillsync log [skill]
    skillsync restore <skill> [commit]
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
    discover_skills,
    group_by_skill,
    head_skill_roots,
)

app = typer.Typer(
    help="Git-based version control for Agent Skills.",
    no_args_is_help=True,
    add_completion=False,
)


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


if __name__ == "__main__":
    main()
