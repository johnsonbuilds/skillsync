---
name: skillsync
description: Git-based version control for AI Agent Skills — detect, review, save, and restore Skill changes.
version: 0.3.1
author: johnsonbuilds
homepage: https://github.com/johnsonbuilds/skillsync
metadata:
  openclaw:
    requires:
      bins:
        - git
        - skillsync
    envVars:
      - name: SKILLSYNC_SKILLS_DIR
        required: false
        description: Override the auto-detected Skills directory path.
---

# SkillSync

Version control for Agent Skills. SkillSync wraps Git to let you track, diff, snapshot, and restore entire Skills — not individual files.

## Rule: Human Confirmation Required

Before executing ANY `skillsync` command, you MUST ask the user for confirmation.

- Never run `skillsync` commands automatically or silently.
- Always explain what the command will do and why, then wait for explicit approval.
- This applies to every command: `init`, `snapshot`, `restore`, `sync`, `remote add`, etc.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.sh | sh
```

Or via pip (requires Python 3.12+):

```bash
pip install skillsync
```

After install, initialize:

```bash
skillsync init
```

This auto-detects your agent harness and Skills directory.

## Commands

### Check for changes

```bash
skillsync status        # which Skills changed
skillsync diff          # what exactly changed
skillsync diff <skill>  # diff for a specific Skill
```

### Save a snapshot

```bash
skillsync snapshot -m "describe what you did"
```

### View history

```bash
skillsync log                    # all snapshots
skillsync log <skill>            # history for one Skill
```

### Restore a Skill

```bash
skillsync restore <skill>                  # restore to last snapshot
skillsync restore <skill> <commit-hash>    # restore to a specific version
```

### Multi-machine sync

```bash
skillsync remote add <url>     # set up remote (first machine)
skillsync clone <url> <path>   # clone to a second machine
skillsync sync                 # sync across machines
skillsync sync --use-remote    # on conflict, accept remote version
```

## Key Concepts

- **Skill**: A directory containing a `SKILL.md` file. SkillSync's basic unit of management.
- **Snapshot**: A Git commit capturing the state of all Skills.
- **Pre-sync Snapshot**: Auto-created before `sync` to protect unsaved local work.

## Safety

- Never force-pushes. History is always safe.
- Restore creates a new commit; existing history is never deleted.
- Network commands have timeout protection (fetch 10s, push 120s, clone 300s).
