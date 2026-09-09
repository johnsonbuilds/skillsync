# SkillSync -- Agent Guide

## Rule: Human Confirmation Required

**Before executing ANY skillsync command, you MUST ask the user for confirmation.**

- Never run `skillsync` commands automatically or silently.
- Always explain what the command will do and why, then wait for explicit approval.
- This applies to every command: `init`, `snapshot`, `restore`, `sync`, `remote add`, etc.
- Violating this rule can cause data loss. Treat skillsync operations with the same caution as file deletions.

## What Is SkillSync

SkillSync is a Git-based version control tool for AI Agent Skills. It lets you track, review, save, and restore entire Skills without interacting with Git directly.

**Core value:** If you modify a Skill and it gets worse, you can easily restore a previous working version.

## Install

```bash
# Unix / macOS
curl -sSL https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.sh | bash

# Or via pip (requires Python 3.12+)
pip install skillsync
```

After install, initialize:

```bash
skillsync init
```

This auto-detects your agent harness and skills directory.

## Daily Workflow

### Check for changes

```bash
skillsync status        # which Skills changed
skillsync diff          # what exactly changed
```

### Save a snapshot

```bash
skillsync snapshot -m "describe what you did"
```

### View history

```bash
skillsync log                    # all snapshots
skillsync log browser-research   # history for one Skill
```

### Restore a Skill

```bash
skillsync restore <skill-name>                  # restore to last snapshot
skillsync restore <skill-name> <commit-hash>    # restore to a specific version
```

## Multi-Machine Sync

### Set up remote (first machine)

```bash
skillsync remote add https://github.com/youruser/skills-backup.git
```

### Clone to a second machine

```bash
skillsync clone https://github.com/youruser/skills-backup.git /path/to/skills
```

### Sync

```bash
skillsync sync
```

`sync` automatically: snapshots locally → fetches remote → merges/rebases → pushes.

On conflict:

```bash
skillsync sync --use-remote    # accept remote version (discards unsynced local changes)
```

## Key Concepts

- **Skill**: A directory containing a `SKILL.md` file. This is the basic unit SkillSync manages.
- **Snapshot**: A Git commit that captures the state of all Skills.
- **Pre-sync Snapshot**: An automatic snapshot created before `sync` to protect unsaved local work.

## Command Reference

| Command | Description |
|---|---|
| `skillsync install` | Install SkillSync |
| `skillsync init` | Initialize for your agent environment |
| `skillsync status` | Show changed Skills |
| `skillsync diff [skill]` | Show diff for a Skill |
| `skillsync snapshot -m "msg"` | Save a snapshot |
| `skillsync log [skill]` | View snapshot history |
| `skillsync restore <skill> [commit]` | Restore a Skill |
| `skillsync remote add <url>` | Add a remote repository |
| `skillsync remote` | Show remote config |
| `skillsync sync` | Sync across machines |
| `skillsync clone <url> <path>` | Clone to a new machine |

## Safety Notes

- SkillSync never force-pushes. History is always safe.
- Restore creates a new commit; existing history is never deleted.
- Network commands have timeout protection (fetch 10s, push 120s, clone 300s).
- Git must be installed on the system. SkillSync uses it via subprocess.
