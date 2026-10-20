---
name: starter-unregister-repo
description: Take a repository out of a workspace by running tool/starter.py unregister, which removes its entry from workspace.json and the workspace table and leaves the folder untouched. Use when the user wants to remove, unregister, unlist, or drop a repository from a workspace (for example "admin 레포 워크스페이스에서 빼줘", "레포 등록 해제해줘").
---

# Unregister a repository

## 1. Locate

- Choose the workspace with [choose-workspace.md](../starter-workspace/references/choose-workspace.md), then the repository by the name its `workspace list` entry shows.
- If the user named a folder rather than an entry, match it by `path`. A folder that has no entry is not registered; say so and stop.
- Removing a whole workspace from the saved list is a different request: `workspace remove --path <path>` in [choose-workspace.md](../starter-workspace/references/choose-workspace.md).

## 2. Explain what changes

Before running, say in two or three lines:

- `workspace.json` loses the entry and the table in the workspace `AGENTS.md` loses its row. The repository folder and every file in it stay as they are.
- For a `managed` entry: the installed harness stays in the repository and keeps working there. `upgrade --workspace` no longer covers it,
  but `harness upgrade --repo <path>` through `starter-upgrade` still does. Listing it again with `starter-adopt-repo` (without install) shows it as `managed`.
- Read the text between the `workspace:contracts` markers of the workspace `AGENTS.md`. List every contract line that names the repository;
  the command does not change them.

Wait for the user to confirm.

## 3. Run

From this starter's root:

```bash
python3 tool/starter.py unregister --workspace <path> --name <name>
```

- On `"ok": false` nothing was written. An unknown name lists the registered ones; show them and ask again.
- On success, report `removed` and every entry in `warnings`. A warning about missing table markers means `workspace.json` changed but the table did not;
  offer to restore the markers and run `sync`.

## 4. Next

- Contract lines that name the repository: propose their new text and edit them only after approval, following `starter-workspace`.
- Deleting or moving the folder is the user's decision. Never do it yourself; if asked, show what the folder holds and its `git status` first.
- Nothing is committed. Offer the workspace commit through `starter-workspace`.
