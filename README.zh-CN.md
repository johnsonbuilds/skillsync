# SkillSync

[English](./README.md) | **简体中文**

> 基于 Git 的 Agent Skills 版本控制。

AI Agent 已经有能力创建和修改它们自己的 Skills。

这很有用——直到某个 Agent 改动了一个原本运行良好的 Skill，把它变糟。

**SkillSync 为你的 Agent Skills 提供一张安全网。**

它能检测 Skill 级别的变更，让你检查具体改了什么，保存可恢复的版本，并在需要时恢复到之前的版本。

```text
Agent 修改了某个 Skill
        ↓
   SkillSync 检测到变更
        ↓
    查看差异
        ↓
   保存快照
        ↓
   出了问题？
        ↓
   恢复之前的版本
```

SkillSync 使用 **Git 作为底层版本控制引擎**，但以 Skill 而非单个文件为单位呈现变更。

---

## 为什么需要 SkillSync？

Git 已经为文件提供了出色的版本控制。

但在处理 Agent Skills 时，你脑子里想的通常是：

```text
"browser-research 变了"
```

而不是：

```text
M browser-research/SKILL.md
M browser-research/references/search.md
M browser-research/scripts/search.py
```

SkillSync 理解 **Skill** 这个更高层的概念。

不再是：

```text
$ git status

modified:
  browser-research/SKILL.md
  browser-research/references/search.md
  github-pr/SKILL.md
```

而是：

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

目标很简单：

> **如果 Agent 改动了你的 Skill，你永远都能看清发生了什么、并退得回去。**

---

## 功能

### Skill 级别状态

一眼看出哪些 Skills 变了，不必面对一堆互不相关的文件。

```bash
skillsync status
```

### Skill 感知的 diff

精确查看一个 Skill 内部改了什么。

```bash
skillsync diff browser-research
```

### 快照

把 Skills 的当前状态保存为一个 Git commit。

```bash
skillsync snapshot -m "Agent improved research workflow"
```

### 版本历史

查看某个 Skill 的历史版本。

```bash
skillsync log browser-research
```

### 恢复

把一个 Skill 恢复到之前的版本。

```bash
skillsync restore browser-research
```

也可以恢复到指定的 Git commit：

```bash
skillsync restore browser-research a83f91c
```

### GitHub 备份与多机同步

把快照备份到私有 GitHub 仓库，让多台机器保持一致——见
[GitHub 远程同步](#github-远程同步)。

---

## 快速开始

> SkillSync 目前是早期 MVP。它会自动检测 Hermes、OpenClaw、Claude Code
> 和 Codex 的 Skills 目录；其他任何目录都可以通过 `--path` 使用。

### 安装

需要 Python 3.12+ 和 git。

一行命令安装（创建隔离的 venv 并暴露 `skillsync` 命令）：

```bash
curl -fsSL https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.sh | sh
```

在 Debian/Ubuntu 上，创建 venv 失败时，安装脚本会自动安装 `python3-venv`
（有 root 权限就直接装，否则通过 `sudo`）。设置 `SKILLSYNC_NO_AUTOINSTALL=1`
可以跳过这一步、手动安装依赖。

Windows（原生，PowerShell）：

```powershell
irm https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.ps1 | iex
```

Windows PowerShell 5.1：`iwr <同一 URL> -UseBasicParsing | iex`。需要
Python 3.12+ 和 Git（缺哪个，安装脚本都会给出确切的 `winget` 命令）。它会把一个
`skillsync.cmd` shim 放进 `%USERPROFILE%\.local\bin`，并把该目录加入你的用户
PATH——新开一个终端即可生效。WSL 用户可以直接用上面的 Unix 一行命令。

也可以从本地检出的源码安装：

```bash
git clone https://github.com/johnsonbuilds/skillsync
cd skillsync
pip install .
```

### 初始化

对你的 Agent Skills 运行 SkillSync：

```bash
skillsync init
```

SkillSync 会检测 Agent，并围绕其 Skills 目录初始化一个 Git 仓库。

例如：

```text
~/.hermes/skills/
├── .git/
├── browser-research/
├── github-pr/
└── ...
```

### 检查变更

```bash
skillsync status
```

### 查看变更

```bash
skillsync diff browser-research
```

### 保存版本

```bash
skillsync snapshot -m "Save working version"
```

### 恢复

如果 Agent 把某个 Skill 改坏了：

```bash
skillsync restore browser-research
```

你之前的版本会被恢复，且不会删除 Git 历史。

---

## GitHub 远程同步

本地快照保护你免受 Agent 的错误编辑；远程仓库则保护你免受笔记本电脑挂掉的风险——
并让你在每一台工作的机器上都保持 Skills 完全一致。

### 初始设置（一次）

创建一个**空的私有** GitHub 仓库（例如 `you/skills`），然后：

```bash
skillsync remote add git@github.com:you/skills.git
```

URL 会在写入任何内容之前先验证，你的本地快照会立即推送上去作为初始备份。

### 日常使用

```bash
skillsync sync
```

一条命令，按顺序做正确的事：

```text
有未保存的本地变更？
        ↓  自动做同步前快照（绝不与远程工作混在一起）
获取远程
        ↓
远程有新快照？  ── pull（fast-forward，或将本地提交重放其上）
        ↓
推送你的新快照
```

### 设置第二台机器

```bash
skillsync clone git@github.com:you/skills.git ~/.hermes/skills
```

之后在那台机器上照常使用 `skillsync`。`status` 会在每台机器上显示远程状态：

```text
Remote: git@github.com:you/skills.git
Remote state: up to date          (或: ahead 2 / behind 1 / unknown (offline))
```

### 两台机器同时改了同一个 Skill

不同 Skills 的变更由 Git 自动合并。只有当**同一个 Skill** 在两边都被改动时，
`sync` 才会停下来让你选择：

```text
Conflict: the same Skill changed on both sides — automatic merge failed.

  conflicting skill: productivity/pdf

Sync aborted — nothing changed locally. Your snapshots are safe.

Choose one:
  · Adopt the GitHub version:  skillsync sync --use-remote
  · Keep the local version:    manual git push --force-with-lease (rare)
```

SkillSync **绝不 force-push**，也绝不擅自裁定胜负。

### 认证

SkillSync 不自建认证层——直接沿用 git 的凭据：

| 方式 | 依赖 |
|---|---|
| GitHub CLI | `gh auth login`（git 会使用它的凭据助手） |
| SSH | `ssh-keygen` 生成密钥并加入 GitHub，使用 `git@github.com:...` URL |
| Token | 通过 HTTPS 使用个人访问令牌（凭据管理器或 `git-credential-store`） |

如果 `remote add` 报 `could not reach`，请先完成上面任一种配置。

> **首次推送前检查两件事：** 仓库必须是**私有的**；Skills 目录里常常有明文
> API 密钥——先删除它们，或改用环境变量。

---

## CLI

命令面刻意保持很小：

```bash
skillsync init

skillsync status          # 设置远程后，也会显示远程状态

skillsync diff [skill]

skillsync snapshot [-m "message"]

skillsync log [skill]

skillsync restore <skill> [commit]

skillsync remote [add <url> | remove]

skillsync clone <url> <path>

skillsync sync [--use-remote]
```

就这些。

SkillSync 不是要取代 Git。

它在 Git 之上加了一层 Skill 感知——并在 `git push` 之上加了一层
安全优先的同步。

---

## 工作原理

SkillSync 使用 Git 做实际的版本控制。

```text
                 SkillSync
                     │
          ┌──────────┴──────────┐
          │                     │
    Skill 感知层               Git
          │                     │
     ┌────┼────┐          ┌─────┼─────┐
     │    │    │          │     │     │
   status diff restore   commit  diff  history
```

一个 Skill 被视为一个逻辑单元：

```text
browser-research/
├── SKILL.md
├── references/
└── scripts/
```

目录内任何文件发生变更，SkillSync 都会把变更报告为：

```text
M browser-research
```

Git 仍负责存储真实的历史。

---

## 设计原则

### 本地优先

你的 Skills 留在你的机器上。

不依赖任何云服务——GitHub 远程是可选的，所有本地命令在完全离线时也能工作。

### Git 原生

SkillSync 不另造一套版本控制系统。

底层能力由 Git 提供：

* commits
* diffs
* history
* restore

### Skill 优先

用户想的是 Skills。

SkillSync 以 Skill 级别呈现变更。

### 默认安全

恢复一个 Skill 永远不该静默地毁掉历史。

### 极简

项目只聚焦一个问题：

> **保护 Agent Skills 免受糟糕的变更。**

---

## 支持的 Agent

SkillSync 与具体 harness 无关：它可以对**任何** Skills 目录做版本管理。
内置适配器会定位各家 harness 的 Skills 目录：

| Agent | Skills 目录（按优先级） |
|---|---|
| Hermes Agent | `$HERMES_HOME/skills` → `~/.hermes/skills` → `/opt/.hermes/skills` → `/opt/data/.hermes/skills` → `/usr/local/.hermes/skills` |
| OpenClaw | `$OPENCLAW_STATE_DIR/skills` → `~/.openclaw/skills` |
| Claude Code | `~/.claude/skills` |
| Codex | `~/.codex/skills` → `/etc/codex/skills` |

任何其他目录都可用 `skillsync init --path`。

Skill 的发现规则在所有地方一致：**直接包含 `SKILL.md` 文件的目录**，不限
深度。Skill 由它相对 Skills 目录的路径标识——例如扁平布局下的
`browser-research`，或 harness 按 category 分组时的 `productivity/pdf`。扁平
与嵌套布局同样支持。

检测到多个 harness 时，`init` 会列出候选，要求你用 `--agent <key>` 或
`--path` 选定一个——它绝不瞎猜。

---

## 项目状态

**早期 MVP / 实验性**

项目当前的目标是验证一条核心工作流：

```text
Agent 修改 Skill
        ↓
SkillSync 检测到变更
        ↓
用户查看 diff
        ↓
用户保存版本
        ↓
Agent 做出糟糕的变更
        ↓
用户恢复之前的版本
```

优先级是真实场景的使用，而非功能完备性。

---

## 路线图

### MVP

* [x] 产品定义
* [x] Skills 目录适配器（Hermes、OpenClaw、Claude Code、Codex）
* [x] 布局无关的 Skill 发现（扁平与 category 嵌套）
* [x] `skillsync init`（带 `--path` / `--agent` 选择）
* [x] Skill 级别的 `status`
* [x] Skill 感知的 `diff`
* [x] `snapshot`
* [x] `log`
* [x] `restore`

### v0.3 — 远程同步

* [x] `skillsync remote add/remove`（URL 验证、初始备份推送）
* [x] `skillsync sync`（同步前快照 → fetch → rebase → push）
* [x] `skillsync clone <url> <path>`（第二台机器的设置）
* [x] `status` 远程状态（ahead/behind，离线安全）
* [x] 冲突策略：中止 + Skill 级别报告 + 显式 `--use-remote`
* [x] 安全规则：绝不 force-push、超时控制、离线绝不改动本地状态

### 之后

潜在的未来工作包括：

* `remote add --create`（通过 `gh` CLI 创建私有 GitHub 仓库）
* 更好的 CLI 使用体验
* 可选的 Web/桌面 UI

以下内容**刻意排除在当前路线图之外**：

* Skill 市场
* Skill 发现
* Skill 分享平台
* 团队协作
* 企业管理

---

## 开发

在本地检出中运行测试套件：

```bash
pip install -e .[dev]
pytest
```

## 贡献

项目处于早期阶段，设计可能随着 MVP 在真实 Agent 工作流中的检验而调整。

欢迎 issue、反馈和 pull request。
