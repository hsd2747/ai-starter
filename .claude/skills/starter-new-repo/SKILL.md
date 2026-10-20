---
name: starter-new-repo
description: Create a workspace and new repositories from this starter through conversation by running tool/starter.py new. Use when the user asks to create or set up a new repository, project, backend, web, or app, or a new workspace (for example "레포 만들어줘", "be랑 web 세팅해줘").
---

# New repository

The generator validates names, paths, and conflicts itself and writes nothing when a check fails. Do not re-implement its checks; run it and relay its answer.

## 1. Starter version

Run `git rev-parse --verify --quiet HEAD` and `git status --porcelain -- template workspace-template` in this starter.

- No commit: the new repository's `.ai/harness.json` cannot name a starter version, so a later upgrade cannot tell which files the starter changed.
- Uncommitted changes under `template/` or `workspace-template/`: the record names a commit that does not contain them.

In either case tell the user in one line and ask whether to continue (fine for a trial) or commit the starter first. Commit only when the user asks.
When the starter is committed and clean, do not mention this check.

## 2. Workspace

Read [choose-workspace.md](../starter-workspace/references/choose-workspace.md) and follow it. Settle the workspace before asking about repositories.

## 3. Repositories

Use whatever the request or the skill arguments already give. Ask about the product, not about fields.

1. When the request does not say what to build, ask one short question: which repositories are needed and what each owns, in the user's own words
   (for example "a backend for auth and payments, and a web admin"). Skip names the workspace already registers.
2. Propose a small table and ask for a yes or corrections:
   - Per repository: a folder name derived from its role (`be`, `web`, `app`, `admin`, ...) and the role in one line, in the user's words.
   - Remote: only if the user gave one. Otherwise say it can be added later with `git remote add origin <url>`.

Do not list naming rules or field formats; the generator rejects invalid input without writing anything, and you relay that.
Never invent a role the user did not state. If the user actually wants to bring in an existing folder, switch to `starter-adopt-repo`.

## 4. Create

State in one line which folders will be created, then run from this starter's root, once per repository:

```bash
python3 tool/starter.py new --workspace <path> --name <name> --role "<role>" [--remote <url>]
```

The output is JSON. On `"ok": false` nothing was written: show the error and resolve it with the user.
On success, report the repository path, `workspaceCreated` on the first run, and every entry in `warnings`.
The pre-commit hook is connected in the new repository, so every commit there runs `verify`; a teammate's clone connects it with `python3 tool/ai.py hooks install`.

## 5. Next

Nothing is committed in the workspace or in the repository. Offer the next steps:

- Onboard the repository, here with `starter-onboard-repo`, or in an agent session opened in the repository. Until onboarding, its `AGENTS.md` allows no other tracked change.
- With two or more repositories, record the contracts between them with `starter-workspace`.
