# SkillSync Functional Design

## 1. Scope

This document defines the minimum implementation required for the SkillSync MVP.

The MVP is intentionally small.

The core workflow is:

```text
Discover Skills
      ↓
Initialize Git
      ↓
Detect changes
      ↓
Show Skill-level diff
      ↓
Create snapshot
      ↓
Restore previous version
```

Git is the underlying version control system.

SkillSync provides the Skill-aware layer.

---

# 2. Supported Agent

## MVP

Support **Hermes Agent only**.

The adapter should locate the Hermes Skill directory.

Expected location:

```text
~/.hermes/skills/
```

The implementation should isolate this path behind a simple Agent adapter so OpenClaw can be added later.

No generalized plugin system is required for MVP.

---

# 3. Skill Model

A Skill is a directory containing an Agent Skill.

Example:

```text
browser-research/
├── SKILL.md
├── references/
│   └── search.md
└── scripts/
    └── search.py
```

SkillSync treats the entire directory as one logical unit.

For example:

```text
browser-research
```

may contain:

```text
SKILL.md
references/search.md
scripts/search.py
```

Changes to any of these files are reported as changes to:

```text
browser-research
```

---

# 4. Repository Layout

SkillSync should create a Git repository around the Agent's Skill directory.

For Hermes:

```text
~/.hermes/skills/
├── .git/
├── browser-research/
├── github-pr/
└── ...
```

This is intentionally simple.

There is no separate SkillSync storage database.

Git metadata lives directly alongside the Skills.

---

# 5. `skillsync init`

Command:

```bash
skillsync init
```

Behavior:

1. Detect Hermes.
2. Locate its Skill directory.
3. Verify that the directory exists.
4. Initialize a Git repository if one does not exist.
5. Create the initial Skill snapshot.

Example:

```text
$ skillsync init

Hermes Skills:
~/.hermes/skills

Found 12 skills.

Initializing SkillSync...
Initial snapshot created.
```

If Git is already initialized, SkillSync must reuse the existing repository.

It must not overwrite existing Git history.

---

# 6. `skillsync status`

Command:

```bash
skillsync status
```

The command compares the current filesystem state against the latest SkillSync snapshot.

Output should be Skill-centric.

Example:

```text
Skills

 M  browser-research
    2 files changed

 M  github-pr
    1 file changed

 A  deploy-k8s
    new skill

 D  old-deploy

4 skills changed
```

### Status meanings

```text
M  Modified
A  Added
D  Deleted
```

The MVP does not need additional Git states.

---

# 7. Skill-Level Grouping

This is one of the core differentiators of SkillSync.

Given:

```text
browser-research/SKILL.md
browser-research/references/search.md
browser-research/scripts/search.py
```

Git may report:

```text
M browser-research/SKILL.md
M browser-research/references/search.md
M browser-research/scripts/search.py
```

SkillSync should report:

```text
M browser-research
  3 files changed
```

The user thinks in terms of Skills, not files.

---

# 8. `skillsync diff`

Command:

```bash
skillsync diff
```

Show all Skill changes.

Example:

```text
browser-research

 SKILL.md

- Always search...
+ Search when information may be outdated.

 references/search.md

+ Added search result filtering.
```

The command may accept an optional Skill name:

```bash
skillsync diff browser-research
```

This shows only that Skill.

The implementation can internally use Git diff.

---

# 9. `skillsync snapshot`

Command:

```bash
skillsync snapshot
```

Purpose:

> Save the current state of all Skills as a recoverable version.

The implementation creates a normal Git commit.

Example:

```text
$ skillsync snapshot

2 skills changed.

Snapshot message:
Agent updated research workflow

Snapshot created.
```

For MVP, the user may provide a message:

```bash
skillsync snapshot -m "Agent updated research workflow"
```

If no message is provided, SkillSync may generate a simple default message.

Example:

```text
SkillSync snapshot: 2026-09-04 14:32
```

---

# 10. Snapshot Semantics

A snapshot records the entire current repository state.

However, SkillSync presents changes to the user at the Skill level.

Example:

```text
Snapshot
├── browser-research
├── github-pr
└── deploy-k8s
```

Git remains responsible for the actual commit.

SkillSync does not create a separate version database.

---

# 11. `skillsync restore`

Command:

```bash
skillsync restore browser-research
```

Default behavior:

> Restore the Skill to the immediately previous committed version.

The user should receive confirmation:

```text
Restore browser-research?

Current changes will be replaced.

Previous version:
  commit a83f91c

[y/N]
```

After confirmation, SkillSync restores the Skill.

---

# 12. Restore Specific Version

Optional MVP syntax:

```bash
skillsync restore browser-research <commit>
```

Example:

```bash
skillsync restore browser-research a83f91c
```

The commit may be supplied by:

```bash
skillsync log
```

If implementing version aliases such as `v1`, `v2`, etc. adds complexity, do not implement them in MVP.

Git commit IDs are sufficient.

---

# 13. Restore Must Preserve History

Restore must not delete historical commits.

Example:

```text
A → B → C
        ↓
     restore B
        ↓
A → B → C → D
```

`D` represents the restored state.

This means the user can always recover the previous state if the restore itself was incorrect.

---

# 14. Minimal `log`

A full history UI is not required for MVP.

The restore workflow needs a way to identify previous commits.

Therefore implement:

```bash
skillsync log
```

Output may simply wrap:

```text
commit a83f91c
2026-09-04
Agent updated research workflow

commit 72b19ab
2026-09-03
Initial snapshot
```

Optional Skill filtering:

```bash
skillsync log browser-research
```

The implementation can derive this information from Git history.

---

# 15. Git Commands

SkillSync should internally rely on standard Git operations where possible.

Conceptually:

```text
status   → git status / git diff
diff     → git diff
snapshot → git add + git commit
log      → git log
restore  → git restore / checkout + commit
```

SkillSync must not implement its own version storage.

---

# 16. Safety Requirements

SkillSync must follow these rules:

### Never silently overwrite

Restore requires explicit confirmation.

### Never delete history

Restore creates a new Git state.

### Never modify unmanaged locations

Only the configured Agent Skill directory is managed.

### Never upload anything

MVP has no network functionality.

### Existing Git repositories

If the Skill directory already contains a Git repository:

* do not delete it
* do not rewrite history
* warn the user
* reuse it only when safe

If supporting existing repositories creates ambiguity, `skillsync init` should fail safely and explain the situation rather than making assumptions.

---

# 17. Minimal Configuration

MVP should avoid a complex configuration system.

The Skill directory can be stored in a small local configuration file if necessary.

Example:

```text
.skillsync/
```

or:

```text
.skillsync.json
```

The exact format is an implementation detail.

No cloud configuration is required.

---

# 18. CLI Summary

The MVP CLI is intentionally limited to:

```bash
skillsync init

skillsync status

skillsync diff [skill]

skillsync snapshot [-m "message"]

skillsync log [skill]

skillsync restore <skill> [commit]
```

That is the complete MVP command surface.

Do not add additional commands unless required to make this workflow usable.

---

# 19. MVP End-to-End Test

The implementation must pass this real-world scenario:

### Step 1

User has:

```text
~/.hermes/skills/browser-research/
```

### Step 2

Run:

```bash
skillsync init
```

### Step 3

Verify:

```bash
skillsync status
```

Output:

```text
No changes.
```

### Step 4

Let Hermes modify:

```text
browser-research/SKILL.md
```

### Step 5

Run:

```bash
skillsync status
```

Expected:

```text
M browser-research
```

### Step 6

Run:

```bash
skillsync diff browser-research
```

Verify the actual Agent changes.

### Step 7

Create a snapshot:

```bash
skillsync snapshot -m "Agent modified browser research"
```

### Step 8

Intentionally make the Skill worse.

### Step 9

Run:

```bash
skillsync status
```

Verify that SkillSync detects the modification.

### Step 10

Run:

```bash
skillsync restore browser-research
```

Verify that the Skill returns to the previous known state.

### Step 11

Run:

```bash
skillsync status
```

Expected:

```text
No changes.
```

If this complete workflow works reliably, the MVP has achieved its primary goal.

---

# 20. Implementation Constraint

The first implementation should optimize for:

> **Working today, not architectural completeness.**

Avoid:

* unnecessary abstractions
* database layers
* background services
* web servers
* authentication systems
* plugin frameworks
* complex configuration
* premature multi-agent architecture

The first implementation should be small enough that a developer can inspect the entire codebase and understand how SkillSync works.

The product should earn the right to become more complex only after real usage validates the core workflow.
