---
name: starter-adopt-repo
description: Bring an existing repository that this starter did not create into a workspace, registered with its role only or with the harness installed, by running tool/starter.py adopt. Use when the user wants to add, register, or adopt an existing repository or folder into a workspace, or to install the harness into a repository that is only registered (for example "기존 admin 레포도 워크스페이스에 넣어줘").
---

# Adopt a repository

## 1. Locate

- Choose the workspace with [choose-workspace.md](../starter-workspace/references/choose-workspace.md), then get the repository folder.
  The folder must already be a git repository inside the workspace; `--path` is relative to the workspace.
- If the repository lives elsewhere or only on a remote, propose `git clone <url> <workspace>/<name>` or a move, and run it only after the user confirms.
- The `workspace list` output shows the workspace's repositories. A `registered` entry at the same path can be adopted again with `--install`; a `managed` entry is already done.

## 2. Choose the mode

Explain the two modes in two lines and recommend one from what the user said:

- **register** (no `--install`): the folder is listed in the workspace table with its role, and nothing inside it changes.
  Fits a repository another team owns or one that keeps its own agent rules.
- **install**: copies the harness (`AGENTS.md`, `CLAUDE.md`, `REVIEW.md`, `.ai/`, `.agents/`, `.claude/`, `.gemini/`, `tool/`, `wiki/`, the verify workflow).
  Fits a repository this team will develop with agents. `.gitignore` and `.gitattributes` are merged by appending missing lines.

Before an install, run `git -C <repo> status --porcelain`. If the worktree is dirty, recommend committing or stashing first so that the harness
arrives as its own reviewable change; do neither yourself unless the user asks.

## 3. Run

State in one line what will be written, then run from this starter's root:

```bash
python3 tool/starter.py adopt --workspace <path> --path <relative> [--name <name>] [--role "<role>"] [--remote <url>] [--install]
```

- On `"ok": false` nothing was written. When the error lists existing harness files, show them and ask how to handle each:
  rename or move it and merge it by hand after the install, or stay registered. Never delete, rename, or overwrite a user file without confirmation.
- On success, report `kind`, `merged`, and every entry in `warnings`. After an install, summarize `git -C <repo> status --short` by top-level folder.

## 4. Next

Nothing is committed. After an install the repository is not onboarded yet: offer `starter-onboard-repo`; the onboarding skill's existing-codebase reference applies.
