# SkillSync

> Git for Agent Skills

## 1. Product Definition

SkillSync is a lightweight, local-first version control tool for Agent Skills.

Its primary purpose is to protect Skills from unwanted changes made by AI Agents.

Modern Agents can create and modify their own Skills. A Skill may become better over time, but an Agent may also accidentally make a previously useful Skill worse.

SkillSync provides a simple safety net:

```text
Agent modifies Skill
        ↓
SkillSync detects the change
        ↓
A new version is preserved
        ↓
User can inspect the diff
        ↓
User can restore a previous version
```

Git is used as the underlying version control engine.

SkillSync adds an Agent/Skill-aware user experience on top of Git.

---

## 2. The Problem

An Agent Skill is persistent behavior.

For example:

```text
browser-research/
├── SKILL.md
├── references/
└── scripts/
```

An Agent may modify any of these files while improving the Skill.

The problem is not that the files cannot be versioned.

Git can already version them.

The problem is that Git operates primarily at the file/repository level, while users think about:

> "My `browser-research` Skill changed."

The user needs to quickly answer:

1. Which Skills changed?
2. What changed inside the Skill?
3. What was the previous working version?
4. Can I safely restore it?

SkillSync exists to make these operations Skill-centric.

---

## 3. Core User Scenario

The primary MVP scenario is a Hermes Agent user.

The user has:

```text
~/.hermes/skills/browser-research/
```

The Skill works well.

The Agent later modifies it.

The user runs:

```bash
skillsync status
```

and sees:

```text
Skills

 M  browser-research
    2 files changed

1 skill changed
```

The user runs:

```bash
skillsync diff browser-research
```

and reviews the changes.

If the changes are bad:

```bash
skillsync restore browser-research
```

The Skill returns to the previous version.

This is the entire MVP value proposition.

---

## 4. Product Principles

### 4.1 Skill-first

The primary unit presented to users is a Skill, not an individual Git file.

### 4.2 Local-first

Skills remain on the user's machine.

SkillSync does not require a cloud service.

### 4.3 Git-native

Git provides:

* version storage
* history
* diff
* restore
* commits

SkillSync should reuse Git instead of implementing its own version control system.

### 4.4 Minimal

SkillSync should solve one problem extremely well before adding additional functionality.

### 4.5 Safe

SkillSync must never silently destroy a user's Skill.

Restore operations must preserve the previous state in Git history.

### 4.6 Agent-agnostic

The initial implementation should support Hermes first, while keeping the architecture simple enough to support OpenClaw later.

---

## 5. Target Users

Initial target:

> Developers and power users who use AI Agents that can modify Agent Skills.

Initial validation environment:

* Hermes Agent
* filesystem-based Agent Skills
* Git
* local machine

OpenClaw support should be added immediately after the Hermes validation if the adapter model remains trivial.

---

## 6. MVP

The MVP contains only five user-facing capabilities:

### 1. Initialize

```bash
skillsync init
```

Find the Agent's Skill directory and initialize SkillSync.

### 2. Status

```bash
skillsync status
```

Show changed Skills at the Skill level.

### 3. Diff

```bash
skillsync diff [skill]
```

Show what changed inside a Skill.

### 4. Snapshot

```bash
skillsync snapshot
```

Save the current Skill state as a Git version.

### 5. Restore

```bash
skillsync restore <skill> [version]
```

Restore a Skill to a previous version.

These five capabilities are sufficient to validate the core product.

---

## 7. MVP Explicitly Excludes

Do not implement the following during the initial validation:

* Web UI
* GitHub integration
* GitHub OAuth
* Remote synchronization
* Skill marketplace
* Skill discovery
* Skill sharing
* Team collaboration
* Skill analytics
* Skill quality evaluation
* AI-based change evaluation
* Skill dependencies
* Skill compatibility management
* Automatic background daemon
* Complex configuration
* Multi-repository management

GitHub support can be added after the local workflow is proven.

---

## 8. Validation Goal

The MVP succeeds if the developer can use Hermes normally and trust SkillSync as a safety net.

The key test is:

```text
Good Skill
    ↓
Agent modifies Skill
    ↓
SkillSync detects change
    ↓
User sees Skill-level diff
    ↓
User decides change is bad
    ↓
One command restores previous version
    ↓
Skill works again
```

If this workflow feels significantly better than manually using Git, SkillSync has a reason to exist.

If it does not, the product hypothesis should be reconsidered before adding features.

---

## 9. Product Direction After MVP

Only after the MVP is validated should SkillSync add:

### Phase 2

* OpenClaw support
* GitHub remote support
* push / pull
* multi-machine recovery
* better CLI UX
* optional Web/Desktop UI
* GitHub authentication

The product should remain focused on Skill version control and protection.

Marketplace, Skill discovery, Skill sharing, and team collaboration are outside the current product direction.
