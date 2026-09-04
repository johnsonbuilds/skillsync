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

---

## Quick Start

> SkillSync is currently an early MVP. Hermes Agent is the first supported Agent environment.

### Install

Requires Python 3.12+ and git.

One-line install (creates an isolated venv and exposes the `skillsync` command):

```bash
curl -fsSL https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.sh | sh
```

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

## CLI

The MVP intentionally has a very small command surface:

```bash
skillsync init

skillsync status

skillsync diff [skill]

skillsync snapshot [-m "message"]

skillsync log [skill]

skillsync restore <skill> [commit]
```

That's it.

SkillSync is not trying to replace Git.

It adds a Skill-aware layer on top of Git.

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

No cloud service is required.

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

### Currently

* [x] Hermes Agent
* [ ] OpenClaw

OpenClaw support is planned after the initial Hermes validation.

The architecture should remain simple and Agent-agnostic.

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
* [x] Hermes Skill detection
* [x] `skillsync init`
* [x] Skill-level `status`
* [x] Skill-aware `diff`
* [x] `snapshot`
* [x] `log`
* [x] `restore`

### Later

Potential future work includes:

* OpenClaw support
* GitHub remote synchronization
* Multi-machine recovery
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


