# SkillSync

> Git-based version control for Agent Skills.

AI Agents are becoming capable of creating and modifying their own Skills.

That's useful — until an Agent changes a Skill that was working well and makes it worse.

**SkillSync gives your Agent Skills a safety net.**

It detects Skill-level changes, lets you inspect what changed, saves recoverable versions, and restores a previous version when needed.

```text
Agent modifies a Skill
        ↓
   SkillSync detects it
        ↓
    Review the diff
        ↓
   Save a snapshot
        ↓
 Something goes wrong?
        ↓
   Restore previous version
```

SkillSync uses **Git as the underlying version control engine**, but presents changes in terms of Skills rather than individual files.

---

## Why SkillSync?

Git already provides excellent version control for files.

But when working with Agent Skills, you usually think in terms of:

```text
"browser-research changed"
```

not:

```text
M browser-research/SKILL.md
M browser-research/references/search.md
M browser-research/scripts/search.py
```

SkillSync understands the higher-level concept of a **Skill**.

Instead of:

```text
$ git status

modified:
  browser-research/SKILL.md
  browser-research/references/search.md
  github-pr/SKILL.md
```

You get:

```text
$ skillsync status

Skills

 M  browser-research
    2 files changed

 M  github-pr
    1 file changed

 A  deploy-k8s
    new skill

3 skills changed
```

The goal is simple:

> **If an Agent changes your Skill, you should always be able to see what happened and go back.**

---

## Features

### Skill-level status

See which Skills changed instead of dealing with a list of unrelated files.

```bash
skillsync status
```

### Skill-aware diff

Inspect exactly what changed inside a Skill.

```bash
skillsync diff browser-research
```

### Snapshots

Save the current state of your Skills as a Git commit.

```bash
skillsync snapshot -m "Agent improved research workflow"
```

### Version history

View previous Skill versions.

```bash
skillsync log browser-research
```

### Restore

Restore a Skill to a previous version.

```bash
skillsync restore browser-research
```

Or restore a specific Git commit:

```bash
skillsync restore browser-research a83f91c
```

### GitHub backup & multi-machine sync

Back up snapshots to a private GitHub repository and keep several machines
in step — see [GitHub Remote Synchronization](#github-remote-synchronization).

---

## Quick Start

> SkillSync is currently an early MVP. It auto-detects Hermes, OpenClaw,
> Claude Code and Codex Skills directories; any other directory works via
> `--path`.

### Install

Requires Python 3.12+ and git.

One-line install (creates an isolated venv and exposes the `skillsync` command):

```bash
curl -fsSL https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.sh | sh
```

On Debian/Ubuntu the installer installs `python3-venv` automatically (directly as
root, otherwise via `sudo`) when venv creation fails. Set `SKILLSYNC_NO_AUTOINSTALL=1`
to skip that and install the package by hand.

Windows (native, PowerShell):

```powershell
irm https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.ps1 | iex
```

Windows PowerShell 5.1: `iwr <same url> -UseBasicParsing | iex`. Requires Python 3.12+
and Git (the installer tells you the exact `winget` command when either is missing).
It drops a `skillsync.cmd` shim into `%USERPROFILE%\.local\bin` and adds that directory
to your user PATH — open a new terminal so it takes effect. WSL users can use the
Unix one-liner above instead.

Or install from a local checkout:

```bash
git clone https://github.com/johnsonbuilds/skillsync
cd skillsync
pip install .
```

### Initialize

Run SkillSync against your Agent's Skills:

```bash
skillsync init
```

SkillSync detects the Agent and initializes a Git repository around its Skills directory.

For example:

```text
~/.hermes/skills/
├── .git/
├── browser-research/
├── github-pr/
└── ...
```

### Check for changes

```bash
skillsync status
```

### Inspect changes

```bash
skillsync diff browser-research
```

### Save a version

```bash
skillsync snapshot -m "Save working version"
```

### Restore

If an Agent makes a Skill worse:

```bash
skillsync restore browser-research
```

Your previous version is restored without deleting the Git history.

---

## GitHub Remote Synchronization

Local snapshots protect you from bad Agent edits. A remote protects you
from a dead laptop — and keeps your Skills identical on every machine you
work from.

### Set up (once)

Create an **empty, private** GitHub repository (e.g. `you/skills`), then:

```bash
skillsync remote add git@github.com:you/skills.git
```

The URL is validated before anything is written, and your local snapshots
are pushed immediately as the initial backup.

### Daily use

```bash
skillsync sync
```

One command that does the right thing, in order:

```text
Unsaved local changes?
        ↓  automatic pre-sync snapshot (they are never mixed with remote work)
Fetch the remote
        ↓
Remote has new snapshots?  ── pull (fast-forward, or replay local on top)
        ↓
Push your new snapshots
```

### Set up a second machine

```bash
skillsync clone git@github.com:you/skills.git ~/.hermes/skills
```

Then use `skillsync` there as usual. `status` shows the remote state on
every machine:

```text
Remote: git@github.com:you/skills.git
Remote state: up to date          (or: ahead 2 / behind 1 / unknown (offline))
```

### When both machines changed the same Skill

Git merges different Skills automatically. Only when **the same Skill**
changed on both sides does `sync` stop and ask you to choose:

```text
Conflict: the same Skill changed on both sides — automatic merge failed.

  conflicting skill: productivity/pdf

Sync aborted — nothing changed locally. Your snapshots are safe.

Choose one:
  · Adopt the GitHub version:  skillsync sync --use-remote
  · Keep the local version:    manual git push --force-with-lease (rare)
```

SkillSync **never force-pushes** and never picks a winner on its own.

### Authentication

SkillSync adds no auth layer of its own — git's credentials are used as-is:

| Setup | Works via |
|---|---|
| GitHub CLI | `gh auth login` (git picks up its credential helper) |
| SSH | `ssh-keygen` + add key to GitHub, use `git@github.com:...` URLs |
| Token | Personal access token over HTTPS (credential manager or `git-credential-store`) |

If `remote add` reports `could not reach`, finish one of the setups above first.

> **Two things to check before your first push:** the repository must be
> **private**, and Skills directories often contain plaintext API keys —
> remove them or move them to environment variables first.

---

## CLI

The command surface stays deliberately small:

```bash
skillsync init

skillsync status          # shows remote state too, once a remote is set

skillsync diff [skill]

skillsync snapshot [-m "message"]

skillsync log [skill]

skillsync restore <skill> [commit]

skillsync remote [add <url> | remove]

skillsync clone <url> <path>

skillsync sync [--use-remote]
```

That's it.

SkillSync is not trying to replace Git.

It adds a Skill-aware layer on top of Git — and a safety-first sync layer
on top of `git push`.

---

## How It Works

SkillSync uses Git for the actual version control.

```text
                 SkillSync
                     │
          ┌──────────┴──────────┐
          │                     │
     Skill-aware layer       Git
          │                     │
     ┌────┼────┐          ┌─────┼─────┐
     │    │    │          │     │     │
   status diff restore   commit  diff  history
```

A Skill is treated as a logical unit:

```text
browser-research/
├── SKILL.md
├── references/
└── scripts/
```

If any files inside the directory change, SkillSync reports the change as:

```text
M browser-research
```

Git remains responsible for storing the actual history.

---

## Design Principles

### Local-first

Your Skills stay on your machine.

No cloud service is required — the GitHub remote is optional, and every
local command works fully offline.

### Git-native

SkillSync does not implement another version control system.

Git provides the underlying:

* commits
* diffs
* history
* restore

### Skill-first

Users think about Skills.

SkillSync presents changes at the Skill level.

### Safe by default

Restoring a Skill should never silently destroy history.

### Minimal

The project focuses on one problem:

> **Protect Agent Skills from bad changes.**

---

## Supported Agents

SkillSync is harness-agnostic: it versions **any** directory of Skills.
Built-in adapters locate each harness's Skills directory:

| Agent | Skills directory (priority order) |
|---|---|
| Hermes Agent | `$HERMES_HOME/skills` → `~/.hermes/skills` → `/opt/.hermes/skills` → `/opt/data/.hermes/skills` → `/usr/local/.hermes/skills` |
| OpenClaw | `$OPENCLAW_STATE_DIR/skills` → `~/.openclaw/skills` |
| Claude Code | `~/.claude/skills` |
| Codex | `~/.codex/skills` → `/etc/codex/skills` |

Any other directory works with `skillsync init --path`.

Skills are discovered by the same rule everywhere: **a directory that
directly contains a `SKILL.md` file**, at any depth. A Skill is identified
by its path relative to the Skills directory — for example
`browser-research` in a flat layout, or `productivity/pdf` when the
harness groups Skills into categories. Flat and nested layouts work
equally well.

When several harnesses are detected, `init` lists the candidates and asks
you to pick one with `--agent <key>` or `--path` — it never guesses.

---

## Project Status

**Early MVP / Experimental**

The project is currently being built to validate one core workflow:

```text
Agent modifies Skill
        ↓
SkillSync detects change
        ↓
User reviews diff
        ↓
User saves a version
        ↓
Agent makes a bad change
        ↓
User restores previous version
```

The priority is real-world usage over feature completeness.

---

## Roadmap

### MVP

* [x] Product definition
* [x] Skills-directory adapters (Hermes, OpenClaw, Claude Code, Codex)
* [x] Layout-agnostic Skill discovery (flat and category-nested)
* [x] `skillsync init` (with `--path` / `--agent` selection)
* [x] Skill-level `status`
* [x] Skill-aware `diff`
* [x] `snapshot`
* [x] `log`
* [x] `restore`

### v0.3 — Remote synchronization

* [x] `skillsync remote add/remove` (URL validation, initial backup push)
* [x] `skillsync sync` (pre-sync snapshot → fetch → rebase → push)
* [x] `skillsync clone <url> <path>` (second-machine setup)
* [x] `status` remote state (ahead/behind, offline-safe)
* [x] Conflict policy: abort + skill-level report + explicit `--use-remote`
* [x] Safety rules: never force-push, timeouts, offline never touches local state

### Later

Potential future work includes:

* `remote add --create` (create the private GitHub repo via `gh` CLI)
* Better CLI UX
* Optional Web/Desktop UI

The following are intentionally **not part of the current roadmap**:

* Skill marketplace
* Skill discovery
* Skill sharing platform
* Team collaboration
* Enterprise management

---

## Development

Run the test suite from a local checkout:

```bash
pip install -e .[dev]
pytest
```

## Contributing

The project is in an early stage and the design may change as the MVP is tested with real Agent workflows.

Issues, feedback, and pull requests are welcome.


