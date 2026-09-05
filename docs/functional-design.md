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

SkillSync is harness-agnostic. Each harness contributes only one thing:
the candidates for its Skills directory, in priority order.

## Harness adapters

| Agent | Candidates (priority order) |
|---|---|
| Hermes | `$HERMES_HOME/skills` → `~/.hermes/skills` → `/opt/.hermes/skills` → `/opt/data/.hermes/skills` → `/usr/local/.hermes/skills` |
| OpenClaw | `$OPENCLAW_STATE_DIR/skills` → `~/.openclaw/skills` |
| Claude Code | `~/.claude/skills` |
| Codex | `~/.codex/skills` → `/etc/codex/skills` |

Adding a harness means adding one adapter entry.

## Resolution priority

```text
init --path (explicit)
      ↓
init --agent <key> (explicit harness choice)
      ↓
$SKILLSYNC_SKILLS_DIR (SkillSync override)
      ↓
last init (config file)
      ↓
auto-detect across all harnesses
      ↓
bounded search for "skills" / "optional-skills" directories (hint only, user must pass --path)
```

Auto-detect never guesses: when several harnesses are found, init lists
them and exits, asking the user to pick one with `--agent` or `--path`.

The search is depth-limited, skips hidden and dependency directories, and
only ever presents candidates: SkillSync never picks a searched directory
automatically.

No generalized plugin system is required.

---

# 3. Skill Model

A Skill is a directory that **directly contains a `SKILL.md` file**, at any
depth below the Skills directory.

Flat layout:

```text
skills/
└── browser-research/
    ├── SKILL.md
    ├── references/
    │   └── search.md
    └── scripts/
        └── search.py
```

Category-nested layout:

```text
skills/
└── productivity/
    └── pdf/
        ├── SKILL.md
        └── scripts/
            └── run.py
```

Discovery walks the tree; a directory containing `SKILL.md` is a Skill and
is not descended into (nested `SKILL.md` files belong to that Skill's
payload). Directories without `SKILL.md` — category docs, caches,
dependency trees — are never Skills.

A Skill is identified by its path relative to the Skills directory
(e.g. `browser-research`, `productivity/pdf`). This identity is unique
regardless of how the harness organizes its Skills directory, and doubles
as the git pathspec for diff/log/restore.

Changes to any file inside the Skill directory are reported as changes to
its Skill identity:

```text
 M  productivity/pdf
```

Skills present in the last snapshot (HEAD) but deleted from the working
tree are still grouped and reported as deleted.

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

---

# 21. Addendum — Remote Synchronization (v0.3)

## 21.1 Scope

One workflow: **back up local snapshots to a private GitHub repository and
keep two or more machines in step.** Everything else (auto repo creation,
merge strategies, branch management) is out of scope.

The remote is optional. Every local command keeps working offline, and a
network failure must never change local state.

## 21.2 Commands

| Command | Behavior |
|---|---|
| `remote add <url>` | Validate the URL with `git ls-remote` first (nothing is written on failure). Require an initialized repository with at least one snapshot. Refuse a second remote. On a fresh remote, push the local history as the initial backup. If the remote already holds **unrelated history**, roll the remote configuration back and explain `clone` as the alternative. |
| `remote` / `remote remove` | Show or forget `origin` (local config only; GitHub is untouched). |
| `clone <url> <path>` | Set up a machine from an existing repository: `git clone`, register the Skills directory, report the number of Skills found. Target must not exist or be empty. |
| `sync [--use-remote]` | The daily verb — see 21.3. |
| `status` (enhanced) | When a remote is configured, append `Remote:` and `Remote state:` lines. Fetch uses a 10 s budget; failure degrades to `unknown (offline)`, never an error. |

## 21.3 The `sync` algorithm

```text
1. Working tree dirty?          → automatic "Pre-sync snapshot: <date>"
                                  (remote work is never mixed with unsaved state)
2. fetch origin                 → unreachable: die; local state untouched
3. remote branch missing?       → push -u (initial backup) and stop
4. unrelated histories?         → die with guidance (clone or empty remote)
5. ahead / behind:
     equal                      → "Everything up to date."
     behind only                → merge --ff-only, report pulled count
     ahead only                 → push, report pushed count
     diverged                   → rebase (replay local snapshots onto remote)
           success              → push, "Pulled N, pushed M"
           conflict             → 21.4
6. push rejected (remote raced) → "run skillsync sync again"; nothing changed

Each pulled/pushed count is followed by the touched Skill names, capped at
three ("Pulled 1 new snapshot (browser-research).", "Pushed 1 snapshot
(agent-memory, browser-research, github-pr, +1 more).", "Pulled 1 (a),
pushed 1 (b)."). Changes outside every Skill root are not named; the
parenthesis is omitted when no Skill was touched.
```

Pulls and pushes are plain git operations; SkillSync never rewrites the
remote and never force-pushes.

## 21.4 Conflict policy

When the same Skill changed on both sides, `sync` aborts the rebase
(`git rebase --abort`) and restores the exact pre-sync state, then reports:

* the conflicting **Skills** (file paths grouped via the Skill model), plus
  any conflicted files outside any Skill;
* the two available choices:
  * adopt the remote version: `sync --use-remote`
    (aborts the rebase, `git reset --hard origin/main`; the abandoned local
    snapshots remain recoverable and their starting hash is printed);
  * keep the local version: manual `git push --force-with-lease`
    (SkillSync refuses to do this itself).

Automatic winner-picking is deliberately excluded: silently discarding one
side's work is unacceptable in a backup tool. Different Skills merging
cleanly is the common case and stays fully automatic.

## 21.5 Safety rules

* Never force-push; there is no force wrapper in the git layer at all.
* All network commands run with `GIT_TERMINAL_PROMPT=0` and subprocess
  timeouts (fetch 10 s, push 120 s, clone 300 s, ls-remote 15 s) so an
  unreachable remote fails cleanly instead of hanging.
* `remote add` refuses repositories without snapshots: an uninitialized
  directory must not silently "reserve" a remote that another machine's
  initial backup would then miss.
* Every push path reminds the user: keep the repository **private**, and
  audit Skills for plaintext API keys.
* Authentication is git's own (gh credential helper, SSH keys, tokens);
  SkillSync adds none.

## 21.6 Testing

GitHub is simulated with a local bare repository over `file://`, which
exercises the real git transport. Covered: URL validation failure, initial
backup, second-remote refusal, unrelated-history rollback, remote remove,
`remote` display, pre-sync snapshot, two-machine round-trip (clone, edit,
push, pull), conflict abort and `--use-remote` recovery, offline `sync`
(local state intact) and offline `status` (degrades gracefully), clone into
a non-empty target.
