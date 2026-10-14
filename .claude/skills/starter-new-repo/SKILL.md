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

## 2. Collect inputs

Ask in one message for whatever the request did not give:

- **Workspace path**: outside this starter. If it already has `workspace.json`, read it and show the registered repositories.
- **Per repository**: a folder name (letters, digits, `.`, `_`, `-`), a one-line role stating what it owns (for example `Backend API: auth, payments`),
  and an optional remote URL. A remote only configures `origin`; nothing is pushed.

Suggest names such as `be`, `web`, `app`, but never invent a role the user did not state. If the user actually wants to bring in an existing folder, switch to `starter-adopt-repo`.

## 3. Create

State in one line which folders will be created, then run from this starter's root, once per repository:

```bash
python3 tool/starter.py new --workspace <path> --name <name> --role "<role>" [--remote <url>]
```

The output is JSON. On `"ok": false` nothing was written: show the error and resolve it with the user.
On success, report the repository path, `workspaceCreated` on the first run, and every entry in `warnings`.

## 4. Next

Nothing is committed in the workspace or in the repository. Offer the next steps:

- Onboard the repository, here with `starter-onboard-repo`, or in an agent session opened in the repository. Until onboarding, its `AGENTS.md` allows no other tracked change.
- With two or more repositories, record the contracts between them with `starter-workspace`.
