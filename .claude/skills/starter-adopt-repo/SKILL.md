---
name: starter-adopt-repo
description: List an existing repository that this starter did not create in a workspace, with its role, by running tool/starter.py adopt, optionally installing the harness in the same step. Use when the user wants to add, register, or adopt an existing repository or folder into a workspace (for example "기존 admin 레포도 워크스페이스에 넣어줘").
---

# Adopt a repository

Adopting is workspace work: it lists the repository in `workspace.json` and the workspace table. Installing the harness is a separate step
that `adopt --install` runs first; on its own it is `starter-install-harness`.

## 1. Locate

- Choose the workspace with [choose-workspace.md](../starter-workspace/references/choose-workspace.md), then get the repository folder.
  The folder must already be a git repository inside the workspace; `--path` is relative to the workspace.
- If the repository lives elsewhere or only on a remote, propose `git clone <url> <workspace>/<name>` or a move, and run it only after the user confirms.
- The `workspace list` output shows the workspace's repositories. A listed `registered` entry that should get the harness goes to `starter-install-harness`;
  a listed `managed` entry is already done.

## 2. Choose the mode

Explain the two modes in two lines and recommend one from what the user said:

- **register** (no `--install`): the folder is listed in the workspace table with its role, and nothing inside it changes.
  Fits a repository another team owns or one that keeps its own agent rules. A folder that already has the harness shows as `managed`.
- **install**: also installs the harness. Fits a repository this team will develop with agents.
  Before choosing it, follow sections 1 and 2 of [starter-install-harness](../starter-install-harness/SKILL.md): harness status, a clean worktree,
  and the approved merge plan for the repository's existing agent instructions.

## 3. Run

State in one line what will be written, then run from this starter's root:

```bash
python3 tool/starter.py adopt --workspace <path> --path <relative> [--name <name>] [--role "<role>"] [--remote <url>] [--install]
```

- On `"ok": false` nothing was written. Existing harness files are handled as in `starter-install-harness`.
- On success, report `kind`, `merged`, `existingInstructions`, and every entry in `warnings`. After an install, summarize `git -C <repo> status --short` by top-level folder.

## 4. Next

Nothing is committed. After an install the repository is not onboarded yet: offer `starter-onboard-repo` and hand it the dispositions approved before the install.
